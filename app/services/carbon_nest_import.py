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


# Datetime layouts the SCADA export has been seen to use, most specific first.
# Each entry is (strptime format, human label). Both a US month-first and a
# day-first layout are listed because the export has shipped both — see
# infer_datetime_format() for how the ambiguity is resolved.
_DATETIME_FORMATS: Tuple[Tuple[str, str], ...] = (
    ("%Y-%m-%d %H:%M:%S", "ISO (YYYY-MM-DD)"),
    ("%Y-%m-%d %H:%M", "ISO (YYYY-MM-DD)"),
    ("%m/%d/%Y %H:%M:%S", "month-first (MM/DD/YYYY)"),
    ("%m/%d/%Y %H:%M", "month-first (MM/DD/YYYY)"),
    ("%d/%m/%Y %H:%M:%S", "day-first (DD/MM/YYYY)"),
    ("%d/%m/%Y %H:%M", "day-first (DD/MM/YYYY)"),
)


def _blank_mask(raw: pd.Series) -> pd.Series:
    """True where the source cell is genuinely empty (vs. unparseable)."""
    return raw.isna() | (raw.astype(str).str.strip().isin(["", "nan", "NaT", "None"]))


def _parse_with_format(raw: pd.Series, fmt: str) -> Optional[pd.Series]:
    """Parse the whole column with `fmt`, or None if any non-blank cell fails.

    Deliberately all-or-nothing. The old code called pd.to_datetime() with no
    format and errors="coerce", which let pandas infer a layout from the FIRST
    row and then silently coerce every row that disagreed with it into NaT —
    the exact failure that put month-first dates into a day-first export.
    """
    parsed = pd.to_datetime(raw, format=fmt, errors="coerce")
    failed = parsed.isna() & ~_blank_mask(raw)
    if failed.any():
        return None
    return parsed


def infer_datetime_format(
    df: pd.DataFrame, columns: List[str], order_column: Optional[str] = None
) -> Tuple[Optional[str], Optional[str], List[str]]:
    """Work out which datetime layout this export actually uses.

    Returns (format, human label, errors).

    A layout is a candidate only if it parses EVERY non-blank cell in EVERY
    datetime column. That alone disambiguates any file containing at least one
    date whose day is >12 (e.g. "22/08/2026" cannot be month-first).

    When a file is wholly ambiguous — every single date has day <=12, so both
    layouts parse cleanly but disagree on what they mean — two tie-breakers
    run in order:

    1. `order_column` (cycle number). Carbon Nest cycle numbers are issued in
       chronological order, so a layout whose timestamps run backwards against
       them is wrong. This alone is often not enough: real dates 7, 8, 9 Sep
       read month-first become 9 Jul, 9 Aug, 9 Sep, which still ascends.
    2. Date span. Transposing day and month maps day-of-month onto
       month-of-year, which can only stretch a file's range, never compress
       it — so whichever layout yields the tighter span is the true one. This
       holds in both directions, for genuinely day-first and genuinely
       month-first exports alike.

    Only a degenerate file (one row, or one distinct date) survives both. For
    that, this returns an error rather than picking one, because a silent
    wrong guess shifts cycles into the wrong weeks and corrupts every weekly
    summary downstream.
    """
    candidates = []
    for fmt, label in _DATETIME_FORMATS:
        if all(_parse_with_format(df[col], fmt) is not None for col in columns):
            candidates.append((fmt, label))

    if not candidates:
        samples = [str(v) for v in df[columns[0]].dropna().head(3).tolist()]
        return None, None, [
            "Could not parse the date column with any known layout "
            f"(tried {', '.join(sorted({lbl for _, lbl in _DATETIME_FORMATS}))}). "
            f"Sample values: {', '.join(samples) or '(none)'}"
        ]

    # Collapse candidates that produce identical timestamps — e.g. the
    # with-seconds and without-seconds ISO variants are not a real ambiguity.
    primary = columns[0]
    distinct: List[Tuple[str, str, pd.Series]] = []
    for fmt, label in candidates:
        parsed = _parse_with_format(df[primary], fmt)
        if not any(parsed.equals(seen) for _, _, seen in distinct):
            distinct.append((fmt, label, parsed))

    if len(distinct) == 1:
        fmt, label, _ = distinct[0]
        return fmt, label, []

    remaining = distinct
    if order_column and order_column in df.columns:
        order = pd.to_numeric(df[order_column], errors="coerce")
        monotonic = [c for c in remaining if _is_chronological(c[2], order)]
        if len(monotonic) == 1:
            return monotonic[0][0], monotonic[0][1], []
        if monotonic:
            remaining = monotonic

    # Both readings still standing (e.g. real dates Sep 7,8,9 read month-first
    # become Jul 9, Aug 9, Sep 9 — still ascending, so chronology alone cannot
    # separate them). Span does: swapping day and month maps day-of-month onto
    # month-of-year, which can only ever stretch a file's date range, never
    # compress it. A weekly SCADA export spans days; the wrong reading spans
    # months. So the tightest span is the true one.
    spans = [(_date_span_days(parsed), fmt, label) for fmt, label, parsed in remaining]
    spans.sort(key=lambda item: item[0])
    if len(spans) > 1 and spans[0][0] < spans[1][0]:
        return spans[0][1], spans[0][2], []

    labels = sorted({label for _, label, _ in remaining})
    return None, None, [
        "This export's dates are ambiguous — they parse equally well as "
        f"{' or '.join(labels)}, and the cycle ordering does not settle it. "
        "Every date in the file has a day of 12 or lower. Re-export with an "
        "unambiguous date format (ISO YYYY-MM-DD) rather than risk loading "
        "cycles into the wrong weeks."
    ]


