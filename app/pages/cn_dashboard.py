import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import streamlit as st

from app.auth.authentication import require_login
from app.components.branding import get_brand_css, render_logo, render_hero_metric, render_stat_tile
from app.components.charts import (
    cn_energy_breakdown_chart,
    cn_energy_intensity_chart,
    emissions_breakdown_pie,
    loss_analysis_chart,
    waterfall_chart,
)
from app.components.sidebar import render_energy_scenario, render_series_filter
from app.database.connection import get_session, init_db
from app.database.models import CarbonNestWeeklySummary
from app.services.carbon_nest_aggregation import get_grid_ef, get_weekly_metrics_by_series
from app.services.carbon_nest_embodied import calculate_embodied_kg


def _bucket(summary, column: str, fallback) -> float:
    """A Tier 2 bucket, falling back for weeks saved before the tiered model.

    Weeks saved on or after 2026-08-25 always have these populated (the
    aggregation service fills a missing meter from the tier below), but rows
    written before then hold NULL. Without a fallback those weeks would drop
    out of the energy-breakdown chart entirely rather than merely being
    coarser, which reads as "no energy used" instead of "not re-saved yet".
    """
    return (getattr(summary, column, None) or 0) or (fallback or 0)


def _legacy_skid(summary) -> float:
    """Utility-skid total reconstructed from the pre-tiered component columns."""
    return sum(
        getattr(summary, field, None) or 0
        for field in (
            "ct_kwh", "ct_pump_kwh", "vp402_kwh", "vp501_kwh",
            "vp402_standby_kwh", "vp501_standby_kwh", "ct_standby_kwh",
            "compressor_a_kwh", "compressor_b_kwh", "water_pumps_kwh", "air_dryer_kwh",
        )
    )


