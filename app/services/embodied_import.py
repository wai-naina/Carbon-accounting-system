from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Dict, List, Optional, Tuple

import pandas as pd


def _normalize(value: str) -> str:
    return "".join(ch for ch in value.lower().strip() if ch.isalnum())


def suggest_mapping(columns: List[str], aliases: Dict[str, List[str]]) -> Dict[str, Optional[str]]:
    normalized = {_normalize(col): col for col in columns}
    mapping: Dict[str, Optional[str]] = {}
    for field, options in aliases.items():
        match = None
        for alias in options:
            key = _normalize(alias)
            if key in normalized:
                match = normalized[key]
                break
        mapping[field] = match
    return mapping


def parse_float(value) -> Optional[float]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_int(value) -> Optional[int]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_date(value) -> Optional[date]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.date()


@dataclass
class ImportStats:
    added: int
    skipped: int
    errors: List[str]


INFRA_ALIASES = {
    "zone": ["zone", "area", "section"],
    "item": ["item", "equipment", "component", "asset", "material"],
    "weight_kg": ["weight_kg", "weight (kg)", "mass_kg", "mass (kg)", "weight"],
    "emission_factor": [
        "emission_factor",
        "ef",
        "ef (kg co2/kg)",
        "emission factor (kg co2/kg)",
        "kg co2/kg",
    ],
    "lifetime_years": ["lifetime", "lifetime years", "years"],
    "notes": ["notes", "comment", "remarks"],
}


SORBENT_ALIASES = {
    "batch_number": ["batch", "batch number", "batch_number"],
    "start_date": ["start date", "start_date", "date"],
    "alumina_kg": ["alumina", "alumina_kg", "alumina (kg)"],
    "pei_kg": ["pei", "pei_kg", "pei (kg)"],
    "methanol_kg": ["methanol", "methanol_kg", "methanol (kg)"],
    "ef_alumina": ["ef alumina", "ef_alumina", "alumina ef"],
    "ef_pei": ["ef pei", "ef_pei", "pei ef"],
    "ef_methanol": ["ef methanol", "ef_methanol", "methanol ef"],
    "eol_ef": ["eol ef", "eol_ef", "end of life ef", "eol factor"],
    "notes": ["notes", "comment", "remarks"],
}


def build_excel_preview(file, sheet_name: str, max_rows: int = 5) -> pd.DataFrame:
    df = pd.read_excel(file, sheet_name=sheet_name)
    return df.head(max_rows)


def _find_header_row(df: pd.DataFrame, label: str) -> Optional[int]:
    for idx in range(min(25, len(df))):
        value = df.iloc[idx, 0]
        if isinstance(value, str) and _normalize(value) == _normalize(label):
            return idx
    return None


def _find_column(columns: List[str], contains: List[str]) -> Optional[str]:
    for col in columns:
        normalized = _normalize(str(col))
        if all(part in normalized for part in contains):
            return col
    return None


def parse_octavia_zone_sheet(file, sheet_name: str, zone_label: str) -> List[Dict[str, Optional[float]]]:
    df_raw = pd.read_excel(file, sheet_name=sheet_name, header=None)
    header_row = _find_header_row(df_raw, "Item")
    if header_row is None:
        return []
    df = pd.read_excel(file, sheet_name=sheet_name, header=header_row)
    item_col = _find_column(list(df.columns), ["item"])
    weight_col = _find_column(list(df.columns), ["weight", "kg"])
    ef_col = _find_column(list(df.columns), ["ef", "kgco2"])
    embodied_col = _find_column(list(df.columns), ["embodied", "kg"])

    rows: List[Dict[str, Optional[float]]] = []
    for _, row in df.iterrows():
        item = row.get(item_col) if item_col else None
        embodied = parse_float(row.get(embodied_col)) if embodied_col else None
        weight = parse_float(row.get(weight_col)) if weight_col else None
        ef = parse_float(row.get(ef_col)) if ef_col else None
        if not item or embodied is None:
            continue
        rows.append(
            {
                "zone": zone_label,
                "item": str(item),
                "weight_kg": weight,
                "emission_factor": ef,
                "embodied_co2_kg": embodied,
            }
        )
    return rows


