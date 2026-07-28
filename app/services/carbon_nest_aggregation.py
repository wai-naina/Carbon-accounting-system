from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import Optional, Tuple

from sqlalchemy import and_

from app.database.models import CarbonNestCycleData, CarbonNestWeeklySummary, SystemConfig
from app.services.carbon_nest_calculations import calculate_weekly_metrics, safe_value

SATURDAY = 5  # date.weekday(): Monday=0 ... Saturday=5, Sunday=6
WEEK_BOUNDARY_HOUR = 18


def get_carbon_nest_week_bounds(reference) -> Tuple[datetime, datetime]:
    """Return (week_start, week_end) as Saturday-18:00 datetimes enclosing `reference`.

    Carbon Nest weeks run Saturday 18:00 -> the following Saturday 18:00,
    matching Athena's own weekly report cadence (e.g. the week of the 18th
    18:00 to the 25th 18:00). Miniplant 2.0 keeps its Mon-based ISO week,
    untouched. `reference` may be a date or datetime; bare dates are treated
    as midnight for boundary purposes.
    """
    if isinstance(reference, datetime):
        ref_dt = reference
    else:
        ref_dt = datetime.combine(reference, time(0, 0))

    days_since_saturday = (ref_dt.date().weekday() - SATURDAY) % 7
    week_start = datetime.combine(ref_dt.date() - timedelta(days=days_since_saturday), time(WEEK_BOUNDARY_HOUR, 0))

    if ref_dt < week_start:
        week_start -= timedelta(days=7)

    week_end = week_start + timedelta(days=7)
    return week_start, week_end


def list_week_options(count_back: int = 12, count_forward: int = 1, anchor=None) -> list:
    """Recent/upcoming Saturday-anchored (start, end) windows, most recent first."""
    if anchor is None:
        anchor = datetime.now()
    current_start, _ = get_carbon_nest_week_bounds(anchor)
    return [
        (current_start + timedelta(days=7 * i), current_start + timedelta(days=7 * i) + timedelta(days=7))
        for i in range(count_forward, -count_back - 1, -1)
    ]


def get_series_filter() -> Optional[str]:
    """Get the current series filter (1n3/2n4) from session state."""
    try:
        import streamlit as st

        filter_val = st.session_state.get("cn_series_filter", "all")
        return None if filter_val == "all" else filter_val
    except Exception:
        return None


def get_filtered_cycles(session, start_dt: datetime, end_dt: datetime, series_filter: Optional[str] = None) -> list:
    query = session.query(CarbonNestCycleData).filter(
        and_(CarbonNestCycleData.start_time >= start_dt, CarbonNestCycleData.start_time < end_dt)
    )
    if series_filter:
        query = query.filter(CarbonNestCycleData.series == series_filter)
    return query.all()


def _get_config_value(session, key: str, default: float) -> float:
    config = session.query(SystemConfig).filter(SystemConfig.key == key).first()
    if not config:
        return default
    try:
        return float(config.value)
    except ValueError:
        return default


def get_grid_ef(session) -> float:
    """Carbon Nest's own grid emission factor (kg CO2/kWh) — deliberately
    separate from Miniplant 2.0's grid_emission_factor config key, since
    Miniplant is a frozen historical archive and shouldn't shift when this
    is updated (0.0579 as of 2026-07-29, up from the prior 0.055 figure)."""
    return _get_config_value(session, "carbon_nest_grid_emission_factor", 0.0579)


def _sum_energy(cycles) -> dict:
    fans = sum(safe_value(c.fans_kwh) for c in cycles)
    ct = sum(safe_value(c.ct_kwh) for c in cycles)
    ct_pump = sum(safe_value(c.ct_pump_kwh) for c in cycles)
    vp402 = sum(safe_value(c.vp402_kwh) for c in cycles)
    vp501 = sum(safe_value(c.vp501_kwh) for c in cycles)
    boiler_a = sum(safe_value(c.boiler_a_kwh) for c in cycles)
    boiler_b = sum(safe_value(c.boiler_b_kwh) for c in cycles)
    main_utility = sum(safe_value(c.main_utility_kwh) for c in cycles)
    thermal = boiler_a + boiler_b
    # "Process" energy = Fans + CT + CT Pump + VP402 + VP501 + Boiler A/B.
    # Verified against the real Carbon Nest export: this sum equals the
    # per-cycle "eTotal kWh" field exactly (0 discrepancies across the full
    # dataset), and eTotal is what SCADA's own "MWh/tCO2" column is computed
    # from. main_utility_kwh is imported/kept for reference only — Octavia's
    # SCADA lead confirmed (2026-07-28) it's a known-buggy/incomplete stand-in
    # for cooling tower/pump/compressor draw, so it's excluded from every
    # total below. The real utility + standby figures are entered manually
    # each week from the Athena weekly PDF report instead (see
    # create_or_update_weekly_summary).
    process = fans + ct + ct_pump + vp402 + vp501 + thermal
    return {
        "fans_kwh": fans,
        "ct_kwh": ct,
        "ct_pump_kwh": ct_pump,
        "vp402_kwh": vp402,
        "vp501_kwh": vp501,
        "boiler_a_kwh": boiler_a,
        "boiler_b_kwh": boiler_b,
        "main_utility_kwh": main_utility,
        "thermal_kwh": thermal,
        "process_kwh": process,
    }


