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
    emissions_breakdown_pie,
    energy_breakdown_chart,
    energy_intensity_chart,
    loss_analysis_chart,
    waterfall_chart,
)
from app.components.sidebar import render_module_filter, get_filter_display_name
from app.database.connection import get_session, init_db
from app.database.models import WeeklySummary
from app.services.aggregation import get_weekly_metrics_by_pair


def load_weekly_df(session, pair_filter: str = None) -> pd.DataFrame:
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
            
            # Liquefied is not pair-specific (it's from the combined bag)
            # Proportionally allocate based on bag contribution
            liq = w.liquefied_co2_kg or 0
            total_bag = w.total_bag_co2_kg or 0
            if liq > 0 and total_bag > 0:
                liq = liq * (bag / total_bag)  # Proportional allocation
            else:
                liq = 0
        else:
            # Use stored values and get energy breakdown from cycles
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
        # Always base total operational emissions on TOTAL energy,
        # then split between thermal and auxiliary so that:
        #   thermal_emissions + auxiliary_emissions == total_operational_emissions
        grid_ef = 0.049  # Default (overridden in config elsewhere)
        operational_emissions = total_energy * grid_ef

        if total_energy > 0:
            # Use actual auxiliary share if available, otherwise fall back to 30%
            aux_share = min(max(auxiliary_energy / total_energy, 0.0), 1.0) if auxiliary_energy > 0 else 0.30
            thermal_share = 1.0 - aux_share
        else:
            aux_share = 0.0
            thermal_share = 0.0

        auxiliary_emissions = operational_emissions * aux_share
        thermal_emissions = operational_emissions * thermal_share
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
            "srv_lrvp_kwh": srv_lrvp_kwh,
            "ct_kwh": ct_kwh,
            "fans_kwh": fans_kwh,
            "liquefaction_energy_kwh": liquefaction_kwh,
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
    
    # Render the Module pair filter in sidebar and get selected value
    pair_filter = render_module_filter()
    
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
        
        Embodied emissions are calculated using a fixed formula (see **⚙️ Configuration**).
        """)
        return

    # Week/Date Selector
    st.markdown("### 📅 Select Week")
    # Include cycle count in the week label so it's easy to reference a week by both calendar and cycles
    week_options = [
        f"{row['year']}-W{row['week_number']:02d} "
        f"({row['start_date'].strftime('%b %d')} - {row['end_date'].strftime('%b %d, %Y')}) "
        f"• {int(row['total_cycles']) if row['total_cycles'] is not None else 0} cycles"
        for _, row in df.iterrows()
    ]
    week_indices = list(range(len(week_options)))
    
    selector_col1, selector_col2 = st.columns([2, 1])
    with selector_col1:
        selected_idx = st.selectbox(
            "Choose a week to view:",
            options=week_indices,
            format_func=lambda x: week_options[x],
            index=len(week_options) - 1,  # Default to latest week
            key="week_selector"
        )
    with selector_col2:
        compare_previous = st.checkbox("Compare to previous week", value=False, key="compare_prev")
    
    selected_week = df.iloc[selected_idx]
    previous_week = df.iloc[selected_idx - 1] if selected_idx > 0 and compare_previous else None
    
    # Status indicator
    is_positive = selected_week["net_removal_kg"] > 0
    status_color = "#28A745" if is_positive else "#DC3545"
    status_text = "NET POSITIVE ✓" if is_positive else "NET NEGATIVE ✗"
    status_emoji = "🌱" if is_positive else "⚠️"

    # Key Metrics Row
    st.markdown("### 🎯 Key Performance Indicators")
    
    # Collected CO2 = liquefied if available, otherwise bag
    liq = selected_week['liquefied_co2_kg']
    bag = selected_week['total_bag_co2_kg']
    ads = selected_week['total_ads_co2_kg']
    collected_co2 = liq if liq > 0 else bag
    collected_label = "Liquefied CO₂" if liq > 0 else "Collected CO₂"
    
    # System losses = Adsorbed - Collected (cumulative losses)
    system_losses = ads - collected_co2
    
    # Calculate deltas if comparing to previous week
    def get_delta(current, previous, format_str="{:.1f}"):
        if previous is not None and previous > 0:
            change = current - previous
            pct_change = (change / previous) * 100
            return f"{format_str.format(change)} ({pct_change:+.1f}%)"
        return None
    
    col1, col2, col3, col4, col5 = st.columns(5)
    
    with col1:
        prev_net = previous_week['net_removal_kg'] if previous_week is not None else None
        delta_net = get_delta(selected_week['net_removal_kg'], prev_net) if compare_previous and prev_net is not None else f"Week {selected_week['week_number']}"
        st.metric(
            label="Net CO₂ Removal",
            value=f"{selected_week['net_removal_kg']:.1f} kg",
            delta=delta_net
        )
    
    with col2:
        prev_collected = (previous_week['liquefied_co2_kg'] if previous_week['liquefied_co2_kg'] > 0 else previous_week['total_bag_co2_kg']) if previous_week is not None else None
        delta_collected = get_delta(collected_co2, prev_collected) if compare_previous and prev_collected is not None else None
        st.metric(
            label=collected_label,
            value=f"{collected_co2:.1f} kg",
            delta=delta_collected,
            help="CO₂ ready for storage (liquefied if available, otherwise collected in bag)"
        )
    
    with col3:
        prev_op = previous_week['total_operational_emissions_kg'] if previous_week is not None else None
        delta_op = get_delta(selected_week['total_operational_emissions_kg'], prev_op) if compare_previous and prev_op is not None else None
        st.metric(
            label="Operational Emissions",
            value=f"{selected_week['total_operational_emissions_kg']:.1f} kg",
            delta=delta_op,
            help="Emissions from energy use - can be reduced with efficiency or geothermal"
        )
    
    with col4:
        prev_losses = (previous_week['total_ads_co2_kg'] - (previous_week['liquefied_co2_kg'] if previous_week['liquefied_co2_kg'] > 0 else previous_week['total_bag_co2_kg'])) if previous_week is not None else None
        delta_losses = get_delta(system_losses, prev_losses) if compare_previous and prev_losses is not None else None
        st.metric(
            label="System Losses",
            value=f"{system_losses:.1f} kg",
            delta=delta_losses,
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
    
    # Weekly Performance Summary Section
    st.divider()
    st.markdown("### 📊 Weekly Performance Summary")
    
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
        op_em = selected_week['total_operational_emissions_kg']
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
        emb_em = selected_week['total_embodied_emissions_kg']
        st.markdown(f"""
        <div style="background:#e0e0e0; padding:1.2rem; border-radius:10px; text-align:center; border:2px solid #9e9e9e;">
            <div style="font-size:0.75rem; color:#666; text-transform:uppercase; margin-bottom:0.5rem;">🏭 Embodied (Fixed)</div>
            <div style="font-size:2rem; font-weight:bold; color:#616161;">{emb_em:.1f}</div>
            <div style="font-size:0.8rem; color:#666;">kg CO₂/week</div>
        </div>
        """, unsafe_allow_html=True)
    
    # Net removal breakdown – use high-contrast colors so it is always readable
    net = selected_week['net_removal_kg']
    bar_bg = "#064e3b" if net > 0 else "#7f1d1d"  # dark green / dark red
    net_color = "#4ade80" if net > 0 else "#fca5a5"  # light green / light red
    st.markdown(f"""
    <div style="background:{bar_bg}; padding:1rem; border-radius:8px; margin-top:1rem;">
        <div style="text-align:center; color:#f9fafb;">
            <span style="font-size:1.05rem;">
                <strong>{collected_co2:.1f}</strong> kg collected 
                − <strong>{op_em:.1f}</strong> kg operational 
                − <strong>{emb_em:.1f}</strong> kg embodied 
                − <strong>{system_losses:.1f}</strong> kg losses
                = <strong style="color:{net_color};">{net:.1f} kg</strong> net removal
            </span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.divider()

    # CO2 Flow Section
    st.markdown("### 🔄 CO₂ Flow Analysis")
    
    flow_col1, flow_col2, flow_col3, flow_col4 = st.columns(4)
    
    with flow_col1:
        ads = selected_week["total_ads_co2_kg"]
        st.markdown(f"""
        <div style="background:#e8f5e9; padding:1rem; border-radius:8px; text-align:center; border-left:4px solid #4CAF50;">
            <div style="font-size:0.8rem; color:#666; text-transform:uppercase;">Adsorbed</div>
            <div style="font-size:1.8rem; font-weight:bold; color:#2e7d32;">{ads:.1f}</div>
            <div style="font-size:0.75rem; color:#888;">kg CO₂</div>
        </div>
        """, unsafe_allow_html=True)
    
    with flow_col2:
        des = selected_week["total_des_co2_kg"]
        eff1 = (des / ads * 100) if ads > 0 else 0
        st.markdown(f"""
        <div style="background:#fff3e0; padding:1rem; border-radius:8px; text-align:center; border-left:4px solid #FF9800;">
            <div style="font-size:0.8rem; color:#666; text-transform:uppercase;">Desorbed</div>
            <div style="font-size:1.8rem; font-weight:bold; color:#ef6c00;">{des:.1f}</div>
            <div style="font-size:0.75rem; color:#888;">{eff1:.1f}% of adsorbed</div>
        </div>
        """, unsafe_allow_html=True)
    
    with flow_col3:
        bag = selected_week["total_bag_co2_kg"]
        eff2 = (bag / des * 100) if des > 0 else 0
        st.markdown(f"""
        <div style="background:#e3f2fd; padding:1rem; border-radius:8px; text-align:center; border-left:4px solid #2196F3;">
            <div style="font-size:0.8rem; color:#666; text-transform:uppercase;">Collected</div>
            <div style="font-size:1.8rem; font-weight:bold; color:#1565c0;">{bag:.1f}</div>
            <div style="font-size:0.75rem; color:#888;">{eff2:.1f}% of desorbed</div>
        </div>
        """, unsafe_allow_html=True)
    
    with flow_col4:
        liq = selected_week["liquefied_co2_kg"]
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
    total_loss = selected_week["total_loss_kg"]
    if total_loss > 0:
        st.caption(f"⚠️ Total CO₂ lost this week: {total_loss:.1f} kg ({total_loss/ads*100:.1f}% of adsorbed)")

    st.divider()

    # Carbon Balance Waterfall Chart (removed tabs, only waterfall)
    st.markdown("### 💧 Carbon Balance")
    
    chart = waterfall_chart(
        collected_co2,  # Use collected (liquefied if available, else bag)
        selected_week["total_operational_emissions_kg"],
        selected_week["total_embodied_emissions_kg"],
    )
    if chart:
        st.plotly_chart(chart, width="stretch")

    st.divider()

    # Emissions & Energy Section
    st.markdown("### ⚡ Emissions & Energy Analysis")
    
    em_col1, em_col2 = st.columns(2)
    
    with em_col1:
        # Create a single-row DataFrame with selected week for pie chart
        selected_df = pd.DataFrame([selected_week])
        pie = emissions_breakdown_pie(selected_df)
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
