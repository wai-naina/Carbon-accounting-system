from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Tuple

import pandas as pd

from app.database.models import CarbonNestCycleData

# "Plant cycles" export: per-cycle process performance (ADS/DES/BAG, efficiencies, capacities).
CYCLE_COLUMNS = {
    "Cycle #": "cycle_number",
    "Module": "raw_module",
    "Start Time": "start_time",
    "End Time": "end_time",
    "Type": "cycle_type",
    "ADS CO2 (kg)": "ads_co2_kg",
    "ADS Hours": "ads_hours",
    "ADS Lost CO2 (kg)": "ads_lost_co2_kg",
    "ADS Efficiency": "ads_efficiency",
    "ADS Mass Cap": "ads_mass_cap",
    "ADS Vol Cap": "ads_vol_cap",
    "DES CO2 (kg)": "des_co2_kg",
    "DES Hours": "des_hours",
    "BAG CO2 (kg)": "bag_co2_kg",
    "DES Efficiency": "des_efficiency",
    "BAG Efficiency": "bag_efficiency",
    "DES Vol Cap": "des_vol_cap",
    "eTotal kWh": "total_kwh",
    "Steam (kg)": "steam_kg",
}

# "Cycle energy" export: per-cycle energy breakdown by subsystem.
ENERGY_COLUMNS = {
    "Cycle #": "cycle_number",
    "Module": "raw_module",
    "MWh/tCO2": "mwh_per_tco2",
    "Fans (kWh)": "fans_kwh",
    "CT (kWh)": "ct_kwh",
    "CT Pump (kWh)": "ct_pump_kwh",
    "VP402 (kWh)": "vp402_kwh",
    "VP501 (kWh)": "vp501_kwh",
    "Boiler A (kWh)": "boiler_a_kwh",
    "Boiler B (kWh)": "boiler_b_kwh",
    "Main Utility (kWh)": "main_utility_kwh",
}

_NELION_TOKEN = re.compile(r"N(\d+)")


def parse_series_and_nelion(raw_module: str) -> Tuple[str, Optional[str]]:
    """Split a Carbon Nest 'Module' value like 'N1N2-M1n3' or 'N2-M2n4' into
    (series, nelion). series is '1n3' or '2n4'. nelion is 'N1'/'N2'/... only
    when the module prefix names exactly one Nelion; it's None when the
    prefix names a combined/interleaved reading across multiple Nelions
    (current SCADA limitation — see carbon_nest_embodied.py module docstring
    equivalent discussion in the aggregation service) or can't be parsed.
    """
    if not raw_module:
        return "unknown", None

    prefix, _, suffix = raw_module.partition("-")
    series = "unknown"
    suffix_lower = suffix.lower()
    if "1n3" in suffix_lower:
        series = "1n3"
    elif "2n4" in suffix_lower:
        series = "2n4"

    nelion_tokens = _NELION_TOKEN.findall(prefix)
    nelion = f"N{nelion_tokens[0]}" if len(nelion_tokens) == 1 else None

    return series, nelion


@dataclass
class ImportReport:
    added: int
    skipped: int
    errors: List[str]
    warnings: List[str]
    date_range: Tuple[Optional[datetime], Optional[datetime]]


def _validate_columns(df: pd.DataFrame, mapping: dict, label: str) -> List[str]:
    missing = [col for col in mapping.keys() if col not in df.columns]
    if missing:
        return [f"{label} missing columns: {', '.join(missing)}"]
    return []


def _parse_dates(df: pd.DataFrame, column: str) -> pd.Series:
    return pd.to_datetime(df[column], errors="coerce")


def load_plant_cycles(file) -> Tuple[pd.DataFrame, List[str]]:
    df = pd.read_csv(file)
    errors = _validate_columns(df, CYCLE_COLUMNS, "Plant Cycles CSV")
    if errors:
        return df, errors
    df = df[list(CYCLE_COLUMNS.keys())].rename(columns=CYCLE_COLUMNS)
    df["start_time"] = _parse_dates(df, "start_time")
    df["end_time"] = _parse_dates(df, "end_time")
    return df, []


