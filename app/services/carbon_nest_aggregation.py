from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import Optional, Tuple

import streamlit as st
from sqlalchemy import and_, func, or_

from app.database.models import CarbonNestCycleData, CarbonNestWeeklySummary, SystemConfig
from app.services.carbon_nest_calculations import calculate_weekly_metrics, safe_value

SATURDAY = 5  # date.weekday(): Monday=0 ... Saturday=5, Sunday=6
WEEK_BOUNDARY_HOUR = 18

# Which timestamp decides a cycle's week — the ONE place to change it.
#   "start"  a cycle counts toward the week it STARTED in. Matches Athena, whose
#            weekly PDF and Plant Cycles export both window by Start Time.
#   "end"    a cycle counts toward the week it COMPLETED in.
# See cycle_week_timestamp() for the evidence and for why we are on "start".
WEEK_ATTRIBUTION = "start"


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


def cycle_week_timestamp(cycle):
    """The timestamp that decides which Carbon Nest week a cycle belongs to.

    Governed by WEEK_ATTRIBUTION, currently **"start"**: a cycle counts toward
    the week it STARTED in. Either way a cycle is never split — there is no such
    thing as half a cycle, and every physical quantity on the row (CO2, kWh,
    steam) stays whole and attached to exactly one week. Both rules are clean
    partitions; all-time totals agree under either, only the boundary moves.

    **Why "start": it matches Athena, and the hand-entered figures come from
    Athena.** Verified against the week of 22-29 Aug 2026, where cycle #346 ran
    17:56 -> 19:36 on the 22nd:

        rule          cycles  desorbed   collected  ADS hrs  DES hrs
        Start Time        43   229.905     203.308    43.072   71.193   <- PDF
        End Time          44   235.540     208.837    44.091   72.857

    Every figure in the weekly PDF (229.9 / 203.3 / 43.07 / 71.19) matches the
    Start Time window exactly. Confirmed from the other side too: the 15-22 Aug
    PDF's 217 / 198.6 equals the End Time window's 211.344 / 193.060 **plus**
    #346, so Athena counted #346 in the earlier week. Nothing is lost by either
    rule — #346 is counted once in each system, just in a different week.

    The deciding argument is scope consistency, not correctness. Every energy and
    liquefaction figure in a weekly summary is transcribed by hand from the PDF,
    so it is scoped to the PDF's window. Pairing those with cycle masses from a
    different window would put numerator and denominator on different sets of
    cycles, quietly corrupting every intensity, MWh/tCO2 and steam-efficiency
    figure. Matching Athena keeps one window across the whole summary.

    History: bnjenga ruled for the completion rule on 2026-08-10, before it was
    known that the PDF windows by Start Time; that finding (2026-08-31) and the
    manual-entry scope argument reversed it the same day. If Athena ever moves to
    completion-based weeks, set WEEK_ATTRIBUTION = "end" and recalculate the
    affected weeks — no other code changes.

    Under "end", falls back to Start Time when End Time is missing (a truncated
    or in-progress export row), since there is nothing better to key off.
    """
    if WEEK_ATTRIBUTION == "start":
        return cycle.start_time
    return cycle.end_time or cycle.start_time


def week_timestamp_column():
    """cycle_week_timestamp() as a SQL expression, for ORDER BY and comparisons.

    Kept beside its Python twin so "which week is this cycle in" can never mean
    two different things depending on whether the question is asked in the
    database or in memory.
    """
    if WEEK_ATTRIBUTION == "start":
        return CarbonNestCycleData.start_time
    return func.coalesce(CarbonNestCycleData.end_time, CarbonNestCycleData.start_time)


def in_week_window(start_dt: datetime, end_dt: datetime):
    """SQL predicate for "this cycle belongs to the week [start_dt, end_dt)".

    Mirrors cycle_week_timestamp() in the database, honouring WEEK_ATTRIBUTION.
    Was named completed_in_window() while the completion rule was the only one.
    """
    if WEEK_ATTRIBUTION == "start":
        return and_(
            CarbonNestCycleData.start_time >= start_dt,
            CarbonNestCycleData.start_time < end_dt,
        )
    return or_(
        and_(
            CarbonNestCycleData.end_time.isnot(None),
            CarbonNestCycleData.end_time >= start_dt,
            CarbonNestCycleData.end_time < end_dt,
        ),
        and_(
            CarbonNestCycleData.end_time.is_(None),
            CarbonNestCycleData.start_time >= start_dt,
            CarbonNestCycleData.start_time < end_dt,
        ),
    )


