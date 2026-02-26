import sys
from pathlib import Path
from io import BytesIO

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from app.auth.authentication import require_login
from app.components.branding import get_brand_css, render_logo
from app.components.charts import cumulative_chart, co2_flow_chart
from app.components.sidebar import render_module_filter, get_filter_display_name
from app.database.connection import get_session, init_db
from app.database.models import WeeklySummary, CycleData
from app.services.aggregation import aggregate_cycles_by_pair, get_weekly_metrics_by_pair
from app.services.calculations import classify_module_pair


def load_summary_data(session, pair_filter: str = None) -> pd.DataFrame:
    """Load weekly summary data, optionally filtered by Module pair."""
    summaries = (
        session.query(WeeklySummary)
        .order_by(WeeklySummary.year, WeeklySummary.week_number)
        .all()
    )
    rows = []
    for w in summaries:
        # If pair filter is active, recalculate from filtered cycle data
        if pair_filter:
            pair_metrics = get_weekly_metrics_by_pair(session, w.year, w.week_number, pair_filter)
            ads = pair_metrics["ads_co2_kg"]
            des = pair_metrics["des_co2_kg"]
            bag = pair_metrics["bag_co2_kg"]
            total_energy = pair_metrics["total_kwh"]
            total_cycles = pair_metrics["cycles"]
            thermal_energy = pair_metrics["boiler_kwh"]
            auxiliary_energy = pair_metrics["auxiliary_kwh"]
            srv_lrvp_kwh = pair_metrics.get("srv_lrvp_kwh", 0)
            ct_kwh = pair_metrics.get("ct_kwh", 0)
            fans_kwh = pair_metrics.get("fans_kwh", 0)
            liquefaction_kwh = pair_metrics.get("liquefaction_energy_kwh", 0)
            
            # Skip weeks with no data for this pair
            if total_cycles == 0:
                continue
            
            # Proportional liquefied allocation
            liq = w.liquefied_co2_kg or 0
            total_bag = w.total_bag_co2_kg or 0
            if liq > 0 and total_bag > 0:
                liq = liq * (bag / total_bag)
            else:
                liq = 0
        else:
            pair_metrics = get_weekly_metrics_by_pair(session, w.year, w.week_number, None)
            srv_lrvp_kwh = pair_metrics.get("srv_lrvp_kwh", 0)
            ct_kwh = pair_metrics.get("ct_kwh", 0)
            fans_kwh = pair_metrics.get("fans_kwh", 0)
            liquefaction_kwh = pair_metrics.get("liquefaction_energy_kwh", 0)
            
            liq = w.liquefied_co2_kg or 0
            bag = w.total_bag_co2_kg or 0
            ads = w.total_ads_co2_kg or 0
            des = w.total_des_co2_kg or 0
            total_energy = w.total_energy_kwh or 0
            total_cycles = w.total_cycles or 0
            thermal_energy = w.thermal_energy_kwh or 0
            auxiliary_energy_stored = w.auxiliary_energy_kwh or 0
            
            # Ensure energy breakdown matches total_energy
            # If total_energy > thermal + auxiliary, allocate the difference
            # Use typical 70% thermal / 30% auxiliary split for missing energy
            energy_sum = thermal_energy + auxiliary_energy_stored
            if total_energy > energy_sum and total_energy > 0:
                missing_energy = total_energy - energy_sum
                # Allocate missing energy: 70% thermal (boiler), 30% auxiliary
                thermal_energy = thermal_energy + (missing_energy * 0.70)
                auxiliary_energy = auxiliary_energy_stored + (missing_energy * 0.30)
            else:
                auxiliary_energy = auxiliary_energy_stored
        
        # Collected CO2 = liquefied if available, otherwise bag
        collected_co2 = liq if liq > 0 else bag
        
        # Calculate energy intensity: total energy / collected CO2
        energy_intensity = (total_energy / (collected_co2 / 1000)) if (collected_co2 > 0 and total_energy > 0) else 0
        
        # Recalculate losses correctly:
        loss_stage_1 = ads - des
        loss_stage_2 = des - bag
        loss_stage_3 = (bag - liq) if liq > 0 else 0
        total_loss = ads - collected_co2
        
        # Proportional embodied emissions
        if pair_filter and (w.total_cycles or 0) > 0:
            proportion = total_cycles / w.total_cycles
            embodied = (w.total_embodied_emissions_kg or 0) * proportion
            infra_embodied = (w.infrastructure_embodied_kg or 0) * proportion
            sorbent_embodied = (w.sorbent_embodied_kg or 0) * proportion
        else:
            embodied = w.total_embodied_emissions_kg or 0
            infra_embodied = w.infrastructure_embodied_kg or 0
            sorbent_embodied = w.sorbent_embodied_kg or 0
        
        # Calculate emissions
        # Base total operational emissions on TOTAL energy, then split between
        # thermal and auxiliary so their sum matches the operational total.
        grid_ef = 0.049
        operational_emissions = total_energy * grid_ef

        if total_energy > 0:
            aux_share = min(max(auxiliary_energy / total_energy, 0.0), 1.0) if auxiliary_energy > 0 else 0.30
            thermal_share = 1.0 - aux_share
        else:
            aux_share = 0.0
            thermal_share = 0.0

        auxiliary_emissions = operational_emissions * aux_share
        thermal_emissions = operational_emissions * thermal_share
        total_emissions = operational_emissions + embodied
        net_removal = collected_co2 - total_emissions
        
        # Component emissions (proportional to energy share of auxiliary)
        aux_em = auxiliary_emissions
        if auxiliary_energy > 0 and aux_em > 0:
            srv_em = aux_em * (srv_lrvp_kwh / auxiliary_energy)
            ct_em = aux_em * (ct_kwh / auxiliary_energy)
            fans_em = aux_em * (fans_kwh / auxiliary_energy)
            liq_em = aux_em * (liquefaction_kwh / auxiliary_energy)
        else:
            srv_em = ct_em = fans_em = liq_em = 0

        rows.append({
            "Year": w.year,
            "Week": w.week_number,
            "Week Label": f"{w.year}-W{w.week_number:02d}",
            "Start Date": w.start_date,
            "End Date": w.end_date,
            "Adsorbed CO₂ (kg)": ads,
            "Desorbed CO₂ (kg)": des,
            "Collected CO₂ (kg)": collected_co2,
            "Bag CO₂ (kg)": bag,
            "Liquefied CO₂ (kg)": liq,
            "Stage 1 Loss (kg)": loss_stage_1,
            "Stage 2 Loss (kg)": loss_stage_2,
            "Stage 3 Loss (kg)": loss_stage_3,
            "Total Loss (kg)": total_loss,
            "Thermal Energy (kWh)": thermal_energy,
            "SRV/LRVP (kWh)": srv_lrvp_kwh,
            "CT (kWh)": ct_kwh,
            "Fans (kWh)": fans_kwh,
            "Liquefaction (kWh)": liquefaction_kwh,
            "Non-thermal Energy (kWh)": auxiliary_energy,
            "Total Energy (kWh)": total_energy,
            "Thermal Emissions (kg)": thermal_emissions,
            "SRV/LRVP Emissions (kg)": srv_em,
            "CT Emissions (kg)": ct_em,
            "Fans Emissions (kg)": fans_em,
            "Liquefaction Emissions (kg)": liq_em,
            "Non-thermal Emissions (kg)": auxiliary_emissions,
            "Operational Emissions (kg)": operational_emissions,
            "Infrastructure Embodied (kg)": infra_embodied,
            "Sorbent Embodied (kg)": sorbent_embodied,
            "Total Embodied (kg)": embodied,
            "Total Emissions (kg)": total_emissions,
            "Net Removal (kg)": net_removal,
            "Energy Intensity (kWh/tCO₂)": energy_intensity,
            "Cycles": total_cycles,
            "Net Positive": "Yes" if net_removal > 0 else "No",
            "Notes": w.notes or "",
        })
    return pd.DataFrame(rows)


