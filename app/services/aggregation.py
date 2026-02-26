from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional, Tuple

from sqlalchemy import and_

from app.database.models import CycleData, SystemConfig, WeeklySummary
from app.services.calculations import (
    calculate_weekly_metrics,
    classify_module_pair,
    safe_value,
)
from app.services.embodied_config import get_weekly_embodied_kg


def get_week_dates(year: int, week_number: int) -> Tuple[date, date]:
    week_start = date.fromisocalendar(year, week_number, 1)
    week_end = week_start + timedelta(days=6)
    return week_start, week_end


def get_module_filter() -> Optional[str]:
    """Get the current Module pair filter from session state."""
    try:
        import streamlit as st
        filter_val = st.session_state.get("module_pair_filter", "all")
        return None if filter_val == "all" else filter_val
    except Exception:
        return None


def filter_cycles_by_pair(cycles: list, pair_filter: Optional[str]) -> list:
    """Filter a list of CycleData objects by Module pair."""
    if not pair_filter:
        return cycles
    
    return [c for c in cycles if classify_module_pair(c.machine) == pair_filter]


def get_filtered_cycles(session, start_dt: datetime, end_dt: datetime, pair_filter: Optional[str] = None) -> list:
    """Get cycles for a date range, optionally filtered by Module pair."""
    cycles = (
        session.query(CycleData)
        .filter(and_(CycleData.start_time >= start_dt, CycleData.start_time < end_dt))
        .all()
    )
    
    return filter_cycles_by_pair(cycles, pair_filter)


def _get_config_value(session, key: str, default: float) -> float:
    config = session.query(SystemConfig).filter(SystemConfig.key == key).first()
    if not config:
        return default
    try:
        return float(config.value)
    except ValueError:
        return default


def _get_weekly_embodied(_session=None) -> Tuple[float, float]:
    """Return (infra_weekly, sorbent_weekly) from fixed embodied formula.
    Session arg kept for backwards compatibility but unused."""
    total = get_weekly_embodied_kg()
    return total, 0.0  # All embodied allocated to infra for compatibility