def load_weekly_df(session, series_filter: str = None, ef_override: float = None) -> pd.DataFrame:
    """Weekly Carbon Nest metrics, recomputed from stored energy and CO2 figures.

    `ef_override` (kg CO2e/kWh) swaps in a hypothetical grid emission factor for
    the "what if we ran this on a cleaner supply" view, instead of the saved
    carbon_nest_grid_emission_factor. It only affects what this function returns
    — no writes, no effect on the stored summaries — so callers that want
    actuals (Reports, the PDF export) simply omit it.
    """
    summaries = (
        session.query(CarbonNestWeeklySummary)
        .order_by(CarbonNestWeeklySummary.start_date)
        .all()
    )
    grid_ef = get_grid_ef(session) if ef_override is None else ef_override
    rows = []
    for w in summaries:
        # get_weekly_metrics_by_series() queries the cycle table for this
        # week — only worth that cost when a series filter is actually
        # active. In the default "All Series" view every field below already
        # came from `w.*` directly and this result was computed then
        # discarded, meaning a full per-series cycle query for every
        # historical week on every single Dashboard/Reports/PDF load, for
        # nothing.
        series_metrics = get_weekly_metrics_by_series(session, w.start_date, series_filter) if series_filter else None

        if series_filter and series_metrics["cycles"] == 0:
            continue

        if series_filter:
            ads = series_metrics["ads_co2_kg"]
            des = series_metrics["des_co2_kg"]
            bag = series_metrics["bag_co2_kg"]
            total_energy = series_metrics["total_kwh"]
            process_energy = series_metrics["process_kwh"]
            total_cycles = series_metrics["cycles"]
            thermal_energy = series_metrics["thermal_kwh"]
            auxiliary_energy = series_metrics["auxiliary_kwh"]
            steam_kg = series_metrics["steam_kg"]

            # Liquefaction is a single shared, plant-level downstream process —
            # it can't be honestly attributed back to one series. Prorating a
            # slice of the whole-plant liquefied figure here while dividing by
            # this series' own (unprorated) metered energy would systematically
            # inflate intensity whenever any bag->liquefied loss exists, which
            # is effectively always. Filtered views report on BAG (collected)
            # CO2 instead — the only quantity actually measured per series.
            liq = 0
        else:
            liq = w.liquefied_co2_kg or 0
            bag = w.total_bag_co2_kg or 0
            ads = w.total_ads_co2_kg or 0
            des = w.total_des_co2_kg or 0
            total_energy = w.total_energy_kwh or 0
            # process_energy_kwh is stored directly by create_or_update_weekly_summary
            # (CSV-metered Fans/CT/CT Pump/VP402/VP501/Boiler A/B only) — matches
            # SCADA's own eTotal/"MWh/tCO2" convention. Everything manually entered
            # (utility skid, standby, support infra, liquefaction) stays in total_energy_kwh
            # for operational emissions but is excluded here.
            process_energy = w.process_energy_kwh or 0
            total_cycles = w.total_cycles or 0
            thermal_energy = w.thermal_energy_kwh or 0
            auxiliary_energy = w.auxiliary_energy_kwh or 0
            steam_kg = w.total_steam_kg or 0

        # Which removal boundary this row reports. A series-filtered view can
        # only do "capture": liquefaction is a single shared downstream process
        # with no per-series liquefied figure (liq is forced to 0 above), so
        # there'd be nothing to divide by. Unfiltered views lead with the
        # liquefied boundary — the credit-bearing one — and carry capture
        # alongside. Read `boundary` before comparing net_removal_kg across
        # rows; the two boundaries are not interchangeable.
        boundary = "capture" if series_filter else "liquefied"

        # Plant-level figures are prorated to a series by its share of BAG CO2 —
        # the same basis get_weekly_metrics_by_series() uses, so the bucket stack
        # and the series' total energy stay consistent with each other.
        bucket_share = 1.0
        if series_filter:
            total_bag_all = w.total_bag_co2_kg or 0
            bucket_share = (bag / total_bag_all) if total_bag_all > 0 else 0.0

        liq_energy = (
            series_metrics["liquefaction_energy_kwh"] if series_filter
            else (w.liquefaction_energy_kwh or 0)
        )

        loss_stage_1 = ads - des
        loss_stage_2 = des - bag
        # CO2 vented during liquefaction. Reduces product; never charged as an
        # emission — it's atmospheric carbon returning to the atmosphere, a
        # failure to remove rather than a new release.
        loss_stage_3 = (bag - liq) if not series_filter else 0
        liquefaction_efficiency = (liq / bag * 100) if (bag > 0 and not series_filter) else None

        # Embodied is output-based, so it's recomputed per boundary from the LCA
        # intensities rather than read from storage: the stored figure is charged
        # on the liquefied mass, and the capture boundary needs it charged on the
        # bagged mass. Recomputing also keeps series views consistent — the
        # intensity is linear in tonnes, so a series' share is just its own BAG
        # mass, with no proration of a mixed liquefied-vs-bag basis.
        capture_embodied = calculate_embodied_kg(bag)
        liquefied_embodied = calculate_embodied_kg(liq)

        # --- Boundary B: liquefied (full site energy) ---
        operational_emissions = total_energy * grid_ef
        if total_energy > 0:
            aux_share = min(max(auxiliary_energy / total_energy, 0.0), 1.0)
            thermal_share = 1.0 - aux_share
        else:
            aux_share = thermal_share = 0.0
        auxiliary_emissions = operational_emissions * aux_share
        thermal_emissions = operational_emissions * thermal_share
        liq_total_emissions = operational_emissions + liquefied_embodied["total_embodied_emissions_kg"]
        liq_net_removal = liq - liq_total_emissions

        # --- Boundary A: capture (liquefaction out of both sides) ---
        capture_energy = max(total_energy - liq_energy, 0.0)
        capture_operational = capture_energy * grid_ef
        capture_total_emissions = capture_operational + capture_embodied["total_embodied_emissions_kg"]
        capture_net_removal = bag - capture_total_emissions

        if boundary == "capture":
            collected_co2 = bag
            embodied = capture_embodied["total_embodied_emissions_kg"]
            infra_embodied = capture_embodied["infrastructure_embodied_kg"]
            sorbent_embodied = capture_embodied["sorbent_embodied_kg"]
            total_emissions = capture_total_emissions
            net_removal = capture_net_removal
            operational_emissions = capture_operational
            auxiliary_emissions = capture_operational * aux_share
            thermal_emissions = capture_operational * thermal_share
        else:
            collected_co2 = liq
            embodied = liquefied_embodied["total_embodied_emissions_kg"]
            infra_embodied = liquefied_embodied["infrastructure_embodied_kg"]
            sorbent_embodied = liquefied_embodied["sorbent_embodied_kg"]
            total_emissions = liq_total_emissions
            net_removal = liq_net_removal

        total_loss = ads - collected_co2

        # Athena-comparable: process energy per tonne, reproducing the weekly
        # PDF's "BAG/LIQ MWh efficiency" exactly. Emissions are never charged on
        # this — see energy_intensity_site_kwh_per_tonne for the accounting basis.
        energy_intensity = (process_energy / (collected_co2 / 1000)) if (collected_co2 > 0 and process_energy > 0) else 0
        energy_intensity_site = (total_energy / (collected_co2 / 1000)) if collected_co2 > 0 else 0
        # Steam intensity mirrors the energy-intensity convention: same
        # denominator, so the two are directly comparable week to week.
        steam_intensity = (steam_kg / (collected_co2 / 1000)) if (collected_co2 > 0 and steam_kg > 0) else 0

        rows.append({
            "year": w.year,
            "week_number": w.week_number,
            "week_label": f"{w.start_date.strftime('%Y-%m-%d')} → {w.end_date.strftime('%m-%d')}",
            "start_date": w.start_date,
            "end_date": w.end_date,
            "net_removal_kg": net_removal,
            "liquefied_co2_kg": liq,
            "total_emissions_kg": total_emissions,
            "thermal_emissions_kg": thermal_emissions,
            "auxiliary_emissions_kg": auxiliary_emissions,
            "total_embodied_emissions_kg": embodied,
            "infrastructure_embodied_kg": infra_embodied,
            "sorbent_embodied_kg": sorbent_embodied,
            "total_operational_emissions_kg": operational_emissions,
            "energy_intensity_kwh_per_tonne": energy_intensity,
            "energy_intensity_site_kwh_per_tonne": energy_intensity_site,
            "total_cycles": total_cycles,
            "total_ads_co2_kg": ads,
            "total_des_co2_kg": des,
            "total_bag_co2_kg": bag,
            "collected_co2_kg": collected_co2,
            "boundary": boundary,
            "liquefaction_efficiency_pct": liquefaction_efficiency,
            # Both boundaries carried on every row so the two can be compared
            # side by side without reloading at a different filter.
            "capture_gross_kg": bag,
            "capture_energy_kwh": capture_energy,
            "capture_operational_emissions_kg": capture_operational,
            "capture_embodied_emissions_kg": capture_embodied["total_embodied_emissions_kg"],
            "capture_total_emissions_kg": capture_total_emissions,
            "capture_net_removal_kg": capture_net_removal,
            "liquefied_gross_kg": liq,
            "liquefied_total_emissions_kg": liq_total_emissions,
            "liquefied_net_removal_kg": liq_net_removal,
            "loss_stage_1_kg": loss_stage_1,
            "loss_stage_2_kg": loss_stage_2,
            "loss_stage_3_kg": loss_stage_3,
            "total_loss_kg": total_loss,
            "thermal_energy_kwh": thermal_energy,
            "auxiliary_energy_kwh": auxiliary_energy,
            "fans_kwh": series_metrics.get("fans_kwh", 0) if series_filter else (w.fans_kwh or 0),
            "ct_kwh": series_metrics.get("ct_kwh", 0) if series_filter else (w.ct_kwh or 0),
            "ct_pump_kwh": series_metrics.get("ct_pump_kwh", 0) if series_filter else (w.ct_pump_kwh or 0),
            "vp402_kwh": series_metrics.get("vp402_kwh", 0) if series_filter else (w.vp402_kwh or 0),
            "vp501_kwh": series_metrics.get("vp501_kwh", 0) if series_filter else (w.vp501_kwh or 0),
            "boiler_a_kwh": series_metrics.get("boiler_a_kwh", 0) if series_filter else (w.boiler_a_kwh or 0),
            "boiler_b_kwh": series_metrics.get("boiler_b_kwh", 0) if series_filter else (w.boiler_b_kwh or 0),
            "main_utility_kwh": series_metrics.get("main_utility_kwh", 0) if series_filter else (w.main_utility_kwh or 0),
            "liquefaction_energy_kwh": liq_energy,
            # Tier 2 buckets, for the energy-breakdown chart. Unfiltered these
            # six sum to the site meter exactly; series views carry each one
            # prorated by the same BAG share used for every other shared
            # quantity, so the stack still sums to that series' own total.
            "boilers_bucket_kwh": thermal_energy,
            "fans_total_kwh": _bucket(w, "fans_total_kwh", w.fans_kwh) * bucket_share,
            "utility_skid_kwh": _bucket(w, "utility_skid_kwh", _legacy_skid(w)) * bucket_share,
            "support_infra_kwh": (w.support_infra_kwh or 0) * bucket_share,
            "plant_residual_kwh": (w.plant_residual_kwh or 0) * bucket_share,
            "site_energy_kwh": (w.site_energy_kwh or 0) * bucket_share,
            "plant_energy_kwh": (w.plant_energy_kwh or 0) * bucket_share,
            "others_kwh": (w.others_kwh or 0) * bucket_share,
            "total_energy_kwh": total_energy,
            "total_steam_kg": steam_kg,
            "steam_intensity_kg_per_tonne": steam_intensity,
            "is_net_positive": net_removal > 0,
        })
    return pd.DataFrame(rows)