def create_or_update_weekly_summary(
    session,
    *,
    week_start: datetime,
    liquefied_co2_kg: float,
    water_pumps_kwh: float = 0.0,
    compressor_a_kwh: float = 0.0,
    compressor_b_kwh: float = 0.0,
    boiler_a_standby_kwh: float = 0.0,
    boiler_b_standby_kwh: float = 0.0,
    vp402_standby_kwh: float = 0.0,
    vp501_standby_kwh: float = 0.0,
    ct_standby_kwh: float = 0.0,
    liquefaction_active_transfer_kwh: float = 0.0,
    liquefaction_standby_kwh: float = 0.0,
    notes: Optional[str],
    created_by: Optional[int],
) -> CarbonNestWeeklySummary:
    week_start, week_end = get_carbon_nest_week_bounds(week_start)

    cycles = (
        session.query(CarbonNestCycleData)
        .filter(and_(CarbonNestCycleData.start_time >= week_start, CarbonNestCycleData.start_time < week_end))
        .all()
    )

    ads_co2 = sum(safe_value(c.ads_co2_kg) for c in cycles)
    des_co2 = sum(safe_value(c.des_co2_kg) for c in cycles)
    bag_co2 = sum(safe_value(c.bag_co2_kg) for c in cycles)
    steam_kg = sum(safe_value(c.steam_kg) for c in cycles)

    energy = _sum_energy(cycles)

    # total_kwh_metered is SCADA's own per-cycle eTotal, summed — verified to
    # equal energy["process_kwh"] exactly on real data; kept as the preferred
    # source with the components sum as a fallback if it's ever missing/zero.
    total_kwh_metered = sum(safe_value(c.total_kwh) for c in cycles)
    process_kwh = max(total_kwh_metered, energy["process_kwh"])

    water_pumps_kwh = safe_value(water_pumps_kwh)
    compressor_a_kwh = safe_value(compressor_a_kwh)
    compressor_b_kwh = safe_value(compressor_b_kwh)
    boiler_a_standby_kwh = safe_value(boiler_a_standby_kwh)
    boiler_b_standby_kwh = safe_value(boiler_b_standby_kwh)
    vp402_standby_kwh = safe_value(vp402_standby_kwh)
    vp501_standby_kwh = safe_value(vp501_standby_kwh)
    ct_standby_kwh = safe_value(ct_standby_kwh)
    liquefaction_active_transfer_kwh = safe_value(liquefaction_active_transfer_kwh)
    liquefaction_standby_kwh = safe_value(liquefaction_standby_kwh)
    liquefaction_energy_kwh = liquefaction_active_transfer_kwh + liquefaction_standby_kwh

    thermal_kwh = energy["thermal_kwh"] + boiler_a_standby_kwh + boiler_b_standby_kwh
    auxiliary_kwh = (
        (process_kwh - energy["thermal_kwh"])  # process-side fans/ct/ct_pump/vp402/vp501
        + vp402_standby_kwh
        + vp501_standby_kwh
        + ct_standby_kwh
        + water_pumps_kwh
        + compressor_a_kwh
        + compressor_b_kwh
        + liquefaction_energy_kwh
    )
    total_kwh = thermal_kwh + auxiliary_kwh

    grid_ef = get_grid_ef(session)

    metrics = calculate_weekly_metrics(
        ads_co2_kg=ads_co2,
        des_co2_kg=des_co2,
        bag_co2_kg=bag_co2,
        liquefied_co2_kg=liquefied_co2_kg,
        thermal_energy_kwh=thermal_kwh,
        auxiliary_energy_kwh=auxiliary_kwh,
        total_energy_kwh=total_kwh,
        process_energy_kwh=process_kwh,
        steam_kg=steam_kg,
        grid_ef=grid_ef,
    )

    summary = (
        session.query(CarbonNestWeeklySummary)
        .filter(CarbonNestWeeklySummary.start_date == week_start)
        .first()
    )

    if not summary:
        summary = CarbonNestWeeklySummary(
            year=week_start.year,
            week_number=week_start.isocalendar().week,
            start_date=week_start,
            end_date=week_end,
            created_by=created_by,
        )
        session.add(summary)

    summary.year = week_start.year
    summary.week_number = week_start.isocalendar().week
    summary.start_date = week_start
    summary.end_date = week_end
    summary.total_ads_co2_kg = ads_co2
    summary.total_des_co2_kg = des_co2
    summary.total_bag_co2_kg = bag_co2
    summary.liquefied_co2_kg = liquefied_co2_kg
    summary.fans_kwh = energy["fans_kwh"]
    summary.ct_kwh = energy["ct_kwh"]
    summary.ct_pump_kwh = energy["ct_pump_kwh"]
    summary.vp402_kwh = energy["vp402_kwh"]
    summary.vp501_kwh = energy["vp501_kwh"]
    summary.boiler_a_kwh = energy["boiler_a_kwh"]
    summary.boiler_b_kwh = energy["boiler_b_kwh"]
    summary.main_utility_kwh = energy["main_utility_kwh"]
    summary.water_pumps_kwh = water_pumps_kwh
    summary.compressor_a_kwh = compressor_a_kwh
    summary.compressor_b_kwh = compressor_b_kwh
    summary.boiler_a_standby_kwh = boiler_a_standby_kwh
    summary.boiler_b_standby_kwh = boiler_b_standby_kwh
    summary.vp402_standby_kwh = vp402_standby_kwh
    summary.vp501_standby_kwh = vp501_standby_kwh
    summary.ct_standby_kwh = ct_standby_kwh
    summary.liquefaction_active_transfer_kwh = liquefaction_active_transfer_kwh
    summary.liquefaction_standby_kwh = liquefaction_standby_kwh
    summary.liquefaction_energy_kwh = liquefaction_energy_kwh
    summary.thermal_energy_kwh = thermal_kwh
    summary.auxiliary_energy_kwh = auxiliary_kwh
    summary.total_energy_kwh = total_kwh
    summary.process_energy_kwh = process_kwh
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