def create_or_update_weekly_summary(
    session,
    *,
    year: int,
    week_number: int,
    liquefied_co2_kg: float,
    liquefaction_energy_kwh: float = 0.0,
    notes: Optional[str],
    created_by: Optional[int],
) -> WeeklySummary:
    week_start, week_end = get_week_dates(year, week_number)
    start_dt = datetime.combine(week_start, datetime.min.time())
    end_dt = datetime.combine(week_end + timedelta(days=1), datetime.min.time())

    cycles = (
        session.query(CycleData)
        .filter(and_(CycleData.start_time >= start_dt, CycleData.start_time < end_dt))
        .all()
    )

    ads_co2 = sum(safe_value(c.ads_co2_kg) for c in cycles)
    des_co2 = sum(safe_value(c.des_co2_kg) for c in cycles)
    bag_co2 = sum(safe_value(c.bag_co2_kg) for c in cycles)
    boiler_kwh = sum(safe_value(c.boiler_kwh) for c in cycles)

    # Base auxiliary energy from SCADA (fans, pumps, etc.)
    auxiliary_kwh_base = sum(
        safe_value(c.srv_lrvp_kwh)
        + safe_value(c.ct_kwh)
        + safe_value(c.nm1_fan_kwh)
        + safe_value(c.nm2_fan_kwh)
        + safe_value(c.nm3_fan_kwh)
        + safe_value(c.nm4_fan_kwh)
        for c in cycles
    )

    # Base total energy from SCADA
    total_kwh_base = sum(safe_value(c.total_kwh) for c in cycles)
    
    # If we have total_kwh but no breakdown (boiler/auxiliary are 0 or missing),
    # estimate the split using typical ratios: 70% thermal (boiler), 30% auxiliary
    if total_kwh_base > 0 and (boiler_kwh == 0 and auxiliary_kwh_base == 0):
        # SCADA provided total but no component breakdown - estimate split
        boiler_kwh = total_kwh_base * 0.70  # Typical: 70% thermal
        auxiliary_kwh_base = total_kwh_base * 0.30  # Typical: 30% auxiliary
    elif total_kwh_base == 0:
        # Fallback: use sum of components if total is missing
        total_kwh_base = boiler_kwh + auxiliary_kwh_base

    # Liquefaction energy is plant-level downstream energy.
    # Treat it as auxiliary energy and add it on top of SCADA auxiliary.
    liquefaction_energy_kwh = safe_value(liquefaction_energy_kwh)
    auxiliary_kwh = auxiliary_kwh_base + liquefaction_energy_kwh
    total_kwh = total_kwh_base + liquefaction_energy_kwh
    steam_kg = sum(safe_value(c.steam_kg) for c in cycles)

    grid_ef = _get_config_value(session, "grid_emission_factor", 0.049)
    infra_weekly, sorbent_weekly = _get_weekly_embodied(session)

    metrics = calculate_weekly_metrics(
        ads_co2_kg=ads_co2,
        des_co2_kg=des_co2,
        bag_co2_kg=bag_co2,
        liquefied_co2_kg=liquefied_co2_kg,
        thermal_energy_kwh=boiler_kwh,
        auxiliary_energy_kwh=auxiliary_kwh,
        total_energy_kwh=total_kwh,
        steam_kg=steam_kg,
        grid_ef=grid_ef,
        infrastructure_embodied_kg=infra_weekly,
        sorbent_embodied_kg=sorbent_weekly,
    )

    summary = (
        session.query(WeeklySummary)
        .filter(
            WeeklySummary.year == year,
            WeeklySummary.week_number == week_number,
        )
        .first()
    )

    if not summary:
        summary = WeeklySummary(
            year=year,
            week_number=week_number,
            start_date=week_start,
            end_date=week_end,
            created_by=created_by,
        )
        session.add(summary)

    summary.start_date = week_start
    summary.end_date = week_end
    summary.total_ads_co2_kg = ads_co2
    summary.total_des_co2_kg = des_co2
    summary.total_bag_co2_kg = bag_co2
    summary.liquefied_co2_kg = liquefied_co2_kg
    summary.liquefaction_energy_kwh = liquefaction_energy_kwh
    summary.thermal_energy_kwh = boiler_kwh
    summary.auxiliary_energy_kwh = auxiliary_kwh
    summary.total_energy_kwh = total_kwh
    summary.total_steam_kg = steam_kg
    summary.total_cycles = len(cycles)
    summary.notes = notes

    summary.loss_stage_1_kg = metrics["loss_stage_1_kg"]
    summary.loss_stage_2_kg = metrics["loss_stage_2_kg"]
    summary.loss_stage_3_kg = metrics["loss_stage_3_kg"]
    summary.total_loss_kg = metrics["total_loss_kg"]

    summary.thermal_emissions_kg = metrics["thermal_emissions_kg"]
    summary.auxiliary_emissions_kg = metrics["auxiliary_emissions_kg"]
    summary.total_operational_emissions_kg = metrics["total_operational_emissions_kg"]
    summary.infrastructure_embodied_kg = metrics["infrastructure_embodied_kg"]
    summary.sorbent_embodied_kg = metrics["sorbent_embodied_kg"]
    summary.total_embodied_emissions_kg = metrics["total_embodied_emissions_kg"]
    summary.gross_captured_kg = metrics["gross_captured_kg"]
    summary.total_emissions_kg = metrics["total_emissions_kg"]
    summary.net_removal_kg = metrics["net_removal_kg"]
    summary.is_net_positive = metrics["is_net_positive"]
    summary.energy_intensity_kwh_per_tonne = metrics["energy_intensity_kwh_per_tonne"]

    session.commit()

    for cycle in cycles:
        cycle.weekly_summary_id = summary.id
    session.commit()

    return summary