def load_cycle_data(session) -> pd.DataFrame:
    cycles = session.query(CycleData).order_by(CycleData.start_time).all()
    rows = []
    for c in cycles:
        pair = classify_module_pair(c.machine) or "Unknown"
        rows.append({
            "Cycle #": c.cycle_number,
            "Machine": c.machine,
            "Module Pair": pair.upper() if pair != "Unknown" else pair,
            "Start Time": c.start_time,
            "ADS CO₂ (kg)": c.ads_co2_kg or 0,
            "DES CO₂ (kg)": c.des_co2_kg or 0,
            "BAG CO₂ (kg)": c.bag_co2_kg or 0,
            "Total kWh": c.total_kwh or 0,
            "Boiler kWh": c.boiler_kwh or 0,
            "Steam (kg)": c.steam_kg or 0,
            "DES n (%)": c.des_n or 0,
        })
    return pd.DataFrame(rows)


def main() -> None:
    st.set_page_config(page_title="Reports - Octavia CAS", page_icon="📈", layout="wide")
    init_db()
    if not require_login():
        return

    # Apply brand CSS
    st.markdown(get_brand_css(), unsafe_allow_html=True)
    
    # Sidebar with logo
    render_logo(location="sidebar")
    
    # Render the Module pair filter in sidebar and get selected value
    pair_filter = render_module_filter()

    st.title("📈 Reports & Analysis")
    
    # Show filter indicator
    if pair_filter:
        pair_name = get_filter_display_name(pair_filter)
        st.info(f"🔬 **Filtered View:** Showing data for **{pair_name}** only. Change filter in sidebar.")
    else:
        st.markdown("Generate detailed reports and export data for carbon credit verification")

    session = get_session()
    try:
        summary_df = load_summary_data(session, pair_filter)
        cycle_df = load_cycle_data(session)
        
        # Filter cycle data if pair filter is active
        if pair_filter:
            cycle_df = cycle_df[cycle_df["Module Pair"] == pair_filter.upper()]
    finally:
        session.close()

    if summary_df.empty:
        if pair_filter:
            st.warning(f"No data available for {pair_filter.upper()}. Try selecting 'All Modules' in the sidebar.")
        else:
            st.warning("No data available. Import SCADA data and create weekly summaries first.")
        return

    # Overview stats
    st.markdown("### 📊 Overview Statistics")
    
    total_captured = summary_df["Liquefied CO₂ (kg)"].sum()
    total_emissions = summary_df["Total Emissions (kg)"].sum()
    total_net = summary_df["Net Removal (kg)"].sum()
    weeks_positive = (summary_df["Net Positive"] == "Yes").sum()
    total_weeks = len(summary_df)
    
    stat_col1, stat_col2, stat_col3, stat_col4, stat_col5 = st.columns(5)
    
    with stat_col1:
        st.metric("Total CO₂ Liquefied", f"{total_captured:,.1f} kg", f"{total_captured/1000:.2f} tonnes")
    with stat_col2:
        st.metric("Total Emissions", f"{total_emissions:,.1f} kg", f"{total_emissions/1000:.2f} tonnes")
    with stat_col3:
        delta_color = "normal" if total_net > 0 else "inverse"
        st.metric("Net Removal", f"{total_net:,.1f} kg", f"{total_net/1000:.2f} tonnes", delta_color=delta_color)
    with stat_col4:
        st.metric("Weeks Net Positive", f"{weeks_positive}/{total_weeks}", f"{weeks_positive/total_weeks*100:.0f}%")
    with stat_col5:
        avg_intensity = summary_df["Energy Intensity (kWh/tCO₂)"].mean()
        st.metric("Avg Energy Intensity", f"{avg_intensity:,.0f} kWh/t")

    st.divider()

    # Report type selection
    report_tab1, report_tab2, report_tab3, report_tab4, report_tab5 = st.tabs([
        "📋 Weekly Summary", "🔄 CO₂ Flow", "🔬 Module Pairs", "⚡ Energy Analysis", "📤 Export"
    ])

    with report_tab1:
        st.markdown("### Weekly Summary Report")
        
        # Date filter
        filter_col1, filter_col2, filter_col3 = st.columns([1, 1, 2])
        with filter_col1:
            years = sorted(summary_df["Year"].unique())
            selected_year = st.selectbox("Year", ["All"] + [str(y) for y in years])
        with filter_col2:
            status_filter = st.selectbox("Status", ["All", "Net Positive", "Net Negative"])
        
        filtered_df = summary_df.copy()
        if selected_year != "All":
            filtered_df = filtered_df[filtered_df["Year"] == int(selected_year)]
        if status_filter == "Net Positive":
            filtered_df = filtered_df[filtered_df["Net Positive"] == "Yes"]
        elif status_filter == "Net Negative":
            filtered_df = filtered_df[filtered_df["Net Positive"] == "No"]
        
        # Summary table
        display_cols = [
            "Week Label", "Cycles", "Liquefied CO₂ (kg)", "Total Emissions (kg)",
            "Net Removal (kg)", "Net Positive"
        ]
        st.dataframe(
            filtered_df[display_cols].sort_values("Week Label", ascending=False),
            width="stretch",
            hide_index=True,
        )
        
        # Trend chart
        if len(filtered_df) > 1:
            # Convert for chart
            chart_df = filtered_df.copy()
            chart_df = chart_df.rename(columns={
                "Week Label": "week_label",
                "Net Removal (kg)": "net_removal_kg",
                "Liquefied CO₂ (kg)": "liquefied_co2_kg",
                "Total Emissions (kg)": "total_emissions_kg",
            })
            
            chart = cumulative_chart(chart_df)
            if chart:
                st.plotly_chart(chart, width="stretch")

    with report_tab2:
        st.markdown("### CO₂ Flow Analysis")
        st.markdown("Track CO₂ through each stage of the capture process")
        
        # Process efficiency summary
        total_ads = summary_df["Adsorbed CO₂ (kg)"].sum()
        total_des = summary_df["Desorbed CO₂ (kg)"].sum()
        total_bag = summary_df["Collected CO₂ (kg)"].sum()
        total_liq = summary_df["Liquefied CO₂ (kg)"].sum()
        
        eff_col1, eff_col2, eff_col3, eff_col4 = st.columns(4)
        
        with eff_col1:
            st.markdown(f"""
            <div style="background:#e8f5e9; padding:1rem; border-radius:8px; text-align:center;">
                <div style="font-size:0.8rem; color:#666;">Total Adsorbed</div>
                <div style="font-size:1.5rem; font-weight:bold; color:#2e7d32;">{total_ads:,.1f} kg</div>
            </div>
            """, unsafe_allow_html=True)
        
        with eff_col2:
            eff1 = (total_des / total_ads * 100) if total_ads > 0 else 0
            st.markdown(f"""
            <div style="background:#fff3e0; padding:1rem; border-radius:8px; text-align:center;">
                <div style="font-size:0.8rem; color:#666;">Total Desorbed</div>
                <div style="font-size:1.5rem; font-weight:bold; color:#ef6c00;">{total_des:,.1f} kg</div>
                <div style="font-size:0.75rem; color:#888;">{eff1:.1f}% efficiency</div>
            </div>
            """, unsafe_allow_html=True)
        
        with eff_col3:
            eff2 = (total_bag / total_des * 100) if total_des > 0 else 0
            st.markdown(f"""
            <div style="background:#e3f2fd; padding:1rem; border-radius:8px; text-align:center;">
                <div style="font-size:0.8rem; color:#666;">Total Collected</div>
                <div style="font-size:1.5rem; font-weight:bold; color:#1565c0;">{total_bag:,.1f} kg</div>
                <div style="font-size:0.75rem; color:#888;">{eff2:.1f}% efficiency</div>
            </div>
            """, unsafe_allow_html=True)
        
        with eff_col4:
            eff_total = (total_liq / total_ads * 100) if total_ads > 0 else 0
            st.markdown(f"""
            <div style="background:#e1f5fe; padding:1rem; border-radius:8px; text-align:center;">
                <div style="font-size:0.8rem; color:#666;">Total Liquefied</div>
                <div style="font-size:1.5rem; font-weight:bold; color:#0277bd;">{total_liq:,.1f} kg</div>
                <div style="font-size:0.75rem; color:#888;">{eff_total:.1f}% overall</div>
            </div>
            """, unsafe_allow_html=True)
        
        # Loss analysis
        st.markdown("#### Loss Analysis")
        
        total_loss_1 = summary_df["Stage 1 Loss (kg)"].sum()
        total_loss_2 = summary_df["Stage 2 Loss (kg)"].sum()
        total_loss_3 = summary_df["Stage 3 Loss (kg)"].sum()
        total_loss = summary_df["Total Loss (kg)"].sum()
        
        loss_data = pd.DataFrame({
            "Stage": ["Adsorption → Desorption", "Desorption → Collection", "Collection → Liquefaction", "Total"],
            "Loss (kg)": [total_loss_1, total_loss_2, total_loss_3, total_loss],
            "% of Input": [
                (total_loss_1 / total_ads * 100) if total_ads > 0 else 0,
                (total_loss_2 / total_des * 100) if total_des > 0 else 0,
                (total_loss_3 / total_bag * 100) if total_bag > 0 else 0,
                (total_loss / total_ads * 100) if total_ads > 0 else 0,
            ]
        })
        
        st.dataframe(loss_data, width="stretch", hide_index=True)
        
        # Flow chart over time
        chart_df = summary_df.copy()
        chart_df = chart_df.rename(columns={
            "Week Label": "week_label",
            "Adsorbed CO₂ (kg)": "total_ads_co2_kg",
            "Desorbed CO₂ (kg)": "total_des_co2_kg",
            "Collected CO₂ (kg)": "total_bag_co2_kg",
            "Liquefied CO₂ (kg)": "liquefied_co2_kg",
        })
        
        flow_chart = co2_flow_chart(chart_df.tail(12))
        if flow_chart:
            st.plotly_chart(flow_chart, width="stretch")

    with report_tab3:
        st.markdown("### 🔬 Module Pair Performance Analysis")
        st.markdown("Compare performance between Module pairs 1&3 vs 2&4")
        
        # Get pair analysis
        session = get_session()
        try:
            pair_analysis = aggregate_cycles_by_pair(session)
        finally:
            session.close()
        
        p1 = pair_analysis["pair_data"]["1n3"]
        p2 = pair_analysis["pair_data"]["2n4"]
        comparison = pair_analysis["comparison"]
        
        if p1["cycles"] > 0 or p2["cycles"] > 0:
            # Summary comparison
            pair_comp_col1, pair_comp_col2, pair_comp_col3 = st.columns(3)
            
            with pair_comp_col1:
                better_pair = "1&3" if p1["overall_efficiency"] > p2["overall_efficiency"] else "2&4"
                st.metric(
                    "Higher Efficiency",
                    f"Module {better_pair}",
                    f"+{comparison['efficiency_difference']:.1f}% better",
                )
            
            with pair_comp_col2:
                st.metric(
                    "1&3 CO₂ Contribution",
                    f"{comparison['1n3_co2_contribution']:.1f}%",
                    f"{p1['bag_co2_kg']:.1f} kg total",
                )
            
            with pair_comp_col3:
                st.metric(
                    "2&4 CO₂ Contribution",
                    f"{comparison['2n4_co2_contribution']:.1f}%",
                    f"{p2['bag_co2_kg']:.1f} kg total",
                )
            
            st.divider()
            
            # Detailed comparison table
            st.markdown("#### Detailed Performance Metrics")
            
            metrics_df = pd.DataFrame({
                "Metric": [
                    "Total Cycles",
                    "Total Adsorbed CO₂ (kg)",
                    "Total Desorbed CO₂ (kg)",
                    "Total Collected CO₂ (kg)",
                    "Overall Efficiency (%)",
                    "Ads→Des Efficiency (%)",
                    "Des→Bag Efficiency (%)",
                    "Total Loss (kg)",
                    "Loss Rate (%)",
                    "Energy Used (kWh)",
                    "kWh per kg CO₂",
                    "Avg Adsorbed/Cycle (kg)",
                    "Avg Collected/Cycle (kg)",
                ],
                "Module 1&3 🌟": [
                    str(p1["cycles"]),
                    f"{p1['ads_co2_kg']:.2f}",
                    f"{p1['des_co2_kg']:.2f}",
                    f"{p1['bag_co2_kg']:.2f}",
                    f"{p1['overall_efficiency']:.1f}",
                    f"{p1['ads_to_des_efficiency']:.1f}",
                    f"{p1['des_to_bag_efficiency']:.1f}",
                    f"{p1['total_loss']:.2f}",
                    f"{p1['loss_rate']:.1f}",
                    f"{p1['total_kwh']:.1f}",
                    f"{p1['kwh_per_kg_co2']:.2f}",
                    f"{p1['avg_ads_per_cycle']:.3f}",
                    f"{p1['avg_bag_per_cycle']:.3f}",
                ],
                "Module 2&4": [
                    str(p2["cycles"]),
                    f"{p2['ads_co2_kg']:.2f}",
                    f"{p2['des_co2_kg']:.2f}",
                    f"{p2['bag_co2_kg']:.2f}",
                    f"{p2['overall_efficiency']:.1f}",
                    f"{p2['ads_to_des_efficiency']:.1f}",
                    f"{p2['des_to_bag_efficiency']:.1f}",
                    f"{p2['total_loss']:.2f}",
                    f"{p2['loss_rate']:.1f}",
                    f"{p2['total_kwh']:.1f}",
                    f"{p2['kwh_per_kg_co2']:.2f}",
                    f"{p2['avg_ads_per_cycle']:.3f}",
                    f"{p2['avg_bag_per_cycle']:.3f}",
                ],
                "Difference": [
                    str(p1["cycles"] - p2["cycles"]),
                    f"{p1['ads_co2_kg'] - p2['ads_co2_kg']:.2f}",
                    f"{p1['des_co2_kg'] - p2['des_co2_kg']:.2f}",
                    f"{p1['bag_co2_kg'] - p2['bag_co2_kg']:.2f}",
                    f"{p1['overall_efficiency'] - p2['overall_efficiency']:+.1f}",
                    f"{p1['ads_to_des_efficiency'] - p2['ads_to_des_efficiency']:+.1f}",
                    f"{p1['des_to_bag_efficiency'] - p2['des_to_bag_efficiency']:+.1f}",
                    f"{p1['total_loss'] - p2['total_loss']:.2f}",
                    f"{p1['loss_rate'] - p2['loss_rate']:+.1f}",
                    f"{p1['total_kwh'] - p2['total_kwh']:.1f}",
                    f"{p1['kwh_per_kg_co2'] - p2['kwh_per_kg_co2']:+.2f}",
                    f"{p1['avg_ads_per_cycle'] - p2['avg_ads_per_cycle']:+.3f}",
                    f"{p1['avg_bag_per_cycle'] - p2['avg_bag_per_cycle']:+.3f}",
                ],
            })
            
            st.dataframe(metrics_df, width="stretch", hide_index=True)
            
            # Charts
            st.divider()
            st.markdown("#### Visual Comparison")
            
            chart_pair_col1, chart_pair_col2 = st.columns(2)
            
            with chart_pair_col1:
                # CO2 comparison bar chart
                fig1 = go.Figure()
                
                fig1.add_trace(go.Bar(
                    name="Module 1&3",
                    x=["Adsorbed", "Desorbed", "Collected"],
                    y=[p1["ads_co2_kg"], p1["des_co2_kg"], p1["bag_co2_kg"]],
                    marker_color="#4CAF50",
                    text=[f"{v:.1f}" for v in [p1["ads_co2_kg"], p1["des_co2_kg"], p1["bag_co2_kg"]]],
                    textposition="outside",
                    textfont=dict(color="#f8fafc"),
                ))
                fig1.add_trace(go.Bar(
                    name="Module 2&4",
                    x=["Adsorbed", "Desorbed", "Collected"],
                    y=[p2["ads_co2_kg"], p2["des_co2_kg"], p2["bag_co2_kg"]],
                    marker_color="#2196F3",
                    text=[f"{v:.1f}" for v in [p2["ads_co2_kg"], p2["des_co2_kg"], p2["bag_co2_kg"]]],
                    textposition="outside",
                    textfont=dict(color="#f8fafc"),
                ))
                
                fig1.update_layout(
                    title="CO₂ Flow Comparison (kg)",
                    barmode="group",
                    template="plotly_dark",
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    font=dict(color="#f8fafc"),
                    height=400,
                    xaxis=dict(tickfont=dict(color="#e2e8f0")),
                    yaxis=dict(tickfont=dict(color="#e2e8f0")),
                )
                st.plotly_chart(fig1, width="stretch")
            
            with chart_pair_col2:
                # Efficiency comparison
                fig2 = go.Figure()
                
                fig2.add_trace(go.Bar(
                    name="Module 1&3",
                    x=["Ads→Des", "Des→Bag", "Overall"],
                    y=[p1["ads_to_des_efficiency"], p1["des_to_bag_efficiency"], p1["overall_efficiency"]],
                    marker_color="#4CAF50",
                    text=[f"{v:.1f}%" for v in [p1["ads_to_des_efficiency"], p1["des_to_bag_efficiency"], p1["overall_efficiency"]]],
                    textposition="outside",
                    textfont=dict(color="#f8fafc"),
                ))
                fig2.add_trace(go.Bar(
                    name="Module 2&4",
                    x=["Ads→Des", "Des→Bag", "Overall"],
                    y=[p2["ads_to_des_efficiency"], p2["des_to_bag_efficiency"], p2["overall_efficiency"]],
                    marker_color="#2196F3",
                    text=[f"{v:.1f}%" for v in [p2["ads_to_des_efficiency"], p2["des_to_bag_efficiency"], p2["overall_efficiency"]]],
                    textposition="outside",
                    textfont=dict(color="#f8fafc"),
                ))
                
                fig2.update_layout(
                    title="Efficiency by Stage (%)",
                    barmode="group",
                    template="plotly_dark",
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    font=dict(color="#f8fafc"),
                    height=400,
                    yaxis_range=[0, 110],
                    xaxis=dict(tickfont=dict(color="#e2e8f0")),
                    yaxis=dict(tickfont=dict(color="#e2e8f0")),
                )
                st.plotly_chart(fig2, width="stretch")
            
            # Contribution pie chart
            st.markdown("#### CO₂ Contribution by Pair")
            
            fig3 = go.Figure(data=[go.Pie(
                labels=["Module 1&3", "Module 2&4"],
                values=[p1["bag_co2_kg"], p2["bag_co2_kg"]],
                marker_colors=["#4CAF50", "#2196F3"],
                hole=0.4,
                textinfo="label+percent",
                textfont_size=14,
            )])
            
            fig3.update_layout(
                title="Collected CO₂ Distribution by Pair",
                template="plotly_dark",
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#f8fafc"),
                height=350,
            )
            st.plotly_chart(fig3, width="stretch")
            
            # Cycle data filtered by pair
            st.divider()
            st.markdown("#### Cycle Data by Pair")
            
            pair_filter = st.selectbox(
                "Filter by Module Pair",
                ["All", "1N3 Only", "2N4 Only"],
                key="pair_filter"
            )
            
            filtered_cycles = cycle_df.copy()
            if pair_filter == "1N3 Only":
                filtered_cycles = filtered_cycles[filtered_cycles["Module Pair"] == "1N3"]
            elif pair_filter == "2N4 Only":
                filtered_cycles = filtered_cycles[filtered_cycles["Module Pair"] == "2N4"]
            
            st.dataframe(
                filtered_cycles.sort_values("Start Time", ascending=False).head(50),
                width="stretch",
                hide_index=True,
            )
            st.caption(f"Showing {min(50, len(filtered_cycles))} of {len(filtered_cycles)} cycles")
        else:
            st.info("No cycle data available. Import SCADA data to see Module pair analysis.")

    with report_tab4:
        st.markdown("### ⚡ Energy Analysis")
        
        # Energy totals
        total_thermal = summary_df["Thermal Energy (kWh)"].sum()
        total_aux = summary_df["Non-thermal Energy (kWh)"].sum()
        total_energy = summary_df["Total Energy (kWh)"].sum()
        total_srv = summary_df["SRV/LRVP (kWh)"].sum()
        total_ct = summary_df["CT (kWh)"].sum()
        total_fans = summary_df["Fans (kWh)"].sum()
        total_liq = summary_df["Liquefaction (kWh)"].sum()
        
        energy_col1, energy_col2, energy_col3 = st.columns(3)
        
        with energy_col1:
            thermal_pct = (total_thermal / total_energy * 100) if total_energy > 0 else 0
            st.metric("Total Thermal Energy", f"{total_thermal:,.0f} kWh", f"{thermal_pct:.1f}% of total")
        with energy_col2:
            aux_pct = (total_aux / total_energy * 100) if total_energy > 0 else 0
            st.metric("Total Non-thermal Energy", f"{total_aux:,.0f} kWh", f"{aux_pct:.1f}% of total")
        with energy_col3:
            st.metric("Total Energy", f"{total_energy:,.0f} kWh")
        
        # Non-thermal breakdown
        with st.expander("📋 Non-thermal energy breakdown (SRV/LRVP, CT, Fans, Liquefaction)"):
            nc1, nc2, nc3, nc4 = st.columns(4)
            with nc1:
                st.metric("SRV/LRVP", f"{total_srv:,.0f} kWh", f"{total_srv/total_aux*100:.1f}%" if total_aux > 0 else "-")
            with nc2:
                st.metric("CT", f"{total_ct:,.0f} kWh", f"{total_ct/total_aux*100:.1f}%" if total_aux > 0 else "-")
            with nc3:
                st.metric("Fans", f"{total_fans:,.0f} kWh", f"{total_fans/total_aux*100:.1f}%" if total_aux > 0 else "-")
            with nc4:
                st.metric("Liquefaction", f"{total_liq:,.0f} kWh", f"{total_liq/total_aux*100:.1f}%" if total_aux > 0 else "-")
        
        # Energy breakdown chart
        fig = go.Figure()
        
        fig.add_trace(go.Bar(
            name="Thermal (Boiler)",
            x=summary_df["Week Label"].tail(12),
            y=summary_df["Thermal Energy (kWh)"].tail(12),
            marker_color="#FD7E14",
        ))
        
        fig.add_trace(go.Bar(
            name="SRV/LRVP",
            x=summary_df["Week Label"].tail(12),
            y=summary_df["SRV/LRVP (kWh)"].tail(12),
            marker_color="#06B6D4",
        ))
        
        fig.add_trace(go.Bar(
            name="CT",
            x=summary_df["Week Label"].tail(12),
            y=summary_df["CT (kWh)"].tail(12),
            marker_color="#0EA5E9",
        ))
        
        fig.add_trace(go.Bar(
            name="Fans",
            x=summary_df["Week Label"].tail(12),
            y=summary_df["Fans (kWh)"].tail(12),
            marker_color="#14B8A6",
        ))
        
        fig.add_trace(go.Bar(
            name="Liquefaction",
            x=summary_df["Week Label"].tail(12),
            y=summary_df["Liquefaction (kWh)"].tail(12),
            marker_color="#6366F1",
        ))
        
        fig.update_layout(
            title="Energy Consumption by Type (Last 12 Weeks)",
            yaxis_title="Energy (kWh)",
            template="plotly_dark",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#f8fafc"),
            barmode="stack",
            height=400,
        )
        
        st.plotly_chart(fig, width="stretch")
        
        # Energy intensity trend
        fig2 = go.Figure()
        
        fig2.add_trace(go.Scatter(
            x=summary_df["Week Label"].tail(12),
            y=summary_df["Energy Intensity (kWh/tCO₂)"].tail(12),
            mode="lines+markers",
            name="Energy Intensity",
            line=dict(color="#6F42C1", width=3),
            marker=dict(size=10),
        ))
        
        fig2.update_layout(
            title="Energy Intensity Trend (Last 12 Weeks)",
            yaxis_title="kWh per tonne CO₂",
            template="plotly_dark",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#f8fafc"),
            height=350,
        )
        
        st.plotly_chart(fig2, width="stretch")

    with report_tab5:
        st.markdown("### 📤 Export Data")
        st.markdown("Download data for external analysis or carbon credit verification")
        
        export_col1, export_col2 = st.columns(2)
        
        with export_col1:
            st.markdown("#### Weekly Summaries")
            st.caption(f"{len(summary_df)} weeks of data")
            
            # CSV export
            csv_summary = summary_df.to_csv(index=False).encode('utf-8')
            st.download_button(
                "📥 Download Weekly Summary (CSV)",
                csv_summary,
                "octavia_weekly_summary.csv",
                "text/csv",
                width="stretch",
            )
            
            # Excel export
            buffer = BytesIO()
            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                summary_df.to_excel(writer, sheet_name='Weekly Summary', index=False)
            
            st.download_button(
                "📥 Download Weekly Summary (Excel)",
                buffer.getvalue(),
                "octavia_weekly_summary.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                width="stretch",
            )
        
        with export_col2:
            st.markdown("#### Cycle Data")
            st.caption(f"{len(cycle_df)} cycles of data")
            
            if not cycle_df.empty:
                csv_cycles = cycle_df.to_csv(index=False).encode('utf-8')
                st.download_button(
                    "📥 Download Cycle Data (CSV)",
                    csv_cycles,
                    "octavia_cycle_data.csv",
                    "text/csv",
                    width="stretch",
                )
                
                buffer2 = BytesIO()
                with pd.ExcelWriter(buffer2, engine='openpyxl') as writer:
                    cycle_df.to_excel(writer, sheet_name='Cycle Data', index=False)
                
                st.download_button(
                    "📥 Download Cycle Data (Excel)",
                    buffer2.getvalue(),
                    "octavia_cycle_data.xlsx",
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    width="stretch",
                )
            else:
                st.info("No cycle data available")
        
        st.divider()
        
        st.markdown("#### Puro.earth Format Export")
        st.markdown("Generate a report formatted for Puro.earth carbon credit submission")
        
        # Create Puro format
        puro_df = pd.DataFrame({
            "Reporting Period Start": summary_df["Start Date"],
            "Reporting Period End": summary_df["End Date"],
            "CO2 Removed (tonnes)": summary_df["Liquefied CO₂ (kg)"] / 1000,
            "Operational Emissions (tonnes CO2)": summary_df["Operational Emissions (kg)"] / 1000,
            "Embodied Emissions (tonnes CO2)": summary_df["Total Embodied (kg)"] / 1000,
            "Total Emissions (tonnes CO2)": summary_df["Total Emissions (kg)"] / 1000,
            "Net Removal (tonnes CO2)": summary_df["Net Removal (kg)"] / 1000,
            "Energy Intensity (kWh/tCO2)": summary_df["Energy Intensity (kWh/tCO₂)"],
            "Verification Status": "Pending",
        })
        
        st.dataframe(puro_df, width="stretch", hide_index=True)
        
        csv_puro = puro_df.to_csv(index=False).encode('utf-8')
        st.download_button(
            "📥 Download Puro.earth Format (CSV)",
            csv_puro,
            "octavia_puro_format.csv",
            "text/csv",
            width="stretch",
        )


if __name__ == "__main__":
    main()
