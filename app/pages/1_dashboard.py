import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import streamlit as st

from app.auth.authentication import require_login
from app.components.branding import get_brand_css, render_logo
from app.components.charts import (
    co2_flow_chart,
    cumulative_chart,
    emissions_breakdown_pie,
    energy_breakdown_chart,
    energy_intensity_chart,
    loss_analysis_chart,
    trend_chart,
    waterfall_chart,
)
from app.components.sidebar import render_nelion_filter, get_filter_display_name
from app.database.connection import get_session, init_db
from app.database.models import CycleData, WeeklySummary
from app.services.aggregation import aggregate_cycles_by_pair, get_weekly_metrics_by_pair
from app.services.calculations import classify_nelion_pair, get_pair_display_name


def load_weekly_df(session, pair_filter: str = None) -> pd.DataFrame:
    """Load weekly summary data, optionally filtered by Nelion pair."""
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
            
            # Skip weeks with no data for this pair
            if total_cycles == 0:
                continue
            
            # Liquefied is not pair-specific (it's from the combined bag)
            # Proportionally allocate based on bag contribution
            liq = w.liquefied_co2_kg or 0
            total_bag = w.total_bag_co2_kg or 0
            if liq > 0 and total_bag > 0:
                liq = liq * (bag / total_bag)  # Proportional allocation
            else:
                liq = 0
        else:
            # Use stored values
            liq = w.liquefied_co2_kg or 0
            bag = w.total_bag_co2_kg or 0
            ads = w.total_ads_co2_kg or 0
            des = w.total_des_co2_kg or 0
            total_energy = w.total_energy_kwh or 0
            total_cycles = w.total_cycles or 0
            thermal_energy = w.thermal_energy_kwh or 0
            auxiliary_energy = w.auxiliary_energy_kwh or 0
        
        # Collected CO2 = liquefied if available, otherwise bag
        collected_co2 = liq if liq > 0 else bag
        
        # Calculate energy intensity: total energy / collected CO2
        energy_intensity = (total_energy / (collected_co2 / 1000)) if (collected_co2 > 0 and total_energy > 0) else 0
        
        # Recalculate losses correctly:
        loss_stage_1 = ads - des
        loss_stage_2 = des - bag
        loss_stage_3 = (bag - liq) if liq > 0 else 0
        total_loss = ads - collected_co2
        
        # Proportional embodied emissions (if filtered)
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
        grid_ef = 0.049  # Default
        thermal_emissions = thermal_energy * grid_ef
        auxiliary_emissions = auxiliary_energy * grid_ef
        operational_emissions = total_energy * grid_ef
        total_emissions = operational_emissions + embodied
        
        # Net removal
        net_removal = collected_co2 - total_emissions
        
        rows.append({
            "year": w.year,
            "week_number": w.week_number,
            "week_label": f"{w.year}-W{w.week_number:02d}",
            "start_date": w.start_date,
            "end_date": w.end_date,
            "net_removal_kg": net_removal,
            "liquefied_co2_kg": liq,
            "total_emissions_kg": total_emissions,
            "thermal_emissions_kg": thermal_emissions,
            "auxiliary_emissions_kg": auxiliary_emissions,
            "total_embodied_emissions_kg": embodied,
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
            "total_energy_kwh": total_energy,
            "is_net_positive": net_removal > 0,
        })
    return pd.DataFrame(rows)