def get_filtered_cycles(
    session, start_dt: datetime, end_dt: datetime, series_filter: Optional[str] = None
) -> list:
    """Every cycle belonging to the week [start_dt, end_dt), optionally one series."""
    query = session.query(CarbonNestCycleData).filter(in_week_window(start_dt, end_dt))
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


@st.cache_data(ttl=60)
def get_grid_ef_cached(_session) -> float:
    """Cached wrapper for read-only display pages. Deliberately NOT used
    inside create_or_update_weekly_summary() (the Data Entry save path) —
    a weekly save should always bake in the live, current emission factor,
    never a possibly-up-to-60s-stale cached one, since that value gets
    permanently persisted into the stored weekly summary."""
    return get_grid_ef(_session)


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
    # --- Tier 1: trusted physical meters (drive all emissions) -------------
    site_energy_kwh: float = 0.0,
    plant_energy_kwh: float = 0.0,
    # --- Tier 2: the utility skid parent meter -----------------------------
    utility_skid_kwh: float = 0.0,
    # --- Tier 3: components, all transcribed verbatim from the weekly PDF --
    fan_n1_m1n2_kwh: float = 0.0,
    fan_n1_m3n4_kwh: float = 0.0,
    fan_n2_m1_kwh: float = 0.0,
    fan_n2_m2_kwh: float = 0.0,
    fan_n2_m3_kwh: float = 0.0,
    fan_n2_m4_kwh: float = 0.0,
    water_pumps_kwh: float = 0.0,
    compressor_a_kwh: float = 0.0,
    compressor_b_kwh: float = 0.0,
    air_dryer_kwh: float = 0.0,
    boiler_a_standby_kwh: float = 0.0,
    boiler_b_standby_kwh: float = 0.0,
    vp402_standby_kwh: float = 0.0,
    vp501_standby_kwh: float = 0.0,
    ct_ct_pump_total_kwh: float = 0.0,
    liquefaction_active_transfer_kwh: float = 0.0,
    liquefaction_standby_kwh: float = 0.0,
    notes: Optional[str],
    created_by: Optional[int],
) -> CarbonNestWeeklySummary:
    """Recompute and persist one Carbon Nest week.

    Energy is modelled in three tiers (see CarbonNestWeeklySummary for the
    column-level notes):

      Tier 1  site_energy_kwh / plant_energy_kwh — physical meters. Operational
              emissions are charged on the site meter and nothing else.
      Tier 2  boilers / liquefaction / fans / utility skid / support infra —
              what the plant meter decomposes into. Used for attribution and
              for the reconciliation residual, never to form the total.
      Tier 3  individual components. Diagnostics only.

    Anchoring the total on a meter rather than a sum of parts is the point:
    unnamed load (others_kwh — 43% of the skid as of 2026-08-22) is already
    inside the plant meter, so it can neither escape the total nor distort it.
    We get a correct total now and improve the labelling later.

    Every caller-supplied figure here is a number printed verbatim on the
    Athena weekly PDF. Each residual — support infra, fan standby, CT standby,
    others, plant instrument error — is derived, so nobody hand-subtracts
    anything. When a meter isn't supplied it degrades cleanly: the tier below
    is summed in its place and that tier's residual comes out at zero.
    """
    week_start, week_end = get_carbon_nest_week_bounds(week_start)

    # Cycles belonging to this week — see cycle_week_timestamp(). One cycle
    # belongs to exactly one week, whole, so the count, the FK back-reference and
    # every summed quantity below all agree on the same set of rows.
    cycles = get_filtered_cycles(session, week_start, week_end)

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
    air_dryer_kwh = safe_value(air_dryer_kwh)
    boiler_a_standby_kwh = safe_value(boiler_a_standby_kwh)
    boiler_b_standby_kwh = safe_value(boiler_b_standby_kwh)
    vp402_standby_kwh = safe_value(vp402_standby_kwh)
    vp501_standby_kwh = safe_value(vp501_standby_kwh)
    liquefaction_active_transfer_kwh = safe_value(liquefaction_active_transfer_kwh)
    liquefaction_standby_kwh = safe_value(liquefaction_standby_kwh)
    liquefaction_energy_kwh = liquefaction_active_transfer_kwh + liquefaction_standby_kwh

    # --- Fans: six per-fan PDF readings, standby derived against the CSV ----
    fan_readings = [
        safe_value(fan_n1_m1n2_kwh), safe_value(fan_n1_m3n4_kwh),
        safe_value(fan_n2_m1_kwh), safe_value(fan_n2_m2_kwh),
        safe_value(fan_n2_m3_kwh), safe_value(fan_n2_m4_kwh),
    ]
    fans_metered = sum(fan_readings)
    fans_total_kwh = fans_metered if fans_metered > 0 else energy["fans_kwh"]
    fan_standby_kwh = fans_total_kwh - energy["fans_kwh"]

    # --- CT & CT Pump: PDF gives one total, no process/standby split --------
    ct_in_cycle_kwh = energy["ct_kwh"] + energy["ct_pump_kwh"]
    ct_ct_pump_total_kwh = safe_value(ct_ct_pump_total_kwh) or ct_in_cycle_kwh
    ct_standby_kwh = ct_ct_pump_total_kwh - ct_in_cycle_kwh

    # --- Utility skid: parent meter, "others" as the derived residual -------
    vp402_total_kwh = energy["vp402_kwh"] + vp402_standby_kwh
    vp501_total_kwh = energy["vp501_kwh"] + vp501_standby_kwh
    skid_children_kwh = (
        vp402_total_kwh + vp501_total_kwh + ct_ct_pump_total_kwh
        + compressor_a_kwh + compressor_b_kwh + water_pumps_kwh + air_dryer_kwh
    )
    utility_skid_kwh = safe_value(utility_skid_kwh) or skid_children_kwh
    others_kwh = utility_skid_kwh - skid_children_kwh

    # --- Tier 2 buckets, and the Tier 1 meters they reconcile against -------
    boilers_kwh = energy["thermal_kwh"] + boiler_a_standby_kwh + boiler_b_standby_kwh
    buckets_kwh = boilers_kwh + liquefaction_energy_kwh + fans_total_kwh + utility_skid_kwh

    # A meter, when given, always wins over the sum of its parts. Falling back
    # to the tier below keeps a partially-filled week computable and drives
    # that tier's residual to exactly zero, so a blank meter can never be
    # mistaken for a reconciled one.
    plant_energy_kwh = safe_value(plant_energy_kwh) or buckets_kwh
    site_energy_kwh = safe_value(site_energy_kwh) or plant_energy_kwh
    support_infra_kwh = site_energy_kwh - plant_energy_kwh
    plant_residual_kwh = plant_energy_kwh - buckets_kwh

    # Operational emissions are charged on the site meter. Boilers are electric
    # (confirmed 2026-08-25), so a single grid factor covers the whole site and
    # thermal + auxiliary partition it exactly: auxiliary is defined as the
    # residual rather than re-summed, so the two can never drift from the total.
    total_kwh = site_energy_kwh
    thermal_kwh = boilers_kwh
    auxiliary_kwh = total_kwh - thermal_kwh

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
        liquefaction_energy_kwh=liquefaction_energy_kwh,
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
    # Tier 1 — meters
    summary.site_energy_kwh = site_energy_kwh
    summary.plant_energy_kwh = plant_energy_kwh
    summary.support_infra_kwh = support_infra_kwh
    # Tier 2 — buckets and the reconciliation residual
    summary.utility_skid_kwh = utility_skid_kwh
    summary.fans_total_kwh = fans_total_kwh
    summary.plant_residual_kwh = plant_residual_kwh
    # Tier 3 — components
    summary.fan_n1_m1n2_kwh = fan_readings[0]
    summary.fan_n1_m3n4_kwh = fan_readings[1]
    summary.fan_n2_m1_kwh = fan_readings[2]
    summary.fan_n2_m2_kwh = fan_readings[3]
    summary.fan_n2_m3_kwh = fan_readings[4]
    summary.fan_n2_m4_kwh = fan_readings[5]
    summary.fan_standby_kwh = fan_standby_kwh
    summary.water_pumps_kwh = water_pumps_kwh
    summary.compressor_a_kwh = compressor_a_kwh
    summary.compressor_b_kwh = compressor_b_kwh
    summary.air_dryer_kwh = air_dryer_kwh
    summary.boiler_a_standby_kwh = boiler_a_standby_kwh
    summary.boiler_b_standby_kwh = boiler_b_standby_kwh
    summary.vp402_standby_kwh = vp402_standby_kwh
    summary.vp501_standby_kwh = vp501_standby_kwh
    summary.ct_ct_pump_total_kwh = ct_ct_pump_total_kwh
    summary.ct_standby_kwh = ct_standby_kwh
    summary.others_kwh = others_kwh
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
    summary.liquefaction_efficiency_pct = metrics["liquefaction_efficiency_pct"]

    summary.thermal_emissions_kg = metrics["thermal_emissions_kg"]
    summary.auxiliary_emissions_kg = metrics["auxiliary_emissions_kg"]
    summary.total_operational_emissions_kg = metrics["total_operational_emissions_kg"]
    summary.infrastructure_embodied_kg = metrics["infrastructure_embodied_kg"]
    summary.sorbent_embodied_kg = metrics["sorbent_embodied_kg"]
    summary.total_embodied_emissions_kg = metrics["total_embodied_emissions_kg"]
    # Boundary B — liquefied, credit-bearing
    summary.gross_captured_kg = metrics["gross_captured_kg"]
    summary.total_emissions_kg = metrics["total_emissions_kg"]
    summary.net_removal_kg = metrics["net_removal_kg"]
    summary.is_net_positive = metrics["is_net_positive"]
    summary.energy_intensity_kwh_per_tonne = metrics["energy_intensity_kwh_per_tonne"]
    # Boundary A — capture, liquefaction excluded from both product and energy
    summary.capture_gross_kg = metrics["capture_gross_kg"]
    summary.capture_operational_emissions_kg = metrics["capture_operational_emissions_kg"]
    summary.capture_embodied_emissions_kg = metrics["capture_embodied_emissions_kg"]
    summary.capture_total_emissions_kg = metrics["capture_total_emissions_kg"]
    summary.capture_net_removal_kg = metrics["capture_net_removal_kg"]
    summary.capture_energy_kwh = metrics["capture_energy_kwh"]
    summary.capture_energy_intensity_kwh_per_tonne = metrics[
        "capture_energy_intensity_kwh_per_tonne"
    ]

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

    # Athena reports every non-per-cycle energy figure at plant level, with no
    # series breakdown, so anything from the weekly summary is prorated to this
    # series by its share of BAG CO2 — the same basis used for every other
    # shared/downstream quantity here. One share factor for all of them, so the
    # prorated parts can't drift apart from each other.
    share = 1.0
    if series_filter:
        all_cycles = get_filtered_cycles(session, week_start, week_end, None)
        total_bag_all = sum(safe_value(c.bag_co2_kg) for c in all_cycles)
        share = (bag_co2 / total_bag_all) if (total_bag_all > 0 and bag_co2 > 0) else 0.0

    # Everything on the site meter the per-cycle CSV doesn't account for:
    # standby, the utility skid (including its unidentified residual), support
    # infrastructure and liquefaction. Taken as a residual against the metered
    # total rather than re-summed from named components, so load we haven't
    # identified yet still reaches the series views instead of vanishing.
    non_cycle_kwh = 0.0
    boiler_standby_kwh = 0.0
    liquefaction_energy_kwh = 0.0
    if weekly_summary:
        non_cycle_kwh = share * max(
            safe_value(weekly_summary.total_energy_kwh)
            - safe_value(weekly_summary.process_energy_kwh),
            0.0,
        )
        boiler_standby_kwh = share * (
            safe_value(weekly_summary.boiler_a_standby_kwh)
            + safe_value(weekly_summary.boiler_b_standby_kwh)
        )
        liquefaction_energy_kwh = share * safe_value(weekly_summary.liquefaction_energy_kwh)

    # Boiler standby is thermal, so it's moved across rather than left in the
    # auxiliary residual — that keeps this split matching the one stored by
    # create_or_update_weekly_summary(). liquefaction_energy_kwh is already
    # inside non_cycle_kwh and is returned separately only for the energy
    # breakdown charts; adding it again here would double-count it.
    thermal_kwh = energy["thermal_kwh"] + boiler_standby_kwh
    total_kwh = process_kwh + non_cycle_kwh
    auxiliary_kwh = total_kwh - thermal_kwh

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
        "non_cycle_kwh": non_cycle_kwh,
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
    """Aggregate cycle data by series (1n3 vs 2n4), and by Nelion where known.

    Uses the module's attribution rule like every other aggregate here — see
    cycle_week_timestamp(). This used to filter Start Time inline, which happened
    to agree with today's rule but hardcoded it, so the same database answered
    the same question two ways whenever the rule changed. Bounds are inclusive
    calendar dates (end_date covers its whole day) and either may be omitted for
    an open-ended range.
    """
    lower = datetime.combine(start_date, time(0, 0)) if start_date else datetime.min
    upper = datetime.combine(end_date + timedelta(days=1), time(0, 0)) if end_date else datetime.max
    cycles = session.query(CarbonNestCycleData).filter(in_week_window(lower, upper)).all()

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


@st.cache_data(ttl=60)
def aggregate_cycles_by_series_cached(_session, start_date=None, end_date=None) -> dict:
    """Cached wrapper for the Reports page's Series Comparison tab."""
    return aggregate_cycles_by_series(_session, start_date, end_date)
