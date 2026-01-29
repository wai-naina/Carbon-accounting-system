from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import List, Tuple

import pandas as pd

from app.database.models import CycleData


CYCLE_COLUMNS = {
    "Cycle #": "cycle_number",
    "Machine": "machine",
    "Start Time": "start_time",
    "ADS CO2 (kg)": "ads_co2_kg",
    "ADS Hours": "ads_hours",
    "DES CO2 (kg)": "des_co2_kg",
    "DES Hours": "des_hours",
    "BAG CO2": "bag_co2_kg",
    "eTotal kWh": "total_kwh",
    "Steam (kg)": "steam_kg",
}

ENERGY_COLUMNS = {
    "Cycle #": "cycle_number",
    "Machine": "machine",
    "eTotal (kWh)": "total_kwh",
    "Boiler (kWh)": "boiler_kwh",
    "SRV/LRVP (kWh)": "srv_lrvp_kwh",
    "CT (kWh)": "ct_kwh",
    "NM1 Fan (kWh)": "nm1_fan_kwh",
    "NM2 Fan (kWh)": "nm2_fan_kwh",
    "NM3 Fan (kWh)": "nm3_fan_kwh",
    "NM4 Fan (kWh)": "nm4_fan_kwh",
}


@dataclass
class ImportReport:
    added: int
    skipped: int
    errors: List[str]
    warnings: List[str]
    date_range: Tuple[datetime | None, datetime | None]


def _validate_columns(df: pd.DataFrame, mapping: dict, label: str) -> List[str]:
    missing = [col for col in mapping.keys() if col not in df.columns]
    if missing:
        return [f"{label} missing columns: {', '.join(missing)}"]
    return []


def _parse_dates(df: pd.DataFrame, column: str) -> pd.Series:
    return pd.to_datetime(df[column], errors="coerce")


def load_cycle_data(file) -> Tuple[pd.DataFrame, List[str]]:
    df = pd.read_csv(file)
    errors = _validate_columns(df, CYCLE_COLUMNS, "Cycle CSV")
    if errors:
        return df, errors
    df = df[list(CYCLE_COLUMNS.keys())].rename(columns=CYCLE_COLUMNS)
    if "total_kwh" in df.columns:
        df = df.rename(columns={"total_kwh": "cycle_total_kwh"})
    df["start_time"] = _parse_dates(df, "start_time")
    return df, []


def load_energy_data(file) -> Tuple[pd.DataFrame, List[str]]:
    df = pd.read_csv(file)
    errors = _validate_columns(df, ENERGY_COLUMNS, "Energy CSV")
    if errors:
        return df, errors
    df = df[list(ENERGY_COLUMNS.keys())].rename(columns=ENERGY_COLUMNS)
    return df, []


def merge_cycle_energy(cycle_df: pd.DataFrame, energy_df: pd.DataFrame) -> pd.DataFrame:
    merged = pd.merge(cycle_df, energy_df, on=["cycle_number", "machine"], how="outer")
    if "total_kwh" not in merged.columns and "cycle_total_kwh" in merged.columns:
        merged["total_kwh"] = merged["cycle_total_kwh"]
    elif "cycle_total_kwh" in merged.columns:
        merged["total_kwh"] = merged["total_kwh"].fillna(merged["cycle_total_kwh"])
    return merged


def import_cycles(session, merged_df: pd.DataFrame, import_batch_id: str) -> ImportReport:
    errors: List[str] = []
    warnings: List[str] = []
    added = 0
    skipped = 0

    if merged_df.empty:
        return ImportReport(0, 0, ["No data rows to import."], [], (None, None))

    existing_keys = {
        (row.cycle_number, row.machine)
        for row in session.query(CycleData.cycle_number, CycleData.machine).all()
    }

    date_range = (
        merged_df["start_time"].min() if "start_time" in merged_df else None,
        merged_df["start_time"].max() if "start_time" in merged_df else None,
    )

    for _, row in merged_df.iterrows():
        cycle_number = row.get("cycle_number")
        machine = row.get("machine")
        if pd.isna(cycle_number) or pd.isna(machine):
            skipped += 1
            continue
        cycle_key = (int(cycle_number), str(machine))
        if cycle_key in existing_keys:
            skipped += 1
            continue

        if pd.isna(row.get("start_time")):
            errors.append(f"Missing start_time for cycle {cycle_key}")
            continue

        cycle = CycleData(
            cycle_number=int(row["cycle_number"]),
            machine=str(row["machine"]),
            start_time=pd.to_datetime(row["start_time"]).to_pydatetime(),
            ads_co2_kg=_to_float(row.get("ads_co2_kg")),
            ads_hours=_to_float(row.get("ads_hours")),
            des_co2_kg=_to_float(row.get("des_co2_kg")),
            des_hours=_to_float(row.get("des_hours")),
            bag_co2_kg=_to_float(row.get("bag_co2_kg")),
            total_kwh=_to_float(row.get("total_kwh")),
            boiler_kwh=_to_float(row.get("boiler_kwh")),
            srv_lrvp_kwh=_to_float(row.get("srv_lrvp_kwh")),
            ct_kwh=_to_float(row.get("ct_kwh")),
            nm1_fan_kwh=_to_float(row.get("nm1_fan_kwh")),
            nm2_fan_kwh=_to_float(row.get("nm2_fan_kwh")),
            nm3_fan_kwh=_to_float(row.get("nm3_fan_kwh")),
            nm4_fan_kwh=_to_float(row.get("nm4_fan_kwh")),
            steam_kg=_to_float(row.get("steam_kg")),
            import_batch_id=import_batch_id,
        )
        session.add(cycle)
        added += 1

    session.commit()
    return ImportReport(added, skipped, errors, warnings, date_range)


def _to_float(value) -> float | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
