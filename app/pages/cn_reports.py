import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st

from app.auth.authentication import require_login
from app.components.branding import get_brand_css, render_logo, render_hero_metric, render_stat_tile
from app.components.charts import co2_flow_chart, cumulative_chart
from app.components.sidebar import render_series_filter
from app.database.connection import get_session, init_db
from app.database.models import CarbonNestWeeklySummary
from app.pages.cn_dashboard import load_weekly_df
from app.services.carbon_nest_aggregation import aggregate_cycles_by_series
from app.services.carbon_nest_calculations import get_series_display_name
from app.services.export import weekly_summaries_to_excel
from app.services.pdf_report import generate_weekly_pdf_report


def main() -> None:
    st.set_page_config(page_title="Reports - Carbon Nest", page_icon="📈", layout="wide")
    init_db()
    if not require_login():
        return

    st.markdown(get_brand_css(), unsafe_allow_html=True)
    render_logo(location="sidebar")

    series_filter = render_series_filter()

    st.title("📈 Carbon Nest — Reports & Analysis")
    st.markdown("Trend analysis and export for Carbon Nest data")

    session = get_session()
    try:
        df = load_weekly_df(session, series_filter)
        series_agg = aggregate_cycles_by_series(session)
    finally:
        session.close()

    if df.empty:
        st.warning("No Carbon Nest data available yet. Import data and create weekly summaries first.")
        return

    st.markdown('<h2 class="section-header">📊 Overview Statistics</h2>', unsafe_allow_html=True)
    total_captured = df["collected_co2_kg"].sum()
    total_emissions = df["total_emissions_kg"].sum()
    total_net = df["net_removal_kg"].sum()
    weeks_positive = int(df["is_net_positive"].sum())
    total_weeks = len(df)
    hero_color = "#22C55E" if total_net > 0 else "#EF4444"

    hero_col, tile_col1, tile_col2, tile_col3 = st.columns([2, 1, 1, 1])
    with hero_col:
        st.markdown(
            render_hero_metric(
                "CUMULATIVE NET CO&#8322; REMOVAL",
                f"{total_net:+,.1f} kg",
                hero_color,
                f"Across {total_weeks} tracked week{'s' if total_weeks != 1 else ''} "
                f"&middot; {total_net/1000:+.2f} t",
            ),
            unsafe_allow_html=True,
        )
    with tile_col1:
        st.markdown(
            render_stat_tile("🎈", "green", "Total CO₂ Captured", f"{total_captured:,.1f} kg", f"{total_captured/1000:.2f} t"),
            unsafe_allow_html=True,
        )
    with tile_col2:
        st.markdown(
            render_stat_tile("⚡", "amber", "Total Emissions", f"{total_emissions:,.1f} kg", f"{total_emissions/1000:.2f} t"),
            unsafe_allow_html=True,
        )
    with tile_col3:
        st.markdown(
            render_stat_tile("✅", "blue", "Weeks Net Positive", f"{weeks_positive}/{total_weeks}"),
            unsafe_allow_html=True,
        )

    st.divider()

    tab1, tab2, tab3, tab4 = st.tabs(["📊 Cumulative Balance", "🔄 CO₂ Flow", "🧭 Series Comparison", "📤 Export"])

    with tab1:
        chart = cumulative_chart(df)
        if chart:
            st.plotly_chart(chart, width="stretch")
            st.caption("The gap between the captured and emissions lines is the running net-removal score — watch whether it's widening (net positive gaining ground) or narrowing.")

    with tab2:
        chart = co2_flow_chart(df)
        if chart:
            st.plotly_chart(chart, width="stretch")
            st.caption("Each line follows the same CO₂ through the process — Adsorbed should always sit on top; if Desorbed or Collected ever cross above it, that's a data problem, not a process one.")

    with tab3:
        st.markdown("#### Series 1&3 vs Series 2&4")
        s1 = series_agg["series_data"].get("1n3", {})
        s2 = series_agg["series_data"].get("2n4", {})
        comp_col1, comp_col2 = st.columns(2)
        with comp_col1:
            st.markdown(f"**{get_series_display_name('1n3')}**")
            st.metric("Cycles", s1.get("cycles", 0))
            st.metric("Collected CO₂", f"{s1.get('bag_co2_kg', 0):.1f} kg")
            st.metric("Overall Efficiency", f"{s1.get('overall_efficiency', 0):.1f}%")
        with comp_col2:
            st.markdown(f"**{get_series_display_name('2n4')}**")
            st.metric("Cycles", s2.get("cycles", 0))
            st.metric("Collected CO₂", f"{s2.get('bag_co2_kg', 0):.1f} kg")
            st.metric("Overall Efficiency", f"{s2.get('overall_efficiency', 0):.1f}%")

        st.divider()
        st.markdown("#### By Nelion (where SCADA can attribute it)")
        nelion_rows = [
            {"Nelion": key, "Cycles": val["cycles"], "Collected CO₂ (kg)": f"{val['bag_co2_kg']:.1f}"}
            for key, val in series_agg["nelion_data"].items()
        ]
        if nelion_rows:
            st.dataframe(nelion_rows, width="stretch", hide_index=True)
        st.caption(
            "Rows tagged 'Combined / unattributed' are interleaved cycles where SCADA "
            "currently reports Nelion 1 and 2 as one joint reading."
        )

    with tab4:
        pdf_col, excel_col = st.columns(2)

        with pdf_col:
            st.markdown("#### 📄 Weekly PDF Report")
            st.caption(
                "One week's Capture & Removal Efficiency, what drove it, and how it compares "
                "to recent weeks — a shareable, printable summary with the Octavia Carbon logo."
            )
            pdf_week_labels = [
                f"{r['start_date'].strftime('%b %d')} – {r['end_date'].strftime('%b %d, %Y')}"
                for _, r in df.iterrows()
            ]
            pdf_week_idx = st.selectbox(
                "Week to report on", options=list(range(len(pdf_week_labels))),
                format_func=lambda i: pdf_week_labels[i],
                index=len(pdf_week_labels) - 1, key="cn_pdf_week_select",
            )
            pdf_week_start = df.iloc[pdf_week_idx]["start_date"]

            if st.button("🖨️ Generate PDF Report", type="primary", width="stretch", key="cn_generate_pdf"):
                with st.spinner("Generating PDF report — rendering charts, this takes a few seconds…"):
                    session = get_session()
                    try:
                        st.session_state["cn_pdf_bytes"] = generate_weekly_pdf_report(session, pdf_week_start, series_filter)
                        st.session_state["cn_pdf_week_key"] = pdf_week_start
                    finally:
                        session.close()
                st.success("✅ Report ready — download below.")

            if st.session_state.get("cn_pdf_bytes") and st.session_state.get("cn_pdf_week_key") == pdf_week_start:
                st.download_button(
                    f"📥 Download PDF — {pdf_week_labels[pdf_week_idx]}",
                    data=st.session_state["cn_pdf_bytes"],
                    file_name=f"carbon_nest_weekly_report_{pdf_week_start.strftime('%Y%m%d')}.pdf",
                    mime="application/pdf",
                    width="stretch",
                    key="cn_download_pdf",
                )

        with excel_col:
            st.markdown("#### 📊 Full History (Excel)")
            st.caption("Every calculated week, one row each — for spreadsheet analysis or archival.")
            session = get_session()
            try:
                summaries = (
                    session.query(CarbonNestWeeklySummary)
                    .order_by(CarbonNestWeeklySummary.start_date)
                    .all()
                )
                excel_bytes = weekly_summaries_to_excel(summaries)
            finally:
                session.close()

            st.download_button(
                "📥 Download Weekly Summaries (Excel)",
                data=excel_bytes,
                file_name="carbon_nest_weekly_summaries.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                width="stretch",
            )


if __name__ == "__main__":
    main()