def _is_chronological(timestamps: pd.Series, order: pd.Series) -> bool:
    """True if `timestamps` ascend when sorted by `order` (cycle number)."""
    frame = pd.DataFrame({"ts": timestamps, "order": order}).dropna()
    if len(frame) < 2:
        return False
    return frame.sort_values("order")["ts"].is_monotonic_increasing


def _date_span_days(timestamps: pd.Series) -> float:
    """Calendar days between the first and last timestamp, inf if unknowable."""
    clean = timestamps.dropna()
    if len(clean) < 2:
        return float("inf")
    return (clean.max() - clean.min()).total_seconds() / 86400.0


def load_plant_cycles(file) -> Tuple[pd.DataFrame, List[str]]:
    df = pd.read_csv(file)
    errors = _validate_columns(df, CYCLE_COLUMNS, "Plant Cycles CSV")
    if errors:
        return df, errors
    df = df[list(CYCLE_COLUMNS.keys())].rename(columns=CYCLE_COLUMNS)

    fmt, label, fmt_errors = infer_datetime_format(
        df, ["start_time", "end_time"], order_column="cycle_number"
    )
    if fmt_errors:
        return df, fmt_errors

    df["start_time"] = _parse_with_format(df["start_time"], fmt)
    df["end_time"] = _parse_with_format(df["end_time"], fmt)
    df.attrs["datetime_format_label"] = label
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


def validate_cycle_dates(df: pd.DataFrame) -> Tuple[List[str], List[str]]:
    """Sanity-check parsed cycle timestamps before anything is written.

    A last line of defence behind infer_datetime_format(). A day/month swap
    that slips through shows up here as timestamps in the future or as a
    cycle sequence that runs backwards in time, and both are cheap to spot
    and impossible to explain away physically.
    """
    errors: List[str] = []
    warnings: List[str] = []

    if "start_time" not in df.columns:
        return errors, warnings

    starts = pd.to_datetime(df["start_time"], errors="coerce")

    # Cycles cannot have run yet. A future timestamp is the loudest symptom of
    # a day/month swap (12/09 read month-first lands in December).
    horizon = pd.Timestamp.now() + pd.Timedelta(days=1)
    future = df[starts > horizon]
    if not future.empty:
        numbers = ", ".join(str(int(n)) for n in future["cycle_number"].dropna().head(5))
        errors.append(
            f"{len(future)} cycle(s) have a start time in the future (e.g. cycle {numbers}). "
            "This almost always means the export's dates were read with the day and "
            "month transposed. Import aborted — re-export with ISO (YYYY-MM-DD) dates."
        )

    if "end_time" in df.columns:
        ends = pd.to_datetime(df["end_time"], errors="coerce")
        backwards = df[ends.notna() & starts.notna() & (ends < starts)]
        if not backwards.empty:
            numbers = ", ".join(str(int(n)) for n in backwards["cycle_number"].dropna().head(5))
            errors.append(
                f"{len(backwards)} cycle(s) end before they start (e.g. cycle {numbers}). "
                "Import aborted."
            )

    # Cycle numbers are issued in chronological order, so their timestamps must
    # ascend with them. A warning rather than an error: a legitimately odd
    # export shouldn't be blocked, but it must not pass unremarked either.
    if "cycle_number" in df.columns:
        order = pd.to_numeric(df["cycle_number"], errors="coerce")
        if len(starts.dropna()) >= 2 and not _is_chronological(starts, order):
            warnings.append(
                "Cycle start times do not increase with cycle number. Check the export's "
                "date format before trusting the weekly totals built from it."
            )

    blank_starts = df[starts.isna()]
    if not blank_starts.empty:
        warnings.append(
            f"{len(blank_starts)} row(s) have no usable start time and will be skipped."
        )

    return errors, warnings


def import_cycles(session, merged_df: pd.DataFrame, import_batch_id: str) -> ImportReport:
    errors: List[str] = []
    warnings: List[str] = []
    added = 0
    skipped = 0

    if merged_df.empty:
        return ImportReport(0, 0, ["No data rows to import."], [], (None, None))

    date_errors, date_warnings = validate_cycle_dates(merged_df)
    warnings.extend(date_warnings)
    if date_errors:
        return ImportReport(0, 0, date_errors, warnings, (None, None))

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