@st.cache_data(ttl=60)
def load_weekly_df_cached(_session, series_filter: str = None, ef_override: float = None) -> pd.DataFrame:
    """Cached wrapper around load_weekly_df() for read-only display pages
    (Dashboard, Reports, PDF export) — deliberately NOT used by Data Entry,
    which needs to see the result of its own imports/saves immediately, not
    up to 60s later. The leading underscore on `_session` tells Streamlit
    not to try hashing the SQLAlchemy session for the cache key; caching is
    keyed on series_filter and ef_override, which are what actually determine
    the result — so flipping between supply scenarios (or back to actuals)
    re-uses each frame rather than recomputing it every rerun.
    """
    return load_weekly_df(_session, series_filter, ef_override)


def removal_efficiency_pct(row) -> float:
    """Net removal as a share of gross captured — the Home-page headline figure.

    Recomputed from the row rather than read from storage so it follows whatever
    supply scenario the row was built at. Returns None when nothing was
    captured, since the ratio is undefined rather than 0%.
    """
    captured = row["collected_co2_kg"] or 0
    if captured <= 0:
        return None
    return row["net_removal_kg"] / captured * 100


def breakeven_ef_g_per_kwh(row) -> float:
    """Grid EF at which this week would exactly break even, in g CO2e/kWh.

    Embodied is charged per tonne captured and doesn't move with the EF, so the
    headroom left for energy is (captured - embodied). A negative result means
    embodied alone already exceeds what was captured — no supply, however clean,
    breaks that week even — and is returned as-is for the caller to flag.
    """
    energy = row["total_energy_kwh"] or 0
    if energy <= 0:
        return None
    headroom = (row["collected_co2_kg"] or 0) - (row["total_embodied_emissions_kg"] or 0)
    return headroom / energy * 1000