def main() -> None:
    st.set_page_config(page_title="Dashboard - Octavia CAS", page_icon="📊", layout="wide")
    init_db()
    if not require_login():
        return

    # Apply brand CSS
    st.markdown(get_brand_css(), unsafe_allow_html=True)
    
    # Sidebar with logo
    render_logo(location="sidebar")
    
    # Render the Nelion pair filter in sidebar and get selected value
    pair_filter = render_nelion_filter()
    
    session = get_session()
    try:
        df = load_weekly_df(session, pair_filter)
    finally:
        session.close()

    st.title("📊 Carbon Accounting Dashboard")
    
    # Show filter indicator
    if pair_filter:
        pair_name = get_filter_display_name(pair_filter)
        st.info(f"🔬 **Filtered View:** Showing data for **{pair_name}** only. Change filter in sidebar.")
    else:
        st.markdown("Real-time monitoring of CO₂ capture performance and net removal status")

    if df.empty:
        st.warning("⚠️ No weekly summaries yet.")
        st.info("""
        **To get started:**
        1. Go to **📥 Data Entry** and import SCADA cycle/energy CSVs
        2. Enter the weekly liquefied CO₂ amount
        3. Click "Save & Calculate Weekly Summary"
        
        **Optional but recommended:**
        - Go to **⚙️ Configuration** and import LCA embodied emissions data
        """)
        return

    latest = df.iloc[-1]
    
    # Status indicator
    is_positive = latest["net_removal_kg"] > 0
    status_color = "#28A745" if is_positive else "#DC3545"
    status_text = "NET POSITIVE ✓" if is_positive else "NET NEGATIVE ✗"
    status_emoji = "🌱" if is_positive else "⚠️"

    # Key Metrics Row
    st.markdown("### 🎯 Key Performance Indicators")
    
    # Collected CO2 = liquefied if available, otherwise bag
    liq = latest['liquefied_co2_kg']
    bag = latest['total_bag_co2_kg']
    ads = latest['total_ads_co2_kg']
    collected_co2 = liq if liq > 0 else bag
    collected_label = "Liquefied CO₂" if liq > 0 else "Collected CO₂"
    
    # System losses = Adsorbed - Collected (cumulative losses)
    system_losses = ads - collected_co2
    
    col1, col2, col3, col4, col5 = st.columns(5)
    
    with col1:
        st.metric(
            label="Net CO₂ Removal",
            value=f"{latest['net_removal_kg']:.1f} kg",
            delta=f"Week {latest['week_number']}"
        )
    
    with col2:
        st.metric(
            label=collected_label,
            value=f"{collected_co2:.1f} kg",
            help="CO₂ ready for storage (liquefied if available, otherwise collected in bag)"
        )
    
    with col3:
        st.metric(
            label="Operational Emissions",
            value=f"{latest['total_operational_emissions_kg']:.1f} kg",
            help="Emissions from energy use - can be reduced with efficiency or geothermal"
        )
    
    with col4:
        st.metric(
            label="System Losses",
            value=f"{system_losses:.1f} kg",
            help="CO₂ lost in process - can be reduced with better equipment/processes"
        )
    
    with col5:
        st.markdown(f"""
        <div style="
            background: {status_color};
            color: white;
            padding: 1rem;
            border-radius: 8px;
            text-align: center;
            font-weight: bold;
            font-size: 1.1rem;
        ">
            {status_emoji} {status_text}
        </div>
        """, unsafe_allow_html=True)
    
    # Controllable Factors Section
    st.divider()
    st.markdown("### ⚙️ Controllable Factors (Latest Week)")
    
    ctrl_col1, ctrl_col2, ctrl_col3, ctrl_col4 = st.columns(4)
    
    with ctrl_col1:
        st.markdown(f"""
        <div style="background:#e8f5e9; padding:1.2rem; border-radius:10px; text-align:center; border:2px solid #4CAF50;">
            <div style="font-size:0.75rem; color:#666; text-transform:uppercase; margin-bottom:0.5rem;">✅ Collected CO₂</div>
            <div style="font-size:2rem; font-weight:bold; color:#2e7d32;">{collected_co2:.1f}</div>
            <div style="font-size:0.8rem; color:#666;">kg</div>
        </div>
        """, unsafe_allow_html=True)
    
    with ctrl_col2:
        op_em = latest['total_operational_emissions_kg']
        st.markdown(f"""
        <div style="background:#fff3e0; padding:1.2rem; border-radius:10px; text-align:center; border:2px solid #FF9800;">
            <div style="font-size:0.75rem; color:#666; text-transform:uppercase; margin-bottom:0.5rem;">⚡ Operational Emissions</div>
            <div style="font-size:2rem; font-weight:bold; color:#ef6c00;">{op_em:.1f}</div>
            <div style="font-size:0.8rem; color:#666;">kg CO₂</div>
        </div>
        """, unsafe_allow_html=True)
    
    with ctrl_col3:
        st.markdown(f"""
        <div style="background:#ffebee; padding:1.2rem; border-radius:10px; text-align:center; border:2px solid #f44336;">
            <div style="font-size:0.75rem; color:#666; text-transform:uppercase; margin-bottom:0.5rem;">💨 System Losses</div>
            <div style="font-size:2rem; font-weight:bold; color:#c62828;">{system_losses:.1f}</div>
            <div style="font-size:0.8rem; color:#666;">kg CO₂</div>
        </div>
        """, unsafe_allow_html=True)
    
    with ctrl_col4:
        emb_em = latest['total_embodied_emissions_kg']
        st.markdown(f"""
        <div style="background:#e0e0e0; padding:1.2rem; border-radius:10px; text-align:center; border:2px solid #9e9e9e;">
            <div style="font-size:0.75rem; color:#666; text-transform:uppercase; margin-bottom:0.5rem;">🏭 Embodied (Fixed)</div>
            <div style="font-size:2rem; font-weight:bold; color:#616161;">{emb_em:.1f}</div>
            <div style="font-size:0.8rem; color:#666;">kg CO₂/week</div>
        </div>
        """, unsafe_allow_html=True)
    
    # Net removal breakdown
    net = latest['net_removal_kg']
    st.markdown(f"""
    <div style="background:{'#e8f5e9' if net > 0 else '#ffebee'}; padding:1rem; border-radius:8px; margin-top:1rem;">
        <div style="text-align:center;">
            <span style="font-size:1.1rem;">
                <strong>{collected_co2:.1f}</strong> kg collected 
                − <strong>{op_em:.1f}</strong> kg operational 
                − <strong>{emb_em:.1f}</strong> kg embodied 
                − <strong>{system_losses:.1f}</strong> kg losses
                = <strong style="color:{'#2e7d32' if net > 0 else '#c62828'};">{net:.1f} kg</strong> net removal
            </span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.divider()

    # CO2 Flow Section
    st.markdown("### 🔄 CO₂ Flow Analysis")
    
    flow_col1, flow_col2, flow_col3, flow_col4 = st.columns(4)
    
    with flow_col1:
        ads = latest["total_ads_co2_kg"]
        st.markdown(f"""
        <div style="background:#e8f5e9; padding:1rem; border-radius:8px; text-align:center; border-left:4px solid #4CAF50;">
            <div style="font-size:0.8rem; color:#666; text-transform:uppercase;">Adsorbed</div>
            <div style="font-size:1.8rem; font-weight:bold; color:#2e7d32;">{ads:.1f}</div>
            <div style="font-size:0.75rem; color:#888;">kg CO₂</div>
        </div>
        """, unsafe_allow_html=True)
    
    with flow_col2:
        des = latest["total_des_co2_kg"]
        eff1 = (des / ads * 100) if ads > 0 else 0
        st.markdown(f"""
        <div style="background:#fff3e0; padding:1rem; border-radius:8px; text-align:center; border-left:4px solid #FF9800;">
            <div style="font-size:0.8rem; color:#666; text-transform:uppercase;">Desorbed</div>
            <div style="font-size:1.8rem; font-weight:bold; color:#ef6c00;">{des:.1f}</div>
            <div style="font-size:0.75rem; color:#888;">{eff1:.1f}% of adsorbed</div>
        </div>
        """, unsafe_allow_html=True)
    
    with flow_col3:
        bag = latest["total_bag_co2_kg"]
        eff2 = (bag / des * 100) if des > 0 else 0
        st.markdown(f"""
        <div style="background:#e3f2fd; padding:1rem; border-radius:8px; text-align:center; border-left:4px solid #2196F3;">
            <div style="font-size:0.8rem; color:#666; text-transform:uppercase;">Collected</div>
            <div style="font-size:1.8rem; font-weight:bold; color:#1565c0;">{bag:.1f}</div>
            <div style="font-size:0.75rem; color:#888;">{eff2:.1f}% of desorbed</div>
        </div>
        """, unsafe_allow_html=True)
    
    with flow_col4:
        liq = latest["liquefied_co2_kg"]
        # Show liquefied if available, otherwise show collected (bag)
        if liq > 0:
            eff_total = (liq / ads * 100) if ads > 0 else 0
            st.markdown(f"""
            <div style="background:#e1f5fe; padding:1rem; border-radius:8px; text-align:center; border-left:4px solid #00BCD4;">
                <div style="font-size:0.8rem; color:#666; text-transform:uppercase;">Liquefied</div>
                <div style="font-size:1.8rem; font-weight:bold; color:#0277bd;">{liq:.1f}</div>
                <div style="font-size:0.75rem; color:#888;">{eff_total:.1f}% overall</div>
            </div>
            """, unsafe_allow_html=True)
        else:
            # No liquefaction - collected (bag) is the final stage
            eff_total = (bag / ads * 100) if ads > 0 else 0
            st.markdown(f"""
            <div style="background:#e1f5fe; padding:1rem; border-radius:8px; text-align:center; border-left:4px solid #00BCD4;">
                <div style="font-size:0.8rem; color:#666; text-transform:uppercase;">Collected (Final)</div>
                <div style="font-size:1.8rem; font-weight:bold; color:#0277bd;">{bag:.1f}</div>
                <div style="font-size:0.75rem; color:#888;">{eff_total:.1f}% overall</div>
            </div>
            """, unsafe_allow_html=True)

    # Loss indicator
    total_loss = latest["total_loss_kg"]
    if total_loss > 0:
        st.caption(f"⚠️ Total CO₂ lost this week: {total_loss:.1f} kg ({total_loss/ads*100:.1f}% of adsorbed)")

    st.divider()

    # Charts Section
    st.markdown("### 📈 Trend Analysis")
    
    chart_tab1, chart_tab2, chart_tab3, chart_tab4 = st.tabs([
        "Net Removal", "CO₂ Flow", "Cumulative", "Carbon Balance"
    ])
    
    with chart_tab1:
        chart = trend_chart(df.tail(12))
        if chart:
            st.plotly_chart(chart, width="stretch")
    
    with chart_tab2:
        chart = co2_flow_chart(df.tail(12))
        if chart:
            st.plotly_chart(chart, width="stretch")
    
    with chart_tab3:
        chart = cumulative_chart(df)
        if chart:
            st.plotly_chart(chart, width="stretch")
    
    with chart_tab4:
        chart = waterfall_chart(
            latest["liquefied_co2_kg"],
            latest["total_operational_emissions_kg"],
            latest["total_embodied_emissions_kg"],
        )
        if chart:
            st.plotly_chart(chart, width="stretch")

    st.divider()

    # Emissions & Energy Section
    st.markdown("### ⚡ Emissions & Energy Analysis")
    
    em_col1, em_col2 = st.columns(2)
    
    with em_col1:
        pie = emissions_breakdown_pie(df)
        if pie:
            st.plotly_chart(pie, width="stretch")
        else:
            st.info("No emissions data available")
    
    with em_col2:
        energy_chart = energy_breakdown_chart(df.tail(8))
        if energy_chart:
            st.plotly_chart(energy_chart, width="stretch")

    # Loss Analysis
    st.markdown("### 📉 Loss Analysis")
    
    loss_col1, loss_col2 = st.columns(2)
    
    with loss_col1:
        loss_chart = loss_analysis_chart(df.tail(8))
        if loss_chart:
            st.plotly_chart(loss_chart, width="stretch")
    
    with loss_col2:
        intensity_chart = energy_intensity_chart(df.tail(8))
        if intensity_chart:
            st.plotly_chart(intensity_chart, width="stretch")

    st.divider()
    
    # Nelion Pair Analysis Section - Only show comparison when not filtered
    if pair_filter:
        st.markdown("### 🔬 Nelion Pair Data")
        pair_name = "Nelion 1 & 3 🌟" if pair_filter == "1n3" else "Nelion 2 & 4"
        st.success(f"Currently viewing **{pair_name}** data only. Select 'All Nelions' in sidebar to see pair comparison.")
    else:
        st.markdown("### 🔬 Nelion Pair Performance Comparison")
        st.caption("Comparing Nelion pairs 1&3 (better sorbent) vs 2&4")
    
    session = get_session()
    try:
        pair_analysis = aggregate_cycles_by_pair(session)
    finally:
        session.close()
    
    p1 = pair_analysis["pair_data"]["1n3"]
    p2 = pair_analysis["pair_data"]["2n4"]
    comparison = pair_analysis["comparison"]
    
    if pair_filter:
        # Show only the selected pair's details
        selected_data = p1 if pair_filter == "1n3" else p2
        pair_label = "Nelion 1 & 3" if pair_filter == "1n3" else "Nelion 2 & 4"
        
        detail_cols = st.columns(4)
        with detail_cols[0]:
            st.metric("Total Cycles", selected_data["cycles"])
        with detail_cols[1]:
            st.metric("Collected CO₂", f"{selected_data['bag_co2_kg']:.1f} kg")
        with detail_cols[2]:
            st.metric("Overall Efficiency", f"{selected_data['overall_efficiency']:.1f}%")
        with detail_cols[3]:
            st.metric("Loss Rate", f"{selected_data['loss_rate']:.1f}%")
    
    elif p1["cycles"] > 0 or p2["cycles"] > 0:
        # Pair comparison metrics
        pair_col1, pair_col2 = st.columns(2)
        
        with pair_col1:
            eff_color_1 = "#2e7d32" if p1["overall_efficiency"] >= p2["overall_efficiency"] else "#666"
            st.markdown(f"""
            <div style="background:linear-gradient(135deg, #e8f5e9 0%, #c8e6c9 100%); padding:1.5rem; border-radius:12px; border:2px solid #4CAF50;">
                <div style="text-align:center; margin-bottom:1rem;">
                    <span style="font-size:1.5rem; font-weight:bold; color:#2e7d32;">🌟 Nelion 1 & 3</span>
                    <div style="font-size:0.85rem; color:#666;">Better Sorbent Material</div>
                </div>
                <div style="display:grid; grid-template-columns:1fr 1fr; gap:0.5rem;">
                    <div style="text-align:center; padding:0.5rem; background:rgba(255,255,255,0.7); border-radius:6px;">
                        <div style="font-size:0.7rem; color:#666;">Cycles</div>
                        <div style="font-size:1.3rem; font-weight:bold;">{p1['cycles']}</div>
                    </div>
                    <div style="text-align:center; padding:0.5rem; background:rgba(255,255,255,0.7); border-radius:6px;">
                        <div style="font-size:0.7rem; color:#666;">Efficiency</div>
                        <div style="font-size:1.3rem; font-weight:bold; color:{eff_color_1};">{p1['overall_efficiency']:.1f}%</div>
                    </div>
                    <div style="text-align:center; padding:0.5rem; background:rgba(255,255,255,0.7); border-radius:6px;">
                        <div style="font-size:0.7rem; color:#666;">Adsorbed</div>
                        <div style="font-size:1.1rem; font-weight:bold;">{p1['ads_co2_kg']:.1f} kg</div>
                    </div>
                    <div style="text-align:center; padding:0.5rem; background:rgba(255,255,255,0.7); border-radius:6px;">
                        <div style="font-size:0.7rem; color:#666;">Collected</div>
                        <div style="font-size:1.1rem; font-weight:bold;">{p1['bag_co2_kg']:.1f} kg</div>
                    </div>
                    <div style="text-align:center; padding:0.5rem; background:rgba(255,255,255,0.7); border-radius:6px;">
                        <div style="font-size:0.7rem; color:#666;">Loss Rate</div>
                        <div style="font-size:1.1rem; font-weight:bold; color:#c62828;">{p1['loss_rate']:.1f}%</div>
                    </div>
                    <div style="text-align:center; padding:0.5rem; background:rgba(255,255,255,0.7); border-radius:6px;">
                        <div style="font-size:0.7rem; color:#666;">kWh/kg CO₂</div>
                        <div style="font-size:1.1rem; font-weight:bold;">{p1['kwh_per_kg_co2']:.1f}</div>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)
        
        with pair_col2:
            eff_color_2 = "#1565c0" if p2["overall_efficiency"] > p1["overall_efficiency"] else "#666"
            st.markdown(f"""
            <div style="background:linear-gradient(135deg, #e3f2fd 0%, #bbdefb 100%); padding:1.5rem; border-radius:12px; border:2px solid #2196F3;">
                <div style="text-align:center; margin-bottom:1rem;">
                    <span style="font-size:1.5rem; font-weight:bold; color:#1565c0;">⚙️ Nelion 2 & 4</span>
                    <div style="font-size:0.85rem; color:#666;">Standard Sorbent</div>
                </div>
                <div style="display:grid; grid-template-columns:1fr 1fr; gap:0.5rem;">
                    <div style="text-align:center; padding:0.5rem; background:rgba(255,255,255,0.7); border-radius:6px;">
                        <div style="font-size:0.7rem; color:#666;">Cycles</div>
                        <div style="font-size:1.3rem; font-weight:bold;">{p2['cycles']}</div>
                    </div>
                    <div style="text-align:center; padding:0.5rem; background:rgba(255,255,255,0.7); border-radius:6px;">
                        <div style="font-size:0.7rem; color:#666;">Efficiency</div>
                        <div style="font-size:1.3rem; font-weight:bold; color:{eff_color_2};">{p2['overall_efficiency']:.1f}%</div>
                    </div>
                    <div style="text-align:center; padding:0.5rem; background:rgba(255,255,255,0.7); border-radius:6px;">
                        <div style="font-size:0.7rem; color:#666;">Adsorbed</div>
                        <div style="font-size:1.1rem; font-weight:bold;">{p2['ads_co2_kg']:.1f} kg</div>
                    </div>
                    <div style="text-align:center; padding:0.5rem; background:rgba(255,255,255,0.7); border-radius:6px;">
                        <div style="font-size:0.7rem; color:#666;">Collected</div>
                        <div style="font-size:1.1rem; font-weight:bold;">{p2['bag_co2_kg']:.1f} kg</div>
                    </div>
                    <div style="text-align:center; padding:0.5rem; background:rgba(255,255,255,0.7); border-radius:6px;">
                        <div style="font-size:0.7rem; color:#666;">Loss Rate</div>
                        <div style="font-size:1.1rem; font-weight:bold; color:#c62828;">{p2['loss_rate']:.1f}%</div>
                    </div>
                    <div style="text-align:center; padding:0.5rem; background:rgba(255,255,255,0.7); border-radius:6px;">
                        <div style="font-size:0.7rem; color:#666;">kWh/kg CO₂</div>
                        <div style="font-size:1.1rem; font-weight:bold;">{p2['kwh_per_kg_co2']:.1f}</div>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)
        
        # Comparison summary
        if p1["cycles"] > 0 and p2["cycles"] > 0:
            better_pair = "1n3" if p1["overall_efficiency"] > p2["overall_efficiency"] else "2n4"
            eff_diff = abs(p1["overall_efficiency"] - p2["overall_efficiency"])
            
            st.markdown(f"""
            <div style="background:#f5f5f5; padding:1rem; border-radius:8px; margin-top:1rem; text-align:center;">
                <strong>📊 Analysis:</strong> Nelion {"1&3" if better_pair == "1n3" else "2&4"} is performing 
                <strong style="color:#2e7d32;">{eff_diff:.1f}%</strong> better in overall efficiency. 
                1&3 contributes <strong>{comparison['1n3_co2_contribution']:.1f}%</strong> of collected CO₂, 
                2&4 contributes <strong>{comparison['2n4_co2_contribution']:.1f}%</strong>.
            </div>
            """, unsafe_allow_html=True)
        
        # Detailed comparison chart
        import plotly.graph_objects as go
        
        with st.expander("📊 Detailed Pair Comparison Charts", expanded=False):
            chart_col1, chart_col2 = st.columns(2)
            
            with chart_col1:
                # CO2 Flow comparison
                fig = go.Figure()
                categories = ["Adsorbed", "Desorbed", "Collected"]
                
                fig.add_trace(go.Bar(
                    name="Nelion 1&3",
                    x=categories,
                    y=[p1["ads_co2_kg"], p1["des_co2_kg"], p1["bag_co2_kg"]],
                    marker_color="#4CAF50",
                    text=[f"{v:.1f}" for v in [p1["ads_co2_kg"], p1["des_co2_kg"], p1["bag_co2_kg"]]],
                    textposition="outside",
                    textfont=dict(color="#f8fafc"),
                ))
                fig.add_trace(go.Bar(
                    name="Nelion 2&4",
                    x=categories,
                    y=[p2["ads_co2_kg"], p2["des_co2_kg"], p2["bag_co2_kg"]],
                    marker_color="#2196F3",
                    text=[f"{v:.1f}" for v in [p2["ads_co2_kg"], p2["des_co2_kg"], p2["bag_co2_kg"]]],
                    textposition="outside",
                    textfont=dict(color="#f8fafc"),
                ))
                
                fig.update_layout(
                    title="CO₂ Flow by Pair (kg)",
                    barmode="group",
                    template="plotly_dark",
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    font=dict(color="#f8fafc"),
                    height=350,
                    xaxis=dict(tickfont=dict(color="#e2e8f0")),
                    yaxis=dict(tickfont=dict(color="#e2e8f0")),
                )
                st.plotly_chart(fig, width="stretch")
            
            with chart_col2:
                # Efficiency comparison
                fig2 = go.Figure()
                
                fig2.add_trace(go.Bar(
                    name="Nelion 1&3",
                    x=["Ads→Des", "Des→Bag", "Overall"],
                    y=[p1["ads_to_des_efficiency"], p1["des_to_bag_efficiency"], p1["overall_efficiency"]],
                    marker_color="#4CAF50",
                    text=[f"{v:.1f}%" for v in [p1["ads_to_des_efficiency"], p1["des_to_bag_efficiency"], p1["overall_efficiency"]]],
                    textposition="outside",
                    textfont=dict(color="#f8fafc"),
                ))
                fig2.add_trace(go.Bar(
                    name="Nelion 2&4",
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
                    height=350,
                    yaxis_range=[0, 110],
                    xaxis=dict(tickfont=dict(color="#e2e8f0")),
                    yaxis=dict(tickfont=dict(color="#e2e8f0")),
                )
                st.plotly_chart(fig2, width="stretch")
            
            # Average per cycle comparison
            st.markdown("#### Average Performance Per Cycle")
            avg_df = pd.DataFrame({
                "Metric": ["Avg Adsorbed (kg)", "Avg Collected (kg)", "Avg Energy (kWh)"],
                "Nelion 1&3": [f"{p1['avg_ads_per_cycle']:.2f}", f"{p1['avg_bag_per_cycle']:.2f}", f"{p1['avg_kwh_per_cycle']:.1f}"],
                "Nelion 2&4": [f"{p2['avg_ads_per_cycle']:.2f}", f"{p2['avg_bag_per_cycle']:.2f}", f"{p2['avg_kwh_per_cycle']:.1f}"],
            })
            st.dataframe(avg_df, hide_index=True, width="stretch")
    else:
        st.info("No cycle data available for pair analysis. Import SCADA data to see Nelion pair comparison.")

    st.divider()

    # Weekly Summary Table
    st.markdown("### 📋 Weekly Summary Table")
    
    display_df = df.tail(12).copy()
    display_df = display_df[[
        "week_label", "total_cycles", "total_ads_co2_kg", "total_des_co2_kg",
        "total_bag_co2_kg", "liquefied_co2_kg", "total_loss_kg",
        "total_emissions_kg", "net_removal_kg", "is_net_positive"
    ]]
    display_df.columns = [
        "Week", "Cycles", "Adsorbed", "Desorbed", "Collected", "Liquefied",
        "Losses", "Emissions", "Net Removal", "Status"
    ]
    display_df["Status"] = display_df["Status"].apply(lambda x: "✅ Positive" if x else "❌ Negative")
    
    # Format numbers
    for col in ["Adsorbed", "Desorbed", "Collected", "Liquefied", "Losses", "Emissions", "Net Removal"]:
        display_df[col] = display_df[col].apply(lambda x: f"{x:.1f} kg")
    
    st.dataframe(
        display_df.sort_values("Week", ascending=False),
        width="stretch",
        hide_index=True,
    )


if __name__ == "__main__":
    main()
