import sys
from pathlib import Path
import uuid
from datetime import date, timedelta

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import streamlit as st

from app.auth.authorization import require_admin
from app.components.branding import get_brand_css, render_logo
from app.database.connection import get_session, init_db
from app.database.models import WeeklySummary, CycleData
from app.services.aggregation import create_or_update_weekly_summary
from app.services.data_import import (
    import_cycles,
    load_cycle_data,
    load_energy_data,
    merge_cycle_energy,
)


def get_week_from_date(start_date: date) -> tuple:
    """Get ISO year and week from a date, and calculate end date."""
    # Always use the provided date as start, then +6 days for end
    week_end = start_date + timedelta(days=6)
    iso = start_date.isocalendar()
    return iso.year, iso.week, start_date, week_end


def main() -> None:
    st.set_page_config(page_title="Data Entry - Octavia CAS", page_icon="📥", layout="wide")
    init_db()
    if not require_admin():
        return

    # Apply brand CSS and logo
    st.markdown(get_brand_css(), unsafe_allow_html=True)
    render_logo(location="sidebar")

    st.title("📥 Data Entry")
    st.markdown("Import SCADA cycle data and enter weekly liquefied CO₂ measurements")

    session = get_session()
    try:
        # Get stats
        total_cycles = session.query(CycleData).count()
        total_weeks = session.query(WeeklySummary).count()
        
        # Get cycle date range
        from sqlalchemy import func
        cycle_dates = session.query(
            func.min(CycleData.start_time),
            func.max(CycleData.start_time)
        ).first()
        
        # Get recent weeks
        recent_weeks = (
            session.query(WeeklySummary)
            .order_by(WeeklySummary.year.desc(), WeeklySummary.week_number.desc())
            .limit(5)
            .all()
        )
    finally:
        session.close()

    # Status overview
    st.markdown("### 📊 Data Status")
    stat_col1, stat_col2, stat_col3, stat_col4 = st.columns(4)
    
    with stat_col1:
        st.metric("Cycles Imported", total_cycles)
    with stat_col2:
        st.metric("Weeks Calculated", total_weeks)
    with stat_col3:
        if cycle_dates[0]:
            st.metric("Earliest Cycle", cycle_dates[0].strftime("%Y-%m-%d"))
        else:
            st.metric("Earliest Cycle", "No data")
    with stat_col4:
        if cycle_dates[1]:
            st.metric("Latest Cycle", cycle_dates[1].strftime("%Y-%m-%d"))
        else:
            st.metric("Latest Cycle", "No data")

    st.divider()

    # Tabs
    tab1, tab2, tab3, tab4 = st.tabs([
        "📤 SCADA Import", "✍️ Weekly Entry", "📝 Manual Entry", "📋 View Data"
    ])

    with tab1:
        st.markdown("### Step 1: Import SCADA Cycle & Energy Data")
        st.markdown("""
        Upload the CSV files exported from SCADA containing cycle performance data.
        
        **Expected columns in Cycle CSV:**
        - `Cycle #`, `Machine`, `Start Time`, `ADS CO2 (kg)`, `DES CO2 (kg)`, `BAG CO2`, `eTotal kWh`, `Steam (kg)`
        
        **Expected columns in Energy CSV:**
        - `Cycle #`, `Machine`, `eTotal (kWh)`, `Boiler (kWh)`, `SRV/LRVP (kWh)`, `CT (kWh)`, `NM1-4 Fan (kWh)`
        """)

        import_col1, import_col2 = st.columns(2)
        
        with import_col1:
            st.markdown("**Cycle Data CSV**")
            cycle_file = st.file_uploader("Upload Cycle Data", type=["csv"], key="cycle")
        
        with import_col2:
            st.markdown("**Energy Data CSV**")
            energy_file = st.file_uploader("Upload Energy Data", type=["csv"], key="energy")

        if cycle_file and energy_file:
            cycle_df, cycle_errors = load_cycle_data(cycle_file)
            energy_df, energy_errors = load_energy_data(energy_file)
            errors = cycle_errors + energy_errors

            if errors:
                for err in errors:
                    st.error(err)
            else:
                st.success("✅ Files parsed successfully!")
                
                # Preview
                preview_col1, preview_col2 = st.columns(2)
                
                with preview_col1:
                    st.markdown("**Cycle Data Preview**")
                    st.dataframe(cycle_df.head(), width="stretch")
                    st.caption(f"Total rows: {len(cycle_df)}")
                
                with preview_col2:
                    st.markdown("**Energy Data Preview**")
                    st.dataframe(energy_df.head(), width="stretch")
                    st.caption(f"Total rows: {len(energy_df)}")

                # Summary stats from the CSV
                st.markdown("#### Data Summary (from CSV)")
                sum_col1, sum_col2, sum_col3, sum_col4 = st.columns(4)
                
                with sum_col1:
                    ads_total = cycle_df["ads_co2_kg"].sum() if "ads_co2_kg" in cycle_df.columns else 0
                    st.metric("Total ADS CO₂", f"{ads_total:.1f} kg")
                
                with sum_col2:
                    des_total = cycle_df["des_co2_kg"].sum() if "des_co2_kg" in cycle_df.columns else 0
                    st.metric("Total DES CO₂", f"{des_total:.1f} kg")
                
                with sum_col3:
                    bag_total = cycle_df["bag_co2_kg"].sum() if "bag_co2_kg" in cycle_df.columns else 0
                    st.metric("Total BAG CO₂", f"{bag_total:.1f} kg")
                
                with sum_col4:
                    if "start_time" in cycle_df.columns:
                        min_date = cycle_df["start_time"].min()
                        max_date = cycle_df["start_time"].max()
                        if pd.notna(min_date) and pd.notna(max_date):
                            st.metric("Date Range", f"{min_date.strftime('%m/%d')} - {max_date.strftime('%m/%d')}")

                if st.button("🚀 Import to Database", type="primary", width="stretch"):
                    merged = merge_cycle_energy(cycle_df, energy_df)
                    session = get_session()
                    try:
                        report = import_cycles(session, merged, import_batch_id=str(uuid.uuid4()))
                    finally:
                        session.close()
                    
                    if report.errors:
                        for err in report.errors:
                            st.error(err)
                    
                    st.success(f"✅ Imported **{report.added}** cycles, skipped {report.skipped}")
                    
                    if report.date_range[0] and report.date_range[1]:
                        st.info(f"📅 Date range: {report.date_range[0].date()} to {report.date_range[1].date()}")
                        st.balloons()

    with tab2:
        st.markdown("### Step 2: Calculate Weekly Summary")
        st.markdown("""
        After importing SCADA data, select a week and enter the **liquefied CO₂** amount 
        (measured from the cryogenic tank load cell). This triggers the weekly calculation 
        which aggregates all cycles in that week.
        
        ⚠️ **Note:** Liquefaction data is entered manually as it's not in SCADA.
        """)

        st.markdown("#### Select Week")
        
        # Date picker for week start
        today = date.today()
        # Default to start of current week (Monday)
        days_since_monday = today.weekday()
        default_start = today - timedelta(days=days_since_monday)
        
        date_col1, date_col2 = st.columns(2)
        
        with date_col1:
            week_start_date = st.date_input(
                "Week Start Date (select any day, will use as start)",
                value=default_start,
                help="Select the first day of the week you want to calculate"
            )
        
        with date_col2:
            week_end_date = week_start_date + timedelta(days=6)
            st.markdown(f"""
            <div style="background:#e7f3ff; padding:1rem; border-radius:8px; margin-top:1.7rem;">
                <strong>Week End:</strong> {week_end_date.strftime('%Y-%m-%d')} ({week_end_date.strftime('%A')})
            </div>
            """, unsafe_allow_html=True)
        
        iso_year, iso_week, _, _ = get_week_from_date(week_start_date)
        st.caption(f"📅 Selected: Week {iso_week} of {iso_year} ({week_start_date} to {week_end_date})")

        # Check for cycles in this week
        session = get_session()
        try:
            from datetime import datetime
            start_dt = datetime.combine(week_start_date, datetime.min.time())
            end_dt = datetime.combine(week_end_date + timedelta(days=1), datetime.min.time())
            
            from sqlalchemy import and_
            cycles_in_week = (
                session.query(CycleData)
                .filter(and_(CycleData.start_time >= start_dt, CycleData.start_time < end_dt))
                .all()
            )
            
            # Aggregate preview
            if cycles_in_week:
                from app.services.calculations import safe_value
                ads_sum = sum(safe_value(c.ads_co2_kg) for c in cycles_in_week)
                des_sum = sum(safe_value(c.des_co2_kg) for c in cycles_in_week)
                bag_sum = sum(safe_value(c.bag_co2_kg) for c in cycles_in_week)
                boiler_sum = sum(safe_value(c.boiler_kwh) for c in cycles_in_week)
                total_kwh_sum = sum(safe_value(c.total_kwh) for c in cycles_in_week)
                
                st.success(f"✅ Found **{len(cycles_in_week)}** cycles in this week")
                
                preview_col1, preview_col2, preview_col3, preview_col4 = st.columns(4)
                with preview_col1:
                    st.metric("ADS CO₂", f"{ads_sum:.1f} kg")
                with preview_col2:
                    st.metric("DES CO₂", f"{des_sum:.1f} kg")
                with preview_col3:
                    st.metric("BAG CO₂", f"{bag_sum:.1f} kg")
                with preview_col4:
                    st.metric("Total Energy", f"{total_kwh_sum:.1f} kWh")
            else:
                st.warning(f"⚠️ No cycles found for this week. Check if your SCADA data covers this period.")
            
            # Check for existing summary
            existing = session.query(WeeklySummary).filter(
                WeeklySummary.year == iso_year,
                WeeklySummary.week_number == iso_week
            ).first()
            
            if existing:
                st.info(f"📌 This week already has a summary. Current liquefied: {existing.liquefied_co2_kg or 0:.1f} kg")
                default_liq = existing.liquefied_co2_kg or 0.0
                default_liq_energy = 0.0  # Not tracked yet
                default_notes = existing.notes or ""
            else:
                default_liq = 0.0
                default_liq_energy = 0.0
                default_notes = ""
        finally:
            session.close()

        st.markdown("#### Liquefaction Data (Manual Entry)")
        st.caption("Enter the amount of CO₂ liquefied this week (from load cell measurement)")
        
        liq_col1, liq_col2 = st.columns(2)
        with liq_col1:
            liquefied = st.number_input(
                "Liquefied CO₂ (kg)",
                min_value=0.0,
                value=default_liq,
                step=0.1,
                help="Amount of CO₂ successfully liquefied and stored"
            )
        with liq_col2:
            liq_energy = st.number_input(
                "Liquefaction Energy (kWh) - Optional",
                min_value=0.0,
                value=default_liq_energy,
                step=1.0,
                help="Energy consumed by the liquefaction unit (if tracked separately)"
            )
        
        notes = st.text_area("Notes (optional)", value=default_notes)

        if st.button("💾 Calculate & Save Weekly Summary", type="primary", width="stretch"):
            session = get_session()
            try:
                summary = create_or_update_weekly_summary(
                    session,
                    year=iso_year,
                    week_number=iso_week,
                    liquefied_co2_kg=liquefied,
                    liquefaction_energy_kwh=liq_energy,
                    notes=notes,
                    created_by=st.session_state.get("user_id"),
                )
                
                st.success(f"✅ Saved week {summary.year}-W{summary.week_number:02d}")
                
                # Show results
                st.markdown("#### Calculated Results")
                
                result_col1, result_col2, result_col3, result_col4 = st.columns(4)
                
                with result_col1:
                    st.markdown(f"""
                    <div style="background:#e8f5e9; padding:1rem; border-radius:8px; text-align:center;">
                        <div style="font-size:0.75rem; color:#666;">ADSORBED</div>
                        <div style="font-size:1.3rem; font-weight:bold; color:#2e7d32;">{summary.total_ads_co2_kg or 0:.1f} kg</div>
                    </div>
                    """, unsafe_allow_html=True)
                
                with result_col2:
                    st.markdown(f"""
                    <div style="background:#fff3e0; padding:1rem; border-radius:8px; text-align:center;">
                        <div style="font-size:0.75rem; color:#666;">DESORBED</div>
                        <div style="font-size:1.3rem; font-weight:bold; color:#ef6c00;">{summary.total_des_co2_kg or 0:.1f} kg</div>
                    </div>
                    """, unsafe_allow_html=True)
                
                with result_col3:
                    st.markdown(f"""
                    <div style="background:#e3f2fd; padding:1rem; border-radius:8px; text-align:center;">
                        <div style="font-size:0.75rem; color:#666;">COLLECTED</div>
                        <div style="font-size:1.3rem; font-weight:bold; color:#1565c0;">{summary.total_bag_co2_kg or 0:.1f} kg</div>
                    </div>
                    """, unsafe_allow_html=True)
                
                with result_col4:
                    st.markdown(f"""
                    <div style="background:#e1f5fe; padding:1rem; border-radius:8px; text-align:center;">
                        <div style="font-size:0.75rem; color:#666;">LIQUEFIED</div>
                        <div style="font-size:1.3rem; font-weight:bold; color:#0277bd;">{summary.liquefied_co2_kg or 0:.1f} kg</div>
                    </div>
                    """, unsafe_allow_html=True)
                
                st.divider()
                
                em_col1, em_col2, em_col3 = st.columns(3)
                
                with em_col1:
                    st.markdown(f"""
                    <div style="background:#fff8e1; padding:1rem; border-radius:8px; text-align:center;">
                        <div style="font-size:0.75rem; color:#666;">OPERATIONAL EMISSIONS</div>
                        <div style="font-size:1.3rem; font-weight:bold; color:#f57c00;">{summary.total_operational_emissions_kg or 0:.1f} kg</div>
                    </div>
                    """, unsafe_allow_html=True)
                
                with em_col2:
                    st.markdown(f"""
                    <div style="background:#fce4ec; padding:1rem; border-radius:8px; text-align:center;">
                        <div style="font-size:0.75rem; color:#666;">EMBODIED EMISSIONS</div>
                        <div style="font-size:1.3rem; font-weight:bold; color:#c2185b;">{summary.total_embodied_emissions_kg or 0:.1f} kg</div>
                    </div>
                    """, unsafe_allow_html=True)
                
                with em_col3:
                    net = summary.net_removal_kg or 0
                    color = "#2e7d32" if net > 0 else "#c62828"
                    bg = "#e8f5e9" if net > 0 else "#ffebee"
                    status = "✅ Net Positive" if net > 0 else "❌ Net Negative"
                    st.markdown(f"""
                    <div style="background:{bg}; padding:1rem; border-radius:8px; text-align:center;">
                        <div style="font-size:0.75rem; color:#666;">NET REMOVAL</div>
                        <div style="font-size:1.3rem; font-weight:bold; color:{color};">{net:.1f} kg</div>
                        <div style="font-size:0.7rem; color:#888;">{status}</div>
                    </div>
                    """, unsafe_allow_html=True)
                
                # Energy intensity: use liquefied if available, otherwise BAG CO2
                co2_for_intensity = summary.liquefied_co2_kg if (summary.liquefied_co2_kg or 0) > 0 else (summary.total_bag_co2_kg or 0)
                if co2_for_intensity > 0 and (summary.total_energy_kwh or 0) > 0:
                    intensity = (summary.total_energy_kwh or 0) / (co2_for_intensity / 1000)
                    basis = "Liquefied" if (summary.liquefied_co2_kg or 0) > 0 else "Collected"
                    st.metric(f"⚡ Energy Intensity ({basis})", f"{intensity:.0f} kWh/tCO₂")
                
                st.caption(f"Cycles aggregated: {summary.total_cycles or 0}")
                
            finally:
                session.close()

    with tab3:
        st.markdown("### Manual Weekly Entry (Without SCADA)")
        st.markdown("""
        Use this form to manually enter weekly data if you don't have SCADA CSV exports.
        This is useful for historical data or when SCADA data is unavailable.
        """)
        
        # Date picker
        m_week_start = st.date_input("Week Start Date", value=default_start, key="manual_start")
        m_week_end = m_week_start + timedelta(days=6)
        st.caption(f"Week: {m_week_start} to {m_week_end}")
        
        m_iso_year, m_iso_week, _, _ = get_week_from_date(m_week_start)
        
        with st.form("manual_entry_form"):
            st.markdown("#### CO₂ Measurements (kg)")
            co2_col1, co2_col2, co2_col3, co2_col4 = st.columns(4)
            
            with co2_col1:
                m_ads = st.number_input("Adsorbed CO₂", min_value=0.0, step=0.1, key="m_ads")
            with co2_col2:
                m_des = st.number_input("Desorbed CO₂", min_value=0.0, step=0.1, key="m_des")
            with co2_col3:
                m_bag = st.number_input("Collected (Bag) CO₂", min_value=0.0, step=0.1, key="m_bag")
            with co2_col4:
                m_liq = st.number_input("Liquefied CO₂", min_value=0.0, step=0.1, key="m_liq")
            
            st.markdown("#### Energy Consumption (kWh)")
            energy_col1, energy_col2, energy_col3 = st.columns(3)
            
            with energy_col1:
                m_boiler = st.number_input("Boiler (Thermal)", min_value=0.0, step=1.0, key="m_boiler")
            with energy_col2:
                m_aux = st.number_input("Auxiliary", min_value=0.0, step=1.0, key="m_aux")
            with energy_col3:
                m_total = st.number_input("Total", min_value=0.0, step=1.0, key="m_total")
            
            st.markdown("#### Additional Info")
            m_cycles = st.number_input("Number of Cycles", min_value=0, value=0, key="m_cycles")
            m_notes = st.text_area("Notes", key="m_notes")
            
            submitted = st.form_submit_button("💾 Save Manual Entry", type="primary", width="stretch")
            
            if submitted:
                session = get_session()
                try:
                    from app.services.calculations import calculate_weekly_metrics
                    from app.services.aggregation import _get_config_value, _get_weekly_embodied
                    
                    grid_ef = _get_config_value(session, "grid_emission_factor", 0.049)
                    infra_weekly, sorbent_weekly = _get_weekly_embodied(session)
                    
                    metrics = calculate_weekly_metrics(
                        ads_co2_kg=m_ads,
                        des_co2_kg=m_des,
                        bag_co2_kg=m_bag,
                        liquefied_co2_kg=m_liq,
                        thermal_energy_kwh=m_boiler,
                        auxiliary_energy_kwh=m_aux,
                        total_energy_kwh=m_total if m_total > 0 else m_boiler + m_aux,
                        steam_kg=0,
                        grid_ef=grid_ef,
                        infrastructure_embodied_kg=infra_weekly,
                        sorbent_embodied_kg=sorbent_weekly,
                    )
                    
                    summary = session.query(WeeklySummary).filter(
                        WeeklySummary.year == m_iso_year,
                        WeeklySummary.week_number == m_iso_week
                    ).first()
                    
                    if not summary:
                        summary = WeeklySummary(
                            year=m_iso_year,
                            week_number=m_iso_week,
                            start_date=m_week_start,
                            end_date=m_week_end,
                            created_by=st.session_state.get("user_id"),
                        )
                        session.add(summary)
                    
                    summary.start_date = m_week_start
                    summary.end_date = m_week_end
                    summary.total_ads_co2_kg = m_ads
                    summary.total_des_co2_kg = m_des
                    summary.total_bag_co2_kg = m_bag
                    summary.liquefied_co2_kg = m_liq
                    summary.thermal_energy_kwh = m_boiler
                    summary.auxiliary_energy_kwh = m_aux
                    summary.total_energy_kwh = m_total if m_total > 0 else m_boiler + m_aux
                    summary.total_cycles = m_cycles
                    summary.notes = m_notes
                    
                    for key, value in metrics.items():
                        if hasattr(summary, key):
                            setattr(summary, key, value)
                    
                    session.commit()
                    st.success(f"✅ Manual entry saved for {m_iso_year}-W{m_iso_week:02d}")
                    
                finally:
                    session.close()

    with tab4:
        st.markdown("### View & Manage Data")
        
        view_tab1, view_tab2 = st.tabs(["📅 Weekly Summaries", "🔄 Cycle Data"])
        
        with view_tab1:
            # Get all weekly summaries (not just recent_weeks which is limited to 5)
            session = get_session()
            try:
                all_weeks = (
                    session.query(WeeklySummary)
                    .order_by(WeeklySummary.year.desc(), WeeklySummary.week_number.desc())
                    .all()
                )
                
                if all_weeks:
                    st.caption(f"Total: {len(all_weeks)} weekly summaries")
                    
                    for week in all_weeks:
                        status_emoji = "✅" if week.is_net_positive else "❌"
                        with st.expander(f"{status_emoji} {week.year}-W{week.week_number:02d} ({week.start_date} to {week.end_date})"):
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
                                # Energy intensity: use liquefied or BAG CO2
                                co2_for_int = (week.liquefied_co2_kg or 0) if (week.liquefied_co2_kg or 0) > 0 else (week.total_bag_co2_kg or 0)
                                if co2_for_int > 0 and (week.total_energy_kwh or 0) > 0:
                                    intensity = (week.total_energy_kwh or 0) / (co2_for_int / 1000)
                                    st.write(f"- Energy: {intensity:.0f} kWh/t")
                            
                            with r_col4:
                                st.markdown("**Actions**")
                                if st.button("🗑️ Delete", key=f"del_{week.id}", type="secondary"):
                                    del_session = get_session()
                                    try:
                                        del_session.query(WeeklySummary).filter(WeeklySummary.id == week.id).delete()
                                        del_session.commit()
                                        st.success(f"Deleted {week.year}-W{week.week_number}")
                                        st.rerun()
                                    finally:
                                        del_session.close()
                            
                            if week.notes:
                                st.caption(f"Notes: {week.notes}")
                    # Bulk delete option
                    st.divider()
                    if st.button("🗑️ Delete ALL Weekly Summaries", type="secondary"):
                        del_session = get_session()
                        try:
                            count = del_session.query(WeeklySummary).count()
                            del_session.query(WeeklySummary).delete()
                            del_session.commit()
                            st.success(f"Deleted {count} weekly summaries")
                            st.rerun()
                        finally:
                            del_session.close()
                else:
                    st.info("No weekly summaries yet.")
            finally:
                session.close()
        
        with view_tab2:
            session = get_session()
            try:
                # Show recent cycles
                recent_cycles = (
                    session.query(CycleData)
                    .order_by(CycleData.start_time.desc())
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
                            "Machine": c.machine,
                            "ADS CO₂": f"{c.ads_co2_kg or 0:.2f}",
                            "DES CO₂": f"{c.des_co2_kg or 0:.2f}",
                            "BAG CO₂": f"{c.bag_co2_kg or 0:.2f}",
                            "Total kWh": f"{c.total_kwh or 0:.1f}",
                            "Boiler kWh": f"{c.boiler_kwh or 0:.1f}",
                        })
                    
                    st.dataframe(cycle_data, width="stretch", hide_index=True)
                else:
                    st.info("No cycle data imported yet. Use the SCADA Import tab above.")
            finally:
                session.close()


if __name__ == "__main__":
    main()
