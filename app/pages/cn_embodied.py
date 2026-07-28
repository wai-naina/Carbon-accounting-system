import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from app.auth.authentication import require_login
from app.components.branding import get_brand_css, render_hero_metric, render_logo, render_stat_tile
from app.components.charts import COLORS, apply_chart_layout, embodied_driver_chart, embodied_pool_split_chart
from app.database.connection import get_session, init_db
from app.database.models import CarbonNestWeeklySummary
from app.services.carbon_nest_embodied import (
    LCA_SOURCE_LABEL,
    get_driver_breakdown,
    get_infrastructure_intensity_kg_per_tonne,
    get_sorbent_intensity_kg_per_tonne,
)


def main() -> None:
    st.set_page_config(page_title="Embodied Emissions - Carbon Nest", page_icon="🏗️", layout="wide")
    init_db()
    if not require_login():
        return

    st.markdown(get_brand_css(), unsafe_allow_html=True)
    render_logo(location="sidebar")

    st.title("🏗️ Embodied Emissions — Carbon Nest")
    st.caption(f"Source: {LCA_SOURCE_LABEL}")

    st.markdown("""
    Carbon Nest embodied emissions are charged **per tonne of CO₂ actually captured**,
    not as a fixed weekly amount. Each driver below is a kg CO₂-eq/t intensity from the
    v0.6 life-cycle assessment; multiplying by the CO₂ captured in a given week gives that
    week's embodied charge. As more Nelions come online and cumulative capture grows, the
    same fixed one-time capital gets spread across more output — the embodied share
    naturally shrinks over the plant's life without any manual adjustment.
    """)

    drivers = get_driver_breakdown()
    infra_intensity = get_infrastructure_intensity_kg_per_tonne()
    sorbent_intensity = get_sorbent_intensity_kg_per_tonne()

    st.markdown("### Rate Card (kg CO₂-eq per tonne captured)")
    hero_col, tile_col1, tile_col2 = st.columns([2, 1, 1])
    with hero_col:
        st.markdown(render_hero_metric("COMBINED NON-ENERGY EMBODIED RATE", f"{infra_intensity + sorbent_intensity:.1f} kg/t", "#3DB3B3", "Charged per tonne of CO&#8322; actually captured — infrastructure + sorbent chain, energy excluded"), unsafe_allow_html=True)
    with tile_col1:
        st.markdown(render_stat_tile("🏗️", "purple", "Infrastructure", f"{infra_intensity:.1f} kg/t", "Structural + equipment + land use"), unsafe_allow_html=True)
    with tile_col2:
        st.markdown(render_stat_tile("🧪", "amber", "Sorbent Chain", f"{sorbent_intensity:.1f} kg/t", "Production + transport + processing"), unsafe_allow_html=True)

    st.divider()

    st.markdown("### Where the Embodied Rate Comes From")
    chart_col1, chart_col2 = st.columns([3, 2])
    with chart_col1:
        driver_chart = embodied_driver_chart(drivers)
        if driver_chart:
            st.plotly_chart(driver_chart, width="stretch")
            st.caption(
                "Longer bars are the LCA line items charged most per tonne captured. Energy is "
                "deliberately excluded here — real metered energy is charged separately, so "
                "combining both would double-count it."
            )

    with chart_col2:
        st.markdown("**Data quality by driver**")
        for d in sorted(drivers, key=lambda x: -x["kg_co2_per_tonne"]):
            if d["pool"] == "energy":
                continue
            badge_color = {
                "Measured": "#22C55E",
                "Mixed (datasheet + placeholder weights)": "#F59E0B",
                "Measured + Placeholder": "#F59E0B",
            }.get(d["data_quality"], "#94A3B8")
            st.markdown(f"""
            <div style="background:#1E293B;border:1px solid #334155;border-left:3px solid {badge_color};
                        border-radius:6px;padding:0.6rem 0.8rem;margin-bottom:0.5rem;">
                <div style="font-weight:600;color:#F1F5F9;font-size:0.85rem;">{d['label']}</div>
                <div style="color:{badge_color};font-size:0.72rem;text-transform:uppercase;letter-spacing:0.4px;">{d['data_quality']}</div>
                <div style="color:#94A3B8;font-size:0.78rem;margin-top:0.25rem;">{d['note']}</div>
            </div>
            """, unsafe_allow_html=True)

    st.info(
        "⚡ **Energy** (1,085.3 kg CO₂-eq/t in the LCA) is deliberately excluded from the "
        "embodied charge above — CAS computes operational emissions from actual metered "
        "Carbon Nest energy (Fans, CT, CT Pump, VP402, VP501, Boiler A/B, Main Utility) × grid EF "
        "instead, which is more accurate for a live plant than the LCA's modeled average. "
        "Charging both would double-count energy."
    )

    st.divider()

    st.markdown("### This Week's Realized Split")
    session = get_session()
    try:
        latest = (
            session.query(CarbonNestWeeklySummary)
            .order_by(CarbonNestWeeklySummary.start_date.desc())
            .first()
        )
        all_weeks = (
            session.query(CarbonNestWeeklySummary)
            .order_by(CarbonNestWeeklySummary.start_date)
            .all()
        )
    finally:
        session.close()

    if not latest:
        st.info("No Carbon Nest weekly summaries yet — this section fills in once a week is calculated in Data Entry.")
        return

    split_col1, split_col2 = st.columns([2, 3])
    with split_col1:
        donut = embodied_pool_split_chart(
            operational_kg=latest.total_operational_emissions_kg or 0,
            infrastructure_kg=latest.infrastructure_embodied_kg or 0,
            sorbent_kg=latest.sorbent_embodied_kg or 0,
        )
        if donut:
            st.plotly_chart(donut, width="stretch")
        st.caption(
            f"Week {latest.start_date.strftime('%Y-%m-%d %H:%M')} → {latest.end_date.strftime('%Y-%m-%d %H:%M')} "
            f"· {latest.gross_captured_kg or 0:.1f} kg captured"
        )

    with split_col2:
        if len(all_weeks) >= 2:
            df = pd.DataFrame([{
                "week_label": w.start_date.strftime("%Y-%m-%d"),
                "Operational": w.total_operational_emissions_kg or 0,
                "Infrastructure": w.infrastructure_embodied_kg or 0,
                "Sorbent chain": w.sorbent_embodied_kg or 0,
            } for w in all_weeks])

            fig = go.Figure()
            for name, color in [
                ("Operational", COLORS["thermal"]),
                ("Infrastructure", "#A855F7"),
                ("Sorbent chain", "#F59E0B"),
            ]:
                fig.add_trace(go.Bar(
                    name=name,
                    x=df["week_label"],
                    y=df[name],
                    marker_color=color,
                    marker_line_color="#1E293B",
                    marker_line_width=1,
                    hovertemplate=f"<b>%{{x}}</b><br>{name}: %{{y:,.1f}} kg<extra></extra>",
                ))
            apply_chart_layout(
                fig,
                title="📈 Emissions Composition Over Time",
                height=380,
                xaxis_title="Week",
                yaxis_title="kg CO₂-eq",
            )
            fig.update_layout(barmode="stack", legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
            st.plotly_chart(fig, width="stretch")
            st.caption(
                "Watch the Infrastructure + Sorbent chain share of the stack shrink over time as "
                "cumulative captured tonnes grow against the same fixed embodied capital."
            )
        else:
            st.info("Need at least 2 calculated weeks to show the trend over time.")


if __name__ == "__main__":
    main()