def parse_octavia_transport_sheet(file) -> List[Dict[str, Optional[float]]]:
    df_raw = pd.read_excel(file, sheet_name="Transport", header=None)
    header_row = _find_header_row(df_raw, "Route Description")
    if header_row is None:
        return []
    df = pd.read_excel(file, sheet_name="Transport", header=header_row)
    route_col = _find_column(list(df.columns), ["route"])
    weight_col = _find_column(list(df.columns), ["weight", "tonnes"])
    ef_col = _find_column(list(df.columns), ["ef", "kgco2"])
    embodied_col = _find_column(list(df.columns), ["embodied", "kg"])

    rows: List[Dict[str, Optional[float]]] = []
    for _, row in df.iterrows():
        route = row.get(route_col) if route_col else None
        embodied = parse_float(row.get(embodied_col)) if embodied_col else None
        weight_tonnes = parse_float(row.get(weight_col)) if weight_col else None
        if not route or embodied is None:
            continue
        rows.append(
            {
                "zone": "Transport",
                "item": str(route),
                "weight_kg": weight_tonnes * 1000 if weight_tonnes is not None else None,
                "emission_factor": parse_float(row.get(ef_col)) if ef_col else None,
                "embodied_co2_kg": embodied,
            }
        )
    return rows


def parse_octavia_sorbent_sheet(file) -> Dict[str, Optional[float]]:
    df_raw = pd.read_excel(file, sheet_name="Sorbent_System", header=None)
    header_row = _find_header_row(df_raw, "Item")
    if header_row is None:
        return {}
    df = pd.read_excel(file, sheet_name="Sorbent_System", header=header_row)
    item_col = _find_column(list(df.columns), ["item"])
    qty_col = _find_column(list(df.columns), ["qty", "batch", "kg"])
    lifetime_col = _find_column(list(df.columns), ["lifetime", "years"])
    ef_col = _find_column(list(df.columns), ["ef", "kgco2"])
    embodied_col = _find_column(list(df.columns), ["embodied", "batch"])

    def row_for(label: str) -> Optional[pd.Series]:
        if not item_col:
            return None
        matches = df[df[item_col].astype(str).str.strip().str.lower() == label.lower()]
        return matches.iloc[0] if not matches.empty else None

    alumina_row = row_for("Support Material (Alumina)")
    pei_row = row_for("Active Sorbent (PEI)")
    methanol_row = row_for("Methanol (regeneration)")
    alumina_eol_row = row_for("Support Material EOL")
    pei_eol_row = row_for("Active Sorbent EOL")
    methanol_eol_row = row_for("Methanol EOL")

    def row_qty(row: Optional[pd.Series]) -> Optional[float]:
        return parse_float(row.get(qty_col)) if row is not None and qty_col else None

    def row_ef(row: Optional[pd.Series]) -> Optional[float]:
        return parse_float(row.get(ef_col)) if row is not None and ef_col else None

    def row_embodied(row: Optional[pd.Series]) -> Optional[float]:
        return parse_float(row.get(embodied_col)) if row is not None and embodied_col else None

    alumina_kg = row_qty(alumina_row)
    pei_kg = row_qty(pei_row)
    methanol_kg = row_qty(methanol_row)

    production = sum(
        value or 0
        for value in [
            row_embodied(alumina_row),
            row_embodied(pei_row),
            row_embodied(methanol_row),
        ]
    )
    eol = sum(
        value or 0
        for value in [
            row_embodied(alumina_eol_row),
            row_embodied(pei_eol_row),
            row_embodied(methanol_eol_row),
        ]
    )

    lifetime_years = None
    if lifetime_col and alumina_row is not None:
        lifetime_years = parse_float(alumina_row.get(lifetime_col))

    return {
        "alumina_kg": alumina_kg,
        "pei_kg": pei_kg,
        "methanol_kg": methanol_kg,
        "production_embodied_kg": production,
        "eol_embodied_kg": eol,
        "total_embodied_kg": production + eol,
        "lifetime_years": lifetime_years,
        "ef_alumina": row_ef(alumina_row),
        "ef_pei": row_ef(pei_row),
        "ef_methanol": row_ef(methanol_row),
        "ef_eol": row_ef(alumina_eol_row) or row_ef(pei_eol_row) or row_ef(methanol_eol_row),
    }