def load_cycle_energy(file) -> Tuple[pd.DataFrame, List[str]]:
    df = pd.read_csv(file)
    errors = _validate_columns(df, ENERGY_COLUMNS, "Cycle Energy CSV")
    if errors:
        return df, errors
    df = df[list(ENERGY_COLUMNS.keys())].rename(columns=ENERGY_COLUMNS)
    return df, []


def merge_plant_cycles_energy(cycles_df: pd.DataFrame, energy_df: pd.DataFrame) -> pd.DataFrame:
    energy_only = energy_df.drop(columns=["raw_module"], errors="ignore")
    merged = pd.merge(cycles_df, energy_only, on="cycle_number", how="outer", suffixes=("", "_energy"))
    return merged


def import_cycles(session, merged_df: pd.DataFrame, import_batch_id: str) -> ImportReport:
    errors: List[str] = []
    warnings: List[str] = []
    added = 0
    skipped = 0

    if merged_df.empty:
        return ImportReport(0, 0, ["No data rows to import."], [], (None, None))

    existing_numbers = {
        row.cycle_number for row in session.query(CarbonNestCycleData.cycle_number).all()
    }

    date_range = (
        merged_df["start_time"].min() if "start_time" in merged_df else None,
        merged_df["start_time"].max() if "start_time" in merged_df else None,
    )

    for _, row in merged_df.iterrows():
        cycle_number = row.get("cycle_number")
        if pd.isna(cycle_number):
            skipped += 1
            continue
        cycle_number = int(cycle_number)
        if cycle_number in existing_numbers:
            skipped += 1
            continue

        if pd.isna(row.get("start_time")):
            errors.append(f"Missing start_time for cycle {cycle_number}")
            continue

        raw_module = str(row.get("raw_module") or "")
        series, nelion = parse_series_and_nelion(raw_module)

        cycle = CarbonNestCycleData(
            cycle_number=cycle_number,
            raw_module=raw_module,
            series=series,
            nelion=nelion,
            start_time=pd.to_datetime(row["start_time"]).to_pydatetime(),
            end_time=pd.to_datetime(row["end_time"]).to_pydatetime() if not pd.isna(row.get("end_time")) else None,
            cycle_type=_to_str(row.get("cycle_type")),
            ads_co2_kg=_to_float(row.get("ads_co2_kg")),
            ads_hours=_to_float(row.get("ads_hours")),
            ads_lost_co2_kg=_to_float(row.get("ads_lost_co2_kg")),
            ads_efficiency=_to_float(row.get("ads_efficiency")),
            ads_mass_cap=_to_float(row.get("ads_mass_cap")),
            ads_vol_cap=_to_float(row.get("ads_vol_cap")),
            des_co2_kg=_to_float(row.get("des_co2_kg")),
            des_hours=_to_float(row.get("des_hours")),
            des_efficiency=_to_float(row.get("des_efficiency")),
            des_vol_cap=_to_float(row.get("des_vol_cap")),
            bag_co2_kg=_to_float(row.get("bag_co2_kg")),
            bag_efficiency=_to_float(row.get("bag_efficiency")),
            total_kwh=_to_float(row.get("total_kwh")),
            mwh_per_tco2=_to_float(row.get("mwh_per_tco2")),
            fans_kwh=_to_float(row.get("fans_kwh")),
            ct_kwh=_to_float(row.get("ct_kwh")),
            ct_pump_kwh=_to_float(row.get("ct_pump_kwh")),
            vp402_kwh=_to_float(row.get("vp402_kwh")),
            vp501_kwh=_to_float(row.get("vp501_kwh")),
            boiler_a_kwh=_to_float(row.get("boiler_a_kwh")),
            boiler_b_kwh=_to_float(row.get("boiler_b_kwh")),
            main_utility_kwh=_to_float(row.get("main_utility_kwh")),
            steam_kg=_to_float(row.get("steam_kg")),
            import_batch_id=import_batch_id,
        )
        session.add(cycle)
        added += 1

    session.commit()
    return ImportReport(added, skipped, errors, warnings, date_range)


def _to_float(value) -> Optional[float]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_str(value) -> Optional[str]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    return str(value)
