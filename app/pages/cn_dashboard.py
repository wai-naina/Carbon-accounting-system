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
from app.components.sidebar import render_series_filter
from app.database.connection import get_session, init_db
from app.database.models import CarbonNestWeeklySummary
from app.services.carbon_nest_aggregation import get_grid_ef, get_weekly_metrics_by_series


def load_weekly_df(session, series_filter: str = None) -> pd.DataFrame:
    summaries = (
        session.query(CarbonNestWeeklySummary)
        .order_by(CarbonNestWeeklySummary.start_date)
        .all()
    )
    grid_ef = get_grid_ef(session)
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
            # (Main Utility's replacements, liquefaction) stays in total_energy_kwh
            # for operational emissions but is excluded here.
            process_energy = w.process_energy_kwh or 0
            total_cycles = w.total_cycles or 0
            thermal_energy = w.thermal_energy_kwh or 0
            auxiliary_energy = w.auxiliary_energy_kwh or 0

        collected_co2 = liq if liq > 0 else bag
        energy_intensity = (process_energy / (collected_co2 / 1000)) if (collected_co2 > 0 and process_energy > 0) else 0

        loss_stage_1 = ads - des
        loss_stage_2 = des - bag
        loss_stage_3 = (bag - liq) if liq > 0 else 0
        total_loss = ads - collected_co2

        # Embodied emissions are output-based (per tonne captured this week) — when
        # viewing a single series, allocate proportionally to that series' share of
        # BAG CO2 (the same basis get_weekly_metrics_by_series uses to prorate
        # shared energy, e.g. liquefaction) rather than a liquefied-vs-bag mix,
        # which would put the two series' shares on inconsistent bases.
        if series_filter:
            total_bag_all = w.total_bag_co2_kg or 0
            share = (bag / total_bag_all) if total_bag_all > 0 else 0
            infra_embodied = (w.infrastructure_embodied_kg or 0) * share
            sorbent_embodied = (w.sorbent_embodied_kg or 0) * share
        else:
            infra_embodied = w.infrastructure_embodied_kg or 0
            sorbent_embodied = w.sorbent_embodied_kg or 0
        embodied = infra_embodied + sorbent_embodied

        operational_emissions = total_energy * grid_ef
        if total_energy > 0:
            aux_share = min(max(auxiliary_energy / total_energy, 0.0), 1.0)
            thermal_share = 1.0 - aux_share
        else:
            aux_share = thermal_share = 0.0
        auxiliary_emissions = operational_emissions * aux_share
        thermal_emissions = operational_emissions * thermal_share
        total_emissions = operational_emissions + embodied
        net_removal = collected_co2 - total_emissions

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
            "total_cycles": total_cycles,
            "total_ads_co2_kg": ads,
            "total_des_co2_kg": des,
            "total_bag_co2_kg": bag,
            "collected_co2_kg": collected_co2,
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
            "liquefaction_energy_kwh": series_metrics.get("liquefaction_energy_kwh", 0) if series_filter else (w.liquefaction_energy_kwh or 0),
            "total_energy_kwh": total_energy,
            "is_net_positive": net_removal > 0,
        })
    return pd.DataFrame(rows)


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
        df = load_weekly_df(session, series_filter)
    finally:
        session.close()

    st.title("📊 Carbon Nest — Carbon Accounting Dashboard")
    st.caption("Output-based embodied emissions (v0.6 LCA) · fully separate from Miniplant 2.0 history")

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
        "total_bag_co2_kg", "liquefied_co2_kg", "total_loss_kg",
        "total_emissions_kg", "net_removal_kg", "is_net_positive",
    ]]
    display_df.columns = [
        "Week", "Cycles", "Adsorbed", "Desorbed", "Collected", "Liquefied",
        "Losses", "Emissions", "Net Removal", "Status",
    ]
    display_df["Status"] = display_df["Status"].apply(lambda x: "✅ Positive" if x else "❌ Negative")
    for col in ["Adsorbed", "Desorbed", "Collected", "Liquefied", "Losses", "Emissions", "Net Removal"]:
        display_df[col] = display_df[col].apply(lambda x: f"{x:.1f} kg")
    st.dataframe(display_df.sort_values("Week", ascending=False), width="stretch", hide_index=True)


if __name__ == "__main__":
    main()