def breakeven_intensity_kwh_per_t(row, ef: float) -> float:
    """Total-energy intensity this week would need to break even at `ef`.

    Deliberately on the site-meter basis, because that's what operational
    emissions are charged on — unlike the energy_intensity_kwh_per_tonne KPI
    shown elsewhere on this page, which is process-only to match SCADA's
    convention. Compare it against actual_intensity_kwh_per_t(), never that KPI.
    """
    captured = row["collected_co2_kg"] or 0
    if captured <= 0 or ef <= 0:
        return None
    embodied_share = (row["total_embodied_emissions_kg"] or 0) / captured
    if embodied_share >= 1:
        return None
    return (1 - embodied_share) / ef * 1000


def actual_intensity_kwh_per_t(row) -> float:
    """This week's total-energy intensity — the like-for-like comparison for
    breakeven_intensity_kwh_per_t()."""
    captured = row["collected_co2_kg"] or 0
    if captured <= 0:
        return None
    return (row["total_energy_kwh"] or 0) / (captured / 1000)


def main() -> None:
    st.set_page_config(page_title="Dashboard - Carbon Nest", page_icon="📊", layout="wide")
    init_db()
    if not require_login():
        return

    st.markdown(get_brand_css(), unsafe_allow_html=True)
    render_logo(location="sidebar")

    series_filter = render_series_filter()

    session = get_session()
    try:
        configured_ef = get_grid_ef(session)
        scenario_ef, scenario_label, is_scenario = render_energy_scenario(configured_ef)
        df = load_weekly_df_cached(session, series_filter, scenario_ef)
        # Only pay for the second frame when a scenario is actually selected —
        # it exists purely to show "vs actuals" alongside the hypothetical.
        actual_df = load_weekly_df_cached(session, series_filter, configured_ef) if is_scenario else df
    finally:
        session.close()

    st.title("📊 Carbon Nest — Carbon Accounting Dashboard")
    st.caption("Output-based embodied emissions (v0.6 LCA) · fully separate from Miniplant 2.0 history")

    if is_scenario:
        st.markdown(f"""
        <div class="info-box warning">
            🔌 <strong>What-if supply: {scenario_label}</strong> (configured:
            {configured_ef * 1000:,.1f} g/kWh). Every emissions, net-removal and
            efficiency figure on this page is recomputed at that factor —
            <strong>these are not the reported actuals.</strong> Nothing is saved; the Home
            page, Reports and the PDF export continue to show the configured factor.
            Switch back to <em>As configured</em> in the sidebar to leave the scenario.
        </div>
        """, unsafe_allow_html=True)

    if df.empty:
        st.warning("⚠️ No weekly summaries yet.")
        st.info("""
        **To get started:**
        1. Go to **📥 Data Entry** and import the Carbon Nest CSV exports
        2. Enter the weekly liquefied CO₂ amount
        3. Click "Save & Calculate Weekly Summary"
        """)
        return

    st.markdown("### 📅 Select Week")
    week_options = [
        f"{row['start_date'].strftime('%b %d %H:%M')} → {row['end_date'].strftime('%b %d, %Y %H:%M')} "
        f"• {int(row['total_cycles']) if row['total_cycles'] is not None else 0} cycles"
        for _, row in df.iterrows()
    ]
    week_indices = list(range(len(week_options)))

    selected_idx = st.selectbox(
        "Choose a week to view:",
        options=week_indices,
        format_func=lambda x: week_options[x],
        index=len(week_options) - 1,
        key="cn_week_selector",
    )
    selected_week = df.iloc[selected_idx]

    is_positive = selected_week["net_removal_kg"] > 0
    hero_color = "#22C55E" if is_positive else "#EF4444"

    liq = selected_week["liquefied_co2_kg"]
    bag = selected_week["total_bag_co2_kg"]
    collected_co2 = liq if liq > 0 else bag
    collected_label = "Liquefied CO₂" if liq > 0 else "Collected CO₂"

    st.markdown('<h2 class="section-header">🎯 Key Performance Indicators</h2>', unsafe_allow_html=True)
    hero_col, tile_col1, tile_col2, tile_col3 = st.columns([2, 1, 1, 1])
    with hero_col:
        st.markdown(
            render_hero_metric(
                "NET CO&#8322; REMOVAL",
                f"{selected_week['net_removal_kg']:+,.1f} kg",
                hero_color,
                f"Week of {selected_week['start_date'].strftime('%b %d')} &ndash; "
                f"{selected_week['end_date'].strftime('%b %d, %Y')} &middot; "
                f"{'net positive' if is_positive else 'net negative'} — "
                f"{collected_label.lower()} minus operational + embodied emissions",
            ),
            unsafe_allow_html=True,
        )
    with tile_col1:
        st.markdown(
            render_stat_tile("❄️" if liq > 0 else "🎈", "teal", collected_label, f"{collected_co2:,.1f} kg"),
            unsafe_allow_html=True,
        )
    with tile_col2:
        st.markdown(
            render_stat_tile(
                "⚡", "amber", "Operational Emissions",
                f"{selected_week['total_operational_emissions_kg']:,.1f} kg",
            ),
            unsafe_allow_html=True,
        )
    with tile_col3:
        st.markdown(
            render_stat_tile(
                "🏗️", "purple", "Embodied Emissions",
                f"{selected_week['total_embodied_emissions_kg']:,.1f} kg",
                "Output-based: v0.6 LCA × tonnes captured",
            ),
            unsafe_allow_html=True,
        )

    st.divider()
    st.markdown('<h2 class="section-header">🔌 Removal Efficiency vs Energy Supply</h2>', unsafe_allow_html=True)
    st.caption(
        "Removal efficiency is net removal ÷ gross captured — the same headline the Home page "
        "leads with, recomputed here at whichever supply is selected in the sidebar. It answers "
        "how much of the gap to net-positive a cleaner grid actually closes, and how much is "
        "left for energy intensity and embodied to close."
    )

    week_eff = removal_efficiency_pct(selected_week)
    if week_eff is None:
        st.info("No CO₂ captured in the selected week — removal efficiency is undefined for it.")
    else:
        eff_color = "#22C55E" if week_eff > 0 else "#EF4444"
        # Efficiency at a zero-carbon supply: the best this week could ever do,
        # since output-based embodied is charged per tonne captured regardless of
        # how the plant is powered.
        embodied_share = (selected_week["total_embodied_emissions_kg"] or 0) / selected_week["collected_co2_kg"]
        ceiling_eff = (1 - embodied_share) * 100
        be_ef = breakeven_ef_g_per_kwh(selected_week)
        be_intensity = breakeven_intensity_kwh_per_t(selected_week, scenario_ef)
        actual_intensity = actual_intensity_kwh_per_t(selected_week)

        eff_hero, eff_t1, eff_t2, eff_t3 = st.columns([2, 1, 1, 1])
        with eff_hero:
            st.markdown(
                render_hero_metric(
                    "REMOVAL EFFICIENCY",
                    f"{week_eff:+.1f}%",
                    eff_color,
                    f"Week of {selected_week['start_date'].strftime('%b %d')} &middot; at "
                    f"{scenario_label}{' (what-if)' if is_scenario else ' (as configured)'}",
                ),
                unsafe_allow_html=True,
            )
        with eff_t1:
            if is_scenario:
                actual_week_eff = removal_efficiency_pct(actual_df.iloc[selected_idx])
                delta = week_eff - (actual_week_eff or 0)
                st.markdown(
                    render_stat_tile(
                        "📌", "teal", "As Configured",
                        f"{actual_week_eff:+.1f}%" if actual_week_eff is not None else "—",
                        f"{delta:+.1f} pp from this scenario",
                    ),
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    render_stat_tile(
                        "🧱", "purple", "Ceiling at 0 g/kWh", f"{ceiling_eff:+.1f}%",
                        "Embodied alone caps it here",
                    ),
                    unsafe_allow_html=True,
                )
        with eff_t2:
            st.markdown(
                render_stat_tile(
                    "⚖️", "amber", "Break-even EF",
                    f"{be_ef:,.1f} g/kWh" if be_ef is not None and be_ef >= 0 else "unreachable",
                    "Supply needed for 0% this week" if be_ef is not None and be_ef >= 0
                    else "Embodied exceeds capture",
                ),
                unsafe_allow_html=True,
            )
        with eff_t3:
            if scenario_ef <= 0:
                # At a zero-carbon supply energy costs nothing, so there's no
                # intensity threshold to hit — embodied is the only constraint.
                intensity_value, intensity_sub = "no limit", "Energy is free of CO₂ at 0 g/kWh"
            elif be_intensity is None:
                intensity_value, intensity_sub = "unreachable", "Embodied exceeds capture"
            else:
                intensity_value = f"{be_intensity:,.0f} kWh/t"
                intensity_sub = f"at {scenario_label} · actual {actual_intensity:,.0f} kWh/t"
            st.markdown(
                render_stat_tile("🔋", "blue", "Break-even Intensity", intensity_value, intensity_sub),
                unsafe_allow_html=True,
            )

        st.caption(
            f"Break-even intensity is on a **site-meter** basis, because that's what operational "
            f"emissions are charged on — so compare it with the {actual_intensity:,.0f} kWh/t "
            f"above, not with the process-only intensity chart further down. Embodied is fixed at "
            f"{embodied_share * 100:,.1f}% of captured this week and doesn't move with supply, so "
            f"{ceiling_eff:+.1f}% is the ceiling even on a zero-carbon grid."
        )

        # Both boundaries, side by side. Without this the headline reads as the
        # whole story, and on the liquefied boundary it is a very large negative
        # number — not because capture went badly but because the denominator is
        # only what survived liquefaction. Which of the two moved is the first
        # thing anyone asks, so answer it on the same screen.
        if selected_week.get("boundary") == "liquefied":
            cap_gross = selected_week["capture_gross_kg"] or 0
            liq_gross = selected_week["liquefied_gross_kg"] or 0
            if cap_gross > 0 and liq_gross > 0:
                cap_eff = (selected_week["capture_net_removal_kg"] or 0) / cap_gross * 100
                liq_eff_pct = (selected_week["liquefied_net_removal_kg"] or 0) / liq_gross * 100
                liq_recovery = selected_week["liquefaction_efficiency_pct"] or 0
                st.markdown("**Which boundary is the headline?**")
                st.dataframe(
                    [
                        {
                            "Boundary": "A · Capture — liquefaction excluded",
                            "Product": f"{cap_gross:,.1f} kg collected",
                            "Energy": f"{selected_week['capture_energy_kwh'] or 0:,.0f} kWh",
                            "Emitted": f"{selected_week['capture_total_emissions_kg'] or 0:,.1f} kg",
                            "Net": f"{selected_week['capture_net_removal_kg'] or 0:+,.1f} kg",
                            "Efficiency": f"{cap_eff:+,.1f}%",
                        },
                        {
                            "Boundary": "B · Liquefied — credit-bearing (headline above)",
                            "Product": f"{liq_gross:,.1f} kg liquefied",
                            "Energy": f"{selected_week['total_energy_kwh'] or 0:,.0f} kWh",
                            "Emitted": f"{selected_week['liquefied_total_emissions_kg'] or 0:,.1f} kg",
                            "Net": f"{selected_week['liquefied_net_removal_kg'] or 0:+,.1f} kg",
                            "Efficiency": f"{liq_eff_pct:+,.1f}%",
                        },
                    ],
                    width="stretch", hide_index=True,
                )
                st.caption(
                    f"The gap between these two is liquefaction recovery, not capture "
                    f"performance: {liq_recovery:.1f}% of the {cap_gross:,.1f} kg collected "
                    f"survived liquefaction, so boundary B charges almost the same energy "
                    f"against {liq_gross:,.1f} kg instead of {cap_gross:,.1f} kg — about "
                    f"{abs(liq_eff_pct / cap_eff):.1f}× the negative efficiency. Recovering "
                    f"more of what's already been captured moves the headline further than any "
                    f"change in supply: at 100% recovery this week would read "
                    f"{((cap_gross - (selected_week['capture_total_emissions_kg'] or 0)) / cap_gross * 100):+,.1f}%. "
                    f"The vented CO₂ is not charged as an emission — it's atmospheric carbon "
                    f"going back to the atmosphere, a failure to remove rather than a new release."
                )

        # Lifetime view: one clean week can't carry the programme figure, so show
        # what the scenario does to the cumulative number too.
        life_captured = df["collected_co2_kg"].sum()
        if life_captured > 0:
            life_eff = df["net_removal_kg"].sum() / life_captured * 100
            if is_scenario:
                life_eff_actual = actual_df["net_removal_kg"].sum() / life_captured * 100
                st.markdown(
                    f"**All weeks combined:** {life_captured:,.1f} kg captured — "
                    f"**{life_eff:+.1f}%** at {scenario_label}, versus **{life_eff_actual:+.1f}%** "
                    f"as configured ({life_eff - life_eff_actual:+.1f} pp)."
                )
            else:
                st.markdown(
                    f"**All weeks combined:** {life_captured:,.1f} kg captured — "
                    f"**{life_eff:+.1f}%** at the configured {scenario_label}."
                )

        if is_scenario:
            with st.expander("📋 Week-by-week — configured vs scenario", expanded=False):
                # to_numeric because the helpers return None for zero-capture or
                # zero-energy weeks, which would otherwise leave these columns as
                # object dtype and make the Change subtraction below raise.
                comp = pd.DataFrame({
                    "Week": df["week_label"],
                    "Captured": df["collected_co2_kg"],
                    "kWh/t": pd.to_numeric(df.apply(actual_intensity_kwh_per_t, axis=1), errors="coerce"),
                    "As configured": pd.to_numeric(actual_df.apply(removal_efficiency_pct, axis=1), errors="coerce"),
                    "Scenario": pd.to_numeric(df.apply(removal_efficiency_pct, axis=1), errors="coerce"),
                    "Break-even EF": pd.to_numeric(df.apply(breakeven_ef_g_per_kwh, axis=1), errors="coerce"),
                })
                comp["Change"] = comp["Scenario"] - comp["As configured"]
                comp["Captured"] = comp["Captured"].apply(lambda x: f"{x:,.1f} kg")
                comp["kWh/t"] = comp["kWh/t"].apply(lambda x: f"{x:,.0f}" if pd.notna(x) else "—")
                for col in ["As configured", "Scenario"]:
                    comp[col] = comp[col].apply(lambda x: f"{x:+.1f}%" if pd.notna(x) else "—")
                comp["Change"] = comp["Change"].apply(lambda x: f"{x:+.1f} pp" if pd.notna(x) else "—")
                comp["Break-even EF"] = comp["Break-even EF"].apply(
                    lambda x: f"{x:,.1f} g/kWh" if pd.notna(x) and x >= 0 else "unreachable"
                )
                st.dataframe(
                    comp.sort_values("Week", ascending=False), width="stretch", hide_index=True
                )
                st.caption(
                    "A week only flips positive once its break-even EF rises above the supply "
                    "factor you're testing — so weeks with a break-even below the scenario stay "
                    "net negative no matter how the grid is sourced."
                )

    st.divider()
    st.markdown("### 💧 Carbon Balance")
    chart = waterfall_chart(
        collected_co2,
        selected_week["total_operational_emissions_kg"],
        selected_week["total_embodied_emissions_kg"],
    )
    if chart:
        st.plotly_chart(chart, width="stretch")
        st.caption(
            "Reads left to right: what was captured, what it cost in operational and "
            "embodied emissions, and what's left over — the last bar answers whether this "
            "week removed more CO₂ than it emitted."
        )

    st.divider()
    st.markdown("### ⚡ Emissions & Energy Analysis")
    em_col1, em_col2 = st.columns(2)
    with em_col1:
        selected_df = pd.DataFrame([selected_week])
        pie = emissions_breakdown_pie(selected_df)
        if pie:
            st.plotly_chart(pie, width="stretch")
            st.caption(
                "Shows where this week's emissions actually came from. A large Embodied "
                "slice usually means captured tonnage is still low relative to the plant's "
                "fixed footprint — not that operations got worse."
            )
    with em_col2:
        energy_chart = cn_energy_breakdown_chart(df.tail(8))
        if energy_chart:
            st.plotly_chart(energy_chart, width="stretch")
            st.caption(
                "Boiler A/B energy use should track roughly with cycle count — a subsystem "
                "growing out of proportion to the others is worth a second look."
            )

    st.markdown("### 💨 Desorption Steam")
    steam_col1, steam_col2 = st.columns(2)
    with steam_col1:
        st.markdown(
            render_stat_tile(
                "💨", "blue", "Steam Used",
                f"{selected_week['total_steam_kg']:,.0f} kg",
                "Desorption steam, selected week",
            ),
            unsafe_allow_html=True,
        )
    with steam_col2:
        st.markdown(
            render_stat_tile(
                "🌡️", "amber", "Steam Intensity",
                f"{selected_week['steam_intensity_kg_per_tonne']:,.0f} kg/t CO₂"
                if selected_week["steam_intensity_kg_per_tonne"] else "—",
                "Steam per tonne captured — same denominator as energy intensity",
            ),
            unsafe_allow_html=True,
        )
    st.caption(
        "Steam is what releases the captured CO₂ from the sorbent bed during desorption — "
        "it's the main driver of Boiler A/B energy above."
    )

    st.markdown("### 📉 Loss Analysis")
    loss_col1, loss_col2 = st.columns(2)
    with loss_col1:
        loss_chart = loss_analysis_chart(df.tail(8))
        if loss_chart:
            st.plotly_chart(loss_chart, width="stretch")
            st.caption(
                "Each stage is CO₂ lost between capture and final output. A stage growing "
                "relative to the others points at a specific process step to investigate, "
                "not the plant as a whole."
            )
    with loss_col2:
        intensity_chart = cn_energy_intensity_chart(df.tail(8))
        if intensity_chart:
            st.plotly_chart(intensity_chart, width="stretch")
            st.caption(
                "Lower is better — this is energy spent per tonne actually captured, so it "
                "should trend down as utilization improves, regardless of how big or small "
                "a given week was."
            )

    st.divider()
    st.markdown("### 📋 Weekly Summary Table")
    display_df = df.tail(12).copy()
    display_df = display_df[[
        "week_label", "total_cycles", "total_ads_co2_kg", "total_des_co2_kg",
        "total_bag_co2_kg", "liquefied_co2_kg", "total_steam_kg", "total_loss_kg",
        "total_emissions_kg", "net_removal_kg", "is_net_positive",
    ]]
    display_df.columns = [
        "Week", "Cycles", "Adsorbed", "Desorbed", "Collected", "Liquefied",
        "Steam", "Losses", "Emissions", "Net Removal", "Status",
    ]
    display_df["Status"] = display_df["Status"].apply(lambda x: "✅ Positive" if x else "❌ Negative")
    for col in ["Adsorbed", "Desorbed", "Collected", "Liquefied", "Steam", "Losses", "Emissions", "Net Removal"]:
        display_df[col] = display_df[col].apply(lambda x: f"{x:.1f} kg")
    st.dataframe(display_df.sort_values("Week", ascending=False), width="stretch", hide_index=True)


if __name__ == "__main__":
    main()