def get_weekly_metrics_by_pair(
    session,
    year: int,
    week_number: int,
    pair_filter: Optional[str] = None,
) -> dict:
    """
    Calculate metrics for a specific week, optionally filtered by Module pair.
    Returns aggregated CO2, energy, and derived metrics.
    """
    week_start, week_end = get_week_dates(year, week_number)
    start_dt = datetime.combine(week_start, datetime.min.time())
    end_dt = datetime.combine(week_end + timedelta(days=1), datetime.min.time())
    
    cycles = get_filtered_cycles(session, start_dt, end_dt, pair_filter)
    
    ads_co2 = sum(safe_value(c.ads_co2_kg) for c in cycles)
    des_co2 = sum(safe_value(c.des_co2_kg) for c in cycles)
    bag_co2 = sum(safe_value(c.bag_co2_kg) for c in cycles)
    boiler_kwh = sum(safe_value(c.boiler_kwh) for c in cycles)

    # Breakdown of auxiliary energy by component
    srv_lrvp_kwh = sum(safe_value(c.srv_lrvp_kwh) for c in cycles)
    ct_kwh = sum(safe_value(c.ct_kwh) for c in cycles)
    fans_kwh = sum(
        safe_value(c.nm1_fan_kwh)
        + safe_value(c.nm2_fan_kwh)
        + safe_value(c.nm3_fan_kwh)
        + safe_value(c.nm4_fan_kwh)
        for c in cycles
    )
    auxiliary_kwh_base = srv_lrvp_kwh + ct_kwh + fans_kwh
    total_kwh_base = sum(safe_value(c.total_kwh) for c in cycles)
    if total_kwh_base == 0:
        total_kwh_base = boiler_kwh + auxiliary_kwh_base

    # Proportionally allocate plant-level liquefaction energy to this pair (or full for unfiltered)
    liquefaction_energy_kwh = 0.0
    weekly_summary = (
        session.query(WeeklySummary)
        .filter(
            WeeklySummary.year == year,
            WeeklySummary.week_number == week_number,
        )
        .first()
    )
    if weekly_summary and weekly_summary.liquefaction_energy_kwh:
        if pair_filter:
            # Total BAG CO2 from all Modules this week (no filter)
            all_cycles = get_filtered_cycles(session, start_dt, end_dt, None)
            total_bag_all = sum(safe_value(c.bag_co2_kg) for c in all_cycles)
            if total_bag_all > 0 and bag_co2 > 0:
                bag_ratio = bag_co2 / total_bag_all
                liquefaction_energy_kwh = safe_value(
                    weekly_summary.liquefaction_energy_kwh
                ) * bag_ratio
        else:
            liquefaction_energy_kwh = safe_value(weekly_summary.liquefaction_energy_kwh)

    auxiliary_kwh = auxiliary_kwh_base + liquefaction_energy_kwh
    total_kwh = total_kwh_base + liquefaction_energy_kwh
    steam_kg = sum(safe_value(c.steam_kg) for c in cycles)
    
    return {
        "cycles": len(cycles),
        "ads_co2_kg": ads_co2,
        "des_co2_kg": des_co2,
        "bag_co2_kg": bag_co2,
        "boiler_kwh": boiler_kwh,
        "auxiliary_kwh": auxiliary_kwh,
        "total_kwh": total_kwh,
        "steam_kg": steam_kg,
        "liquefaction_energy_kwh": liquefaction_energy_kwh,
        "srv_lrvp_kwh": srv_lrvp_kwh,
        "ct_kwh": ct_kwh,
        "fans_kwh": fans_kwh,
    }


