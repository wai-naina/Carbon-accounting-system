"""Weekly sorbent working capacity for Carbon Nest — reproduces an existing
published report metric, computed from the raw cycle log rather than by hand.

Working capacity here is **desorption-based**: moles of CO2 released during the
desorption half-cycle, divided by the sorbent bed volume that took part in that
cycle, averaged unweighted across the valid cycles in the week. It is *not*
adsorption uptake (runs ~20-40% higher) and *not* normalised for desorption
duration — both deliberate, since this reproduces an existing reported figure
rather than proposing a new one (see the brief's "Phase 2" for what's wanted on
top of this later).

Week windows reuse this app's existing Saturday-18:00 Carbon Nest week boundary
(`get_carbon_nest_week_bounds`) rather than the brief's stated Saturday-00:00
boundary, for consistency with every other Carbon Nest metric (Home page,
Dashboard, weekly PDF report all already use Sat 18:00). Verified directly
against the 108-cycle reference sample (25 Jun - 24 Jul 2026) that both
boundary conventions produce byte-identical results — no cycle in that sample
starts in the Sat-00:00-to-18:00 gap — so this choice doesn't change any of the
brief's acceptance numbers today. It could in principle diverge for a future
week if a cycle ever starts in that window; flagged here rather than silently
assumed away.
"""
from __future__ import annotations

from datetime import datetime
from statistics import mean
from typing import Optional

from app.database.models import CarbonNestCycleData, CarbonNestSorbentConfig
from app.services.carbon_nest_aggregation import get_carbon_nest_week_bounds

M_CO2_KG_PER_MOL = 0.04401
MIN_DES_CO2_KG_FOR_VALIDITY = 1.0  # documented interim heuristic, not a physical truth — see brief
CONFIG_ANOMALY_TOLERANCE = 0.005  # 0.5%

GROUP_LABELS = {"A": "Group A (M1 & M3)", "B": "Group B (M2 & M4)"}


def group_of(series: Optional[str]) -> Optional[str]:
    """Series '1n3' -> Group A, '2n4' -> Group B — matches the published report's
    own grouping, which is keyed off the module *suffix*, not the nest prefix."""
    if series == "1n3":
        return "A"
    if series == "2n4":
        return "B"
    return None


def module_prefix_of(raw_module: str) -> str:
    """'N1N2-M1n3' -> 'N1N2'. The config denominator is keyed off this prefix —
    a *different* part of the label than the group (which is keyed off the
    suffix) — do not conflate the two."""
    return raw_module.split("-")[0]


def _config_as_of(session, module_prefix: str, as_of: datetime) -> Optional[CarbonNestSorbentConfig]:
    """The config row in force at `as_of`: the latest one whose effective_date
    doesn't exceed it. Keeps historical weeks stable when a later reload adds a
    new row — never rewrites the past."""
    return (
        session.query(CarbonNestSorbentConfig)
        .filter(
            CarbonNestSorbentConfig.module_prefix == module_prefix,
            CarbonNestSorbentConfig.effective_date <= as_of,
        )
        .order_by(CarbonNestSorbentConfig.effective_date.desc())
        .first()
    )


def bed_volume_m3(session, raw_module: str, as_of: datetime) -> Optional[float]:
    cfg = _config_as_of(session, module_prefix_of(raw_module), as_of)
    return cfg.bed_volume_m3 if cfg else None


def sorbent_charge_kg(session, raw_module: str, as_of: datetime) -> Optional[float]:
    cfg = _config_as_of(session, module_prefix_of(raw_module), as_of)
    return cfg.sorbent_charge_kg if cfg else None


def des_vol_cap(session, cycle: CarbonNestCycleData) -> Optional[float]:
    """Per-cycle working capacity, mol CO2 / m3 of sorbent bed — the metric itself."""
    volume = bed_volume_m3(session, cycle.raw_module, cycle.start_time)
    if not volume or cycle.des_co2_kg is None:
        return None
    return (cycle.des_co2_kg / M_CO2_KG_PER_MOL) / volume


def is_valid_for_capacity(cycle: CarbonNestCycleData) -> bool:
    """DES-based validity filter — NOT ADS-based. A cycle can legitimately show
    zero adsorption (a bed loaded in an earlier cycle, still desorbing normally)
    and must be retained; an ADS-based filter would wrongly discard it."""
    return (cycle.des_co2_kg or 0) >= MIN_DES_CO2_KG_FOR_VALIDITY


def detect_config_anomaly(session, cycle: CarbonNestCycleData) -> Optional[dict]:
    """Flag a cycle whose own exported ADS capacity columns imply a bed volume
    that deviates from the versioned config by more than the tolerance —
    signals a commissioning-era override or a config-table gap for that cycle's
    module, without necessarily affecting its (separately-computed) working
    capacity — e.g. a cycle can have an anomalous ADS side and a perfectly
    normal DES side, and only the DES side feeds this metric."""
    if not cycle.ads_co2_kg or not cycle.ads_vol_cap:
        return None
    configured_volume = bed_volume_m3(session, cycle.raw_module, cycle.start_time)
    if not configured_volume:
        return None
    implied_volume = (cycle.ads_co2_kg / M_CO2_KG_PER_MOL) / cycle.ads_vol_cap
    deviation = abs(implied_volume - configured_volume) / configured_volume
    if deviation > CONFIG_ANOMALY_TOLERANCE:
        return {
            "cycle_number": cycle.cycle_number,
            "raw_module": cycle.raw_module,
            "configured_bed_volume_m3": configured_volume,
            "implied_bed_volume_m3": implied_volume,
            "deviation_pct": deviation * 100,
        }
    return None


def weekly_working_capacity(session, reference: datetime) -> dict:
    """Group A / Group B average sorbent working capacity (mol CO2/m3) for the
    Carbon Nest week containing `reference`."""
    week_start, week_end = get_carbon_nest_week_bounds(reference)
    cycles = (
        session.query(CarbonNestCycleData)
        .filter(
            CarbonNestCycleData.start_time >= week_start,
            CarbonNestCycleData.start_time < week_end,
        )
        .all()
    )

    groups = {}
    for g in ("A", "B"):
        in_window = [c for c in cycles if group_of(c.series) == g]
        valid = [c for c in in_window if is_valid_for_capacity(c)]
        excluded_ids = [c.cycle_number for c in in_window if c not in valid]
        caps = [v for v in (des_vol_cap(session, c) for c in valid) if v is not None]
        anomalies = [a for c in in_window if (a := detect_config_anomaly(session, c))]
        groups[g] = {
            "label": GROUP_LABELS[g],
            "avg_working_capacity_mol_per_m3": mean(caps) if caps else None,
            "n_cycles_in_window": len(in_window),
            "n_cycles_used": len(valid),
            "excluded_cycle_ids": excluded_ids,
            "config_anomalies": anomalies,
        }

    return {"week_start": week_start, "week_end": week_end, "groups": groups}