def get_weekly_metrics_by_series(
    session,
    week_start: datetime,
    series_filter: Optional[str] = None,
) -> dict:
    """Calculate metrics for a specific week, optionally filtered by series (1n3/2n4)."""
    week_start, week_end = get_carbon_nest_week_bounds(week_start)

    cycles = get_filtered_cycles(session, week_start, week_end, series_filter)

    ads_co2 = sum(safe_value(c.ads_co2_kg) for c in cycles)
    des_co2 = sum(safe_value(c.des_co2_kg) for c in cycles)
    bag_co2 = sum(safe_value(c.bag_co2_kg) for c in cycles)
    steam_kg = sum(safe_value(c.steam_kg) for c in cycles)

    energy = _sum_energy(cycles)
    total_kwh_metered = sum(safe_value(c.total_kwh) for c in cycles)
    process_kwh = max(total_kwh_metered, energy["process_kwh"])

    weekly_summary = (
        session.query(CarbonNestWeeklySummary)
        .filter(CarbonNestWeeklySummary.start_date == week_start)
        .first()
    )

    # The manually-entered utility/standby/liquefaction figures are plant-level
    # (Athena's weekly report doesn't break them out by series) — prorate them
    # to this series by its share of BAG CO2 this week, same basis used
    # everywhere else for shared/downstream quantities.
    manual_total = 0.0
    if weekly_summary:
        manual_total = sum(
            safe_value(getattr(weekly_summary, field))
            for field in (
                "water_pumps_kwh",
                "compressor_a_kwh",
                "compressor_b_kwh",
                "boiler_a_standby_kwh",
                "boiler_b_standby_kwh",
                "vp402_standby_kwh",
                "vp501_standby_kwh",
                "ct_standby_kwh",
                "liquefaction_active_transfer_kwh",
                "liquefaction_standby_kwh",
            )
        )

    manual_share_kwh = 0.0
    if manual_total and series_filter:
        all_cycles = get_filtered_cycles(session, week_start, week_end, None)
        total_bag_all = sum(safe_value(c.bag_co2_kg) for c in all_cycles)
        if total_bag_all > 0 and bag_co2 > 0:
            manual_share_kwh = manual_total * (bag_co2 / total_bag_all)
    elif manual_total:
        manual_share_kwh = manual_total

    liquefaction_energy_kwh = 0.0
    if weekly_summary and weekly_summary.liquefaction_energy_kwh:
        if series_filter:
            all_cycles = get_filtered_cycles(session, week_start, week_end, None)
            total_bag_all = sum(safe_value(c.bag_co2_kg) for c in all_cycles)
            if total_bag_all > 0 and bag_co2 > 0:
                bag_ratio = bag_co2 / total_bag_all
                liquefaction_energy_kwh = safe_value(weekly_summary.liquefaction_energy_kwh) * bag_ratio
        else:
            liquefaction_energy_kwh = safe_value(weekly_summary.liquefaction_energy_kwh)

    thermal_kwh = energy["thermal_kwh"]
    auxiliary_kwh = (process_kwh - thermal_kwh) + manual_share_kwh
    total_kwh = process_kwh + manual_share_kwh

    return {
        "cycles": len(cycles),
        "ads_co2_kg": ads_co2,
        "des_co2_kg": des_co2,
        "bag_co2_kg": bag_co2,
        "thermal_kwh": thermal_kwh,
        "auxiliary_kwh": auxiliary_kwh,
        "total_kwh": total_kwh,
        "process_kwh": process_kwh,
        "steam_kg": steam_kg,
        "liquefaction_energy_kwh": liquefaction_energy_kwh,
        "manual_utility_kwh": manual_share_kwh,
        "fans_kwh": energy["fans_kwh"],
        "ct_kwh": energy["ct_kwh"],
        "ct_pump_kwh": energy["ct_pump_kwh"],
        "vp402_kwh": energy["vp402_kwh"],
        "vp501_kwh": energy["vp501_kwh"],
        "boiler_a_kwh": energy["boiler_a_kwh"],
        "boiler_b_kwh": energy["boiler_b_kwh"],
        "main_utility_kwh": energy["main_utility_kwh"],
    }


