import sys
from pathlib import Path
import uuid
from datetime import datetime

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import streamlit as st

from app.auth.authorization import require_admin
from app.components.branding import get_brand_css, render_logo
from app.database.connection import get_session, init_db
from app.database.models import CarbonNestWeeklySummary, CarbonNestCycleData
from app.services.carbon_nest_aggregation import create_or_update_weekly_summary, list_week_options
from app.services.carbon_nest_calculations import get_series_display_name, safe_value
from app.services.carbon_nest_import import (
    import_cycles,
    load_cycle_energy,
    load_plant_cycles,
    merge_plant_cycles_energy,
)


def format_week_option(bounds: tuple) -> str:
    start, end = bounds
    return f"{start.strftime('%b %d %H:%M')} → {end.strftime('%b %d %H:%M, %Y')}"


def main() -> None:
    st.set_page_config(page_title="Data Entry - Carbon Nest", page_icon="📥", layout="wide")
    init_db()
    if not require_admin():
        return

    st.markdown(get_brand_css(), unsafe_allow_html=True)
    render_logo(location="sidebar")

    st.title("📥 Carbon Nest — Data Entry")
    st.markdown("Import Carbon Nest cycle & energy exports and enter weekly liquefied CO₂ measurements")
    st.caption(
        "This data is stored completely separately from Miniplant 2.0 — cycle numbers "
        "never collide between the two systems."
    )

    session = get_session()
    try:
        total_cycles = session.query(CarbonNestCycleData).count()
        total_weeks = session.query(CarbonNestWeeklySummary).count()

        from sqlalchemy import func
        cycle_dates = session.query(
            func.min(CarbonNestCycleData.start_time),
            func.max(CarbonNestCycleData.start_time),
        ).first()
    finally:
        session.close()

    st.markdown("### 📊 Data Status")
    stat_col1, stat_col2, stat_col3, stat_col4 = st.columns(4)
    with stat_col1:
        st.metric("Cycles Imported", total_cycles)
    with stat_col2:
        st.metric("Weeks Calculated", total_weeks)
    with stat_col3:
        st.metric("Earliest Cycle", cycle_dates[0].strftime("%Y-%m-%d") if cycle_dates[0] else "No data")
    with stat_col4:
        st.metric("Latest Cycle", cycle_dates[1].strftime("%Y-%m-%d") if cycle_dates[1] else "No data")

    st.divider()

    tab1, tab2, tab3 = st.tabs(["📤 Carbon Nest Import", "✍️ Weekly Entry", "📋 View Data"])

    with tab1:
        st.markdown("### Step 1: Import Carbon Nest Exports")
        st.markdown("""
        Upload the two CSV exports from Carbon Nest.

        **Plant Cycles CSV columns:**
        `Cycle #`, `Module`, `Start Time`, `End Time`, `Type`, `ADS CO2 (kg)`, `ADS Hours`,
        `ADS Lost CO2 (kg)`, `ADS Efficiency`, `ADS Mass Cap`, `ADS Vol Cap`, `DES CO2 (kg)`,
        `DES Hours`, `BAG CO2 (kg)`, `DES Efficiency`, `BAG Efficiency`, `DES Vol Cap`,
        `eTotal kWh`, `Steam (kg)`

        **Cycle Energy CSV columns:**
        `Cycle #`, `Module`, `MWh/tCO2`, `Fans (kWh)`, `CT (kWh)`, `CT Pump (kWh)`,
        `VP402 (kWh)`, `VP501 (kWh)`, `Boiler A (kWh)`, `Boiler B (kWh)`, `Main Utility (kWh)`
        """)

        import_col1, import_col2 = st.columns(2)
        with import_col1:
            st.markdown("**Plant Cycles CSV**")
            cycles_file = st.file_uploader("Upload Plant Cycles", type=["csv"], key="cn_cycles")
        with import_col2:
            st.markdown("**Cycle Energy CSV**")
            energy_file = st.file_uploader("Upload Cycle Energy", type=["csv"], key="cn_energy")

        if cycles_file and energy_file:
            cycles_df, cycle_errors = load_plant_cycles(cycles_file)
            energy_df, energy_errors = load_cycle_energy(energy_file)
            errors = cycle_errors + energy_errors

            if errors:
                for err in errors:
                    st.error(err)
            else:
                st.success("✅ Files parsed successfully!")

                preview_col1, preview_col2 = st.columns(2)
                with preview_col1:
                    st.markdown("**Plant Cycles Preview**")
                    st.dataframe(cycles_df.head(), width="stretch")
                    st.caption(f"Total rows: {len(cycles_df)}")
                with preview_col2:
                    st.markdown("**Cycle Energy Preview**")
                    st.dataframe(energy_df.head(), width="stretch")
                    st.caption(f"Total rows: {len(energy_df)}")

                # Series breakdown preview so admins can sanity-check before importing
                series_counts = cycles_df["raw_module"].value_counts()
                st.markdown("#### Detected Modules")
                st.dataframe(series_counts.rename("cycles").reset_index().rename(columns={"index": "Module"}), width="stretch", hide_index=True)

                st.markdown("#### Data Summary (from CSV)")
                sum_col1, sum_col2, sum_col3, sum_col4 = st.columns(4)
                with sum_col1:
                    ads_total = cycles_df["ads_co2_kg"].sum() if "ads_co2_kg" in cycles_df.columns else 0
                    st.metric("Total Adsorbed CO₂", f"{ads_total:.1f} kg")
                with sum_col2:
                    des_total = cycles_df["des_co2_kg"].sum() if "des_co2_kg" in cycles_df.columns else 0
                    st.metric("Total Desorbed CO₂", f"{des_total:.1f} kg")
                with sum_col3:
                    bag_total = cycles_df["bag_co2_kg"].sum() if "bag_co2_kg" in cycles_df.columns else 0
                    st.metric("Total Collected CO₂", f"{bag_total:.1f} kg")
                with sum_col4:
                    if "start_time" in cycles_df.columns:
                        min_date = cycles_df["start_time"].min()
                        max_date = cycles_df["start_time"].max()
                        if pd.notna(min_date) and pd.notna(max_date):
                            st.metric("Date Range", f"{min_date.strftime('%m/%d')} - {max_date.strftime('%m/%d')}")

                if st.button("🚀 Import to Carbon Nest Database", type="primary", width="stretch"):
                    merged = merge_plant_cycles_energy(cycles_df, energy_df)
                    session = get_session()
                    try:
                        report = import_cycles(session, merged, import_batch_id=str(uuid.uuid4()))
                    finally:
                        session.close()

                    if report.errors:
                        for err in report.errors:
                            st.error(err)

                    st.success(f"✅ Imported **{report.added}** cycles, skipped {report.skipped} (already imported)")

                    if report.date_range[0] and report.date_range[1]:
                        st.info(f"📅 Date range: {report.date_range[0].date()} to {report.date_range[1].date()}")
                        st.balloons()

    with tab2:
        st.markdown("### Step 2: Calculate Weekly Summary")
        st.markdown("""
        Carbon Nest weeks run **Saturday 18:00 → Saturday 18:00**, matching Athena's
        own weekly report cadence. Select the week, enter the **liquefied CO₂** amount,
        and fill in the utility/standby figures from that week's Athena weekly PDF
        report (SCADA's "Main Utility" export column is known to be incomplete/buggy
        right now, so these are entered by hand until that's fixed).
        """)

        st.markdown("#### Select Week")
        week_options = list_week_options(count_back=12, count_forward=1)
        selected_week_idx = st.selectbox(
            "Week (Saturday 18:00 → Saturday 18:00)",
            options=list(range(len(week_options))),
            format_func=lambda i: format_week_option(week_options[i]),
            index=2,  # most recently COMPLETED week by default (index 0 = next week, 1 = current/in-progress week)
            key="cn_week_select",
        )
        week_start, week_end = week_options[selected_week_idx]
        week_key = week_start.strftime("%Y%m%d%H%M")
        st.caption(f"📅 Selected: {week_start.strftime('%Y-%m-%d %H:%M')} to {week_end.strftime('%Y-%m-%d %H:%M')}")

        session = get_session()
        try:
            cycles_in_week = (
                session.query(CarbonNestCycleData)
                .filter(CarbonNestCycleData.start_time >= week_start, CarbonNestCycleData.start_time < week_end)
                .all()
            )

            if cycles_in_week:
                ads_sum = sum(safe_value(c.ads_co2_kg) for c in cycles_in_week)
                des_sum = sum(safe_value(c.des_co2_kg) for c in cycles_in_week)
                bag_sum = sum(safe_value(c.bag_co2_kg) for c in cycles_in_week)
                total_kwh_sum = sum(safe_value(c.total_kwh) for c in cycles_in_week)

                st.success(f"✅ Found **{len(cycles_in_week)}** cycles in this week")

                series_counts: dict = {}
                for c in cycles_in_week:
                    series_counts.setdefault(c.series, 0)
                    series_counts[c.series] += 1
                st.caption(
                    " · ".join(
                        f"{get_series_display_name(s)}: {n} cycles" for s, n in series_counts.items()
                    )
                )

                preview_col1, preview_col2, preview_col3, preview_col4 = st.columns(4)
                with preview_col1:
                    st.metric("Adsorbed CO₂", f"{ads_sum:.1f} kg")
                with preview_col2:
                    st.metric("Desorbed CO₂", f"{des_sum:.1f} kg")
                with preview_col3:
                    st.metric("Collected CO₂", f"{bag_sum:.1f} kg")
                with preview_col4:
                    st.metric("Process Energy (CSV)", f"{total_kwh_sum:.1f} kWh")
            else:
                st.warning("⚠️ No cycles found for this week. Check if your Carbon Nest export covers this period.")

            existing = session.query(CarbonNestWeeklySummary).filter(
                CarbonNestWeeklySummary.start_date == week_start
            ).first()

            if existing:
                st.info(f"📌 This week already has a summary. Current liquefied: {existing.liquefied_co2_kg or 0:.1f} kg")
                defaults = {
                    "liq": existing.liquefied_co2_kg or 0.0,
                    "water_pumps": existing.water_pumps_kwh or 0.0,
                    "compressor_a": existing.compressor_a_kwh or 0.0,
                    "compressor_b": existing.compressor_b_kwh or 0.0,
                    "boiler_a_standby": existing.boiler_a_standby_kwh or 0.0,
                    "boiler_b_standby": existing.boiler_b_standby_kwh or 0.0,
                    "vp402_standby": existing.vp402_standby_kwh or 0.0,
                    "vp501_standby": existing.vp501_standby_kwh or 0.0,
                    "ct_standby": existing.ct_standby_kwh or 0.0,
                    "liq_active": existing.liquefaction_active_transfer_kwh or 0.0,
                    "liq_standby": existing.liquefaction_standby_kwh or 0.0,
                    "notes": existing.notes or "",
                }
            else:
                defaults = {
                    "liq": 0.0, "water_pumps": 0.0, "compressor_a": 0.0, "compressor_b": 0.0,
                    "boiler_a_standby": 0.0, "boiler_b_standby": 0.0,
                    "vp402_standby": 0.0, "vp501_standby": 0.0, "ct_standby": 0.0,
                    "liq_active": 0.0, "liq_standby": 0.0, "notes": "",
                }
        finally:
            session.close()

        st.markdown("#### Liquefied CO₂ (Manual Entry)")
        liquefied = st.number_input(
            "Liquefied CO₂ (kg)", min_value=0.0, value=defaults["liq"], step=0.1, key=f"cn_liquefied_{week_key}"
        )

        st.markdown("#### Weekly Report Manual Entry")
        st.caption(
            "From the Athena weekly PDF's Component Consumptions tables — replaces the "
            "CSV's Main Utility figure entirely."
        )

        util_col1, util_col2, util_col3 = st.columns(3)
        with util_col1:
            water_pumps = st.number_input(
                "Water Pumps (kWh)", min_value=0.0, value=defaults["water_pumps"], step=0.1, key=f"cn_water_pumps_{week_key}",
                help="From the Athena weekly PDF's Component Consumptions table, Water Pumps row.",
            )
            compressor_a = st.number_input(
                "Compressor A (kWh)", min_value=0.0, value=defaults["compressor_a"], step=0.1, key=f"cn_compressor_a_{week_key}",
                help="From the Athena weekly PDF's Component Consumptions table, Compressor A row.",
            )
            compressor_b = st.number_input(
                "Compressor B (kWh)", min_value=0.0, value=defaults["compressor_b"], step=0.1, key=f"cn_compressor_b_{week_key}",
                help="From the Athena weekly PDF's Component Consumptions table, Compressor B row.",
            )
        with util_col2:
            boiler_a_standby = st.number_input(
                "Boiler A Standby (kWh)", min_value=0.0, value=defaults["boiler_a_standby"], step=0.1, key=f"cn_boiler_a_standby_{week_key}",
                help="From the Athena weekly PDF's Component Consumptions table, Boiler A Standby row (not the process energy already captured by the CSV import).",
            )
            boiler_b_standby = st.number_input(
                "Boiler B Standby (kWh)", min_value=0.0, value=defaults["boiler_b_standby"], step=0.1, key=f"cn_boiler_b_standby_{week_key}",
                help="From the Athena weekly PDF's Component Consumptions table, Boiler B Standby row (not the process energy already captured by the CSV import).",
            )
        with util_col3:
            vp402_standby = st.number_input(
                "VP-402 Standby (kWh)", min_value=0.0, value=defaults["vp402_standby"], step=0.1, key=f"cn_vp402_standby_{week_key}",
                help="From the Athena weekly PDF's Component Consumptions table, VP-402 Standby row.",
            )
            vp501_standby = st.number_input(
                "VP-501 Standby (kWh)", min_value=0.0, value=defaults["vp501_standby"], step=0.1, key=f"cn_vp501_standby_{week_key}",
                help="From the Athena weekly PDF's Component Consumptions table, VP-501 Standby row.",
            )
            ct_standby = st.number_input(
                "CT & CT Pump Standby (kWh)", min_value=0.0, value=defaults["ct_standby"], step=0.1, key=f"cn_ct_standby_{week_key}",
                help="Athena's weekly report doesn't split CT & CT Pump into process/standby — enter the "
                "difference between the report's CT & CT Pump total and the CSV's CT + CT Pump sum for this week.",
            )

        st.markdown("**Liquefaction**")
        liq_col1, liq_col2 = st.columns(2)
        with liq_col1:
            liq_active = st.number_input(
                "Active Transfer (kWh)", min_value=0.0, value=defaults["liq_active"], step=0.1, key=f"cn_liq_active_{week_key}",
                help="From the Athena weekly PDF's Component Consumptions table, Liquefaction Active Transfer row.",
            )
        with liq_col2:
            liq_standby = st.number_input(
                "Standby/RFU (kWh)", min_value=0.0, value=defaults["liq_standby"], step=0.1, key=f"cn_liq_standby_{week_key}",
                help="From the Athena weekly PDF's Component Consumptions table, Liquefaction Standby/RFU row.",
            )

        notes = st.text_area("Notes (optional)", value=defaults["notes"], key=f"cn_notes_{week_key}")

        if st.button("💾 Calculate & Save Weekly Summary", type="primary", width="stretch", key="cn_save_summary"):
            session = get_session()
            try:
                summary = create_or_update_weekly_summary(
                    session,
                    week_start=week_start,
                    liquefied_co2_kg=liquefied,
                    water_pumps_kwh=water_pumps,
                    compressor_a_kwh=compressor_a,
                    compressor_b_kwh=compressor_b,
                    boiler_a_standby_kwh=boiler_a_standby,
                    boiler_b_standby_kwh=boiler_b_standby,
                    vp402_standby_kwh=vp402_standby,
                    vp501_standby_kwh=vp501_standby,
                    ct_standby_kwh=ct_standby,
                    liquefaction_active_transfer_kwh=liq_active,
                    liquefaction_standby_kwh=liq_standby,
                    notes=notes,
                    created_by=st.session_state.get("user_id"),
                )

                st.success(f"✅ Saved week {summary.start_date.strftime('%Y-%m-%d')} → {summary.end_date.strftime('%Y-%m-%d')}")

                st.markdown("#### Calculated Results")
                result_col1, result_col2, result_col3 = st.columns(3)
                with result_col1:
                    st.metric("Operational Emissions", f"{summary.total_operational_emissions_kg or 0:.1f} kg")
                with result_col2:
                    st.metric("Embodied Emissions (output-based)", f"{summary.total_embodied_emissions_kg or 0:.1f} kg")
                with result_col3:
                    net = summary.net_removal_kg or 0
                    st.metric("Net Removal", f"{net:.1f} kg", delta="Net Positive" if net > 0 else "Net Negative")

            finally:
                session.close()

    with tab3:
        st.markdown("### View & Manage Data")
        view_tab1, view_tab2 = st.tabs(["📅 Weekly Summaries", "🔄 Cycle Data"])

        with view_tab1:
            session = get_session()
            try:
                all_weeks = (
                    session.query(CarbonNestWeeklySummary)
                    .order_by(CarbonNestWeeklySummary.start_date.desc())
                    .all()
                )
                if all_weeks:
                    st.caption(f"Total: {len(all_weeks)} weekly summaries")
                    for week in all_weeks:
                        status_emoji = "✅" if week.is_net_positive else "❌"
                        week_label = f"{week.start_date.strftime('%Y-%m-%d %H:%M')} → {week.end_date.strftime('%Y-%m-%d %H:%M')}"
                        with st.expander(f"{status_emoji} {week_label}"):
                            r_col1, r_col2, r_col3, r_col4 = st.columns([1, 1, 1, 0.5])
                            with r_col1:
                                st.markdown("**CO₂ Flow (kg)**")
                                st.write(f"- Adsorbed: {week.total_ads_co2_kg or 0:.1f}")
                                st.write(f"- Desorbed: {week.total_des_co2_kg or 0:.1f}")
                                st.write(f"- Collected: {week.total_bag_co2_kg or 0:.1f}")
                                st.write(f"- Liquefied: {week.liquefied_co2_kg or 0:.1f}")
                            with r_col2:
                                st.markdown("**Emissions (kg CO₂)**")
                                st.write(f"- Operational: {week.total_operational_emissions_kg or 0:.1f}")
                                st.write(f"- Embodied: {week.total_embodied_emissions_kg or 0:.1f}")
                                st.write(f"- Total: {week.total_emissions_kg or 0:.1f}")
                            with r_col3:
                                st.markdown("**Result**")
                                net = week.net_removal_kg or 0
                                status = "✅ Net Positive" if net > 0 else "❌ Net Negative"
                                st.write(f"- Net Removal: {net:.1f} kg")
                                st.write(f"- Status: {status}")
                                st.write(f"- Cycles: {week.total_cycles or 0}")
                            with r_col4:
                                st.markdown("**Actions**")
                                if st.button("🗑️ Delete", key=f"cn_del_{week.id}", type="secondary"):
                                    del_session = get_session()
                                    try:
                                        del_session.query(CarbonNestCycleData).filter(
                                            CarbonNestCycleData.weekly_summary_id == week.id
                                        ).delete()
                                        del_session.query(CarbonNestWeeklySummary).filter(
                                            CarbonNestWeeklySummary.id == week.id
                                        ).delete()
                                        del_session.commit()
                                        st.success(f"Deleted {week_label}")
                                        st.rerun()
                                    finally:
                                        del_session.close()
                            if week.notes:
                                st.caption(f"Notes: {week.notes}")
                else:
                    st.info("No weekly summaries yet.")
            finally:
                session.close()

        with view_tab2:
            session = get_session()
            try:
                recent_cycles = (
                    session.query(CarbonNestCycleData)
                    .order_by(CarbonNestCycleData.start_time.desc())
                    .limit(20)
                    .all()
                )
                if recent_cycles:
                    st.caption(f"Showing most recent 20 of {total_cycles} total cycles")
                    cycle_data = []
                    for c in recent_cycles:
                        cycle_data.append({
                            "Date": c.start_time.strftime("%Y-%m-%d %H:%M") if c.start_time else "N/A",
                            "Cycle": c.cycle_number,
                            "Module": c.raw_module,
                            "Series": get_series_display_name(c.series),
                            "Nelion": c.nelion or "Combined/unattributed",
                            "ADS CO₂": f"{c.ads_co2_kg or 0:.2f}",
                            "DES CO₂": f"{c.des_co2_kg or 0:.2f}",
                            "BAG CO₂": f"{c.bag_co2_kg or 0:.2f}",
                            "Total kWh": f"{c.total_kwh or 0:.1f}",
                        })
                    st.dataframe(cycle_data, width="stretch", hide_index=True)
                else:
                    st.info("No cycle data imported yet. Use the Carbon Nest Import tab above.")
            finally:
                session.close()


if __name__ == "__main__":
    main()