def aggregate_cycles_by_pair(
    session,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> dict:
    """
    Aggregate cycle data by Module pair (1n3 vs 2n4).
    
    Returns a dictionary with:
    - pair_data: dict keyed by pair name with aggregated metrics
    - cycles_by_pair: count of cycles per pair
    - comparison: efficiency and performance comparisons
    """
    query = session.query(CycleData)
    
    if start_date:
        query = query.filter(CycleData.start_time >= datetime.combine(start_date, datetime.min.time()))
    if end_date:
        query = query.filter(CycleData.start_time < datetime.combine(end_date + timedelta(days=1), datetime.min.time()))
    
    cycles = query.all()
    
    pair_data = {
        "1n3": {
            "cycles": 0,
            "ads_co2_kg": 0.0,
            "des_co2_kg": 0.0,
            "bag_co2_kg": 0.0,
            "total_kwh": 0.0,
            "boiler_kwh": 0.0,
            "steam_kg": 0.0,
        },
        "2n4": {
            "cycles": 0,
            "ads_co2_kg": 0.0,
            "des_co2_kg": 0.0,
            "bag_co2_kg": 0.0,
            "total_kwh": 0.0,
            "boiler_kwh": 0.0,
            "steam_kg": 0.0,
        },
        "unknown": {
            "cycles": 0,
            "ads_co2_kg": 0.0,
            "des_co2_kg": 0.0,
            "bag_co2_kg": 0.0,
            "total_kwh": 0.0,
            "boiler_kwh": 0.0,
            "steam_kg": 0.0,
        },
    }
    
    for cycle in cycles:
        pair = classify_module_pair(cycle.machine) or "unknown"
        
        pair_data[pair]["cycles"] += 1
        pair_data[pair]["ads_co2_kg"] += safe_value(cycle.ads_co2_kg)
        pair_data[pair]["des_co2_kg"] += safe_value(cycle.des_co2_kg)
        pair_data[pair]["bag_co2_kg"] += safe_value(cycle.bag_co2_kg)
        pair_data[pair]["total_kwh"] += safe_value(cycle.total_kwh)
        pair_data[pair]["boiler_kwh"] += safe_value(cycle.boiler_kwh)
        pair_data[pair]["steam_kg"] += safe_value(cycle.steam_kg)
    
    # Calculate derived metrics for each pair
    for pair_name, data in pair_data.items():
        ads = data["ads_co2_kg"]
        des = data["des_co2_kg"]
        bag = data["bag_co2_kg"]
        
        # Efficiency metrics
        data["ads_to_des_efficiency"] = (des / ads * 100) if ads > 0 else 0
        data["des_to_bag_efficiency"] = (bag / des * 100) if des > 0 else 0
        data["overall_efficiency"] = (bag / ads * 100) if ads > 0 else 0
        
        # Loss calculations
        data["loss_stage_1"] = ads - des
        data["loss_stage_2"] = des - bag
        data["total_loss"] = ads - bag
        data["loss_rate"] = ((ads - bag) / ads * 100) if ads > 0 else 0
        
        # Energy per kg CO2
        data["kwh_per_kg_co2"] = (data["total_kwh"] / bag) if bag > 0 else 0
        
        # Average per cycle
        if data["cycles"] > 0:
            data["avg_ads_per_cycle"] = ads / data["cycles"]
            data["avg_bag_per_cycle"] = bag / data["cycles"]
            data["avg_kwh_per_cycle"] = data["total_kwh"] / data["cycles"]
        else:
            data["avg_ads_per_cycle"] = 0
            data["avg_bag_per_cycle"] = 0
            data["avg_kwh_per_cycle"] = 0
    
    # Comparison between pairs
    p1 = pair_data["1n3"]
    p2 = pair_data["2n4"]
    
    comparison = {
        "better_efficiency_pair": "1n3" if p1["overall_efficiency"] > p2["overall_efficiency"] else "2n4",
        "efficiency_difference": abs(p1["overall_efficiency"] - p2["overall_efficiency"]),
        "1n3_vs_2n4_efficiency_ratio": (p1["overall_efficiency"] / p2["overall_efficiency"]) if p2["overall_efficiency"] > 0 else None,
        "1n3_co2_contribution": (p1["bag_co2_kg"] / (p1["bag_co2_kg"] + p2["bag_co2_kg"]) * 100) if (p1["bag_co2_kg"] + p2["bag_co2_kg"]) > 0 else 0,
        "2n4_co2_contribution": (p2["bag_co2_kg"] / (p1["bag_co2_kg"] + p2["bag_co2_kg"]) * 100) if (p1["bag_co2_kg"] + p2["bag_co2_kg"]) > 0 else 0,
    }
    
    return {
        "pair_data": pair_data,
        "comparison": comparison,
        "total_cycles": sum(d["cycles"] for d in pair_data.values()),
    }