def aggregate_cycles_by_series(session, start_date=None, end_date=None) -> dict:
    """Aggregate cycle data by series (1n3 vs 2n4), and by Nelion where known."""
    query = session.query(CarbonNestCycleData)
    if start_date:
        query = query.filter(CarbonNestCycleData.start_time >= datetime.combine(start_date, time(0, 0)))
    if end_date:
        query = query.filter(
            CarbonNestCycleData.start_time < datetime.combine(end_date + timedelta(days=1), time(0, 0))
        )
    cycles = query.all()

    def _blank():
        return {"cycles": 0, "ads_co2_kg": 0.0, "des_co2_kg": 0.0, "bag_co2_kg": 0.0, "total_kwh": 0.0}

    series_data = {"1n3": _blank(), "2n4": _blank(), "unknown": _blank()}
    nelion_data: dict = {}

    for cycle in cycles:
        series = cycle.series if cycle.series in series_data else "unknown"
        series_data[series]["cycles"] += 1
        series_data[series]["ads_co2_kg"] += safe_value(cycle.ads_co2_kg)
        series_data[series]["des_co2_kg"] += safe_value(cycle.des_co2_kg)
        series_data[series]["bag_co2_kg"] += safe_value(cycle.bag_co2_kg)
        series_data[series]["total_kwh"] += safe_value(cycle.total_kwh)

        nelion_key = cycle.nelion or "Combined / unattributed"
        if nelion_key not in nelion_data:
            nelion_data[nelion_key] = _blank()
        nelion_data[nelion_key]["cycles"] += 1
        nelion_data[nelion_key]["ads_co2_kg"] += safe_value(cycle.ads_co2_kg)
        nelion_data[nelion_key]["des_co2_kg"] += safe_value(cycle.des_co2_kg)
        nelion_data[nelion_key]["bag_co2_kg"] += safe_value(cycle.bag_co2_kg)
        nelion_data[nelion_key]["total_kwh"] += safe_value(cycle.total_kwh)

    for data in series_data.values():
        ads = data["ads_co2_kg"]
        bag = data["bag_co2_kg"]
        data["overall_efficiency"] = (bag / ads * 100) if ads > 0 else 0
        data["kwh_per_kg_co2"] = (data["total_kwh"] / bag) if bag > 0 else 0

    return {
        "series_data": series_data,
        "nelion_data": nelion_data,
        "total_cycles": len(cycles),
    }
