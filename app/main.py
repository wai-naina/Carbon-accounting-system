"""Octavia Carbon Accounting System - Main Entry Point."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st

from app.auth.authentication import logout, require_login
from app.components.branding import render_logo, get_brand_css, render_header_with_logo
from app.components.sidebar import render_nelion_filter
from app.database.connection import get_session, init_db
from app.database.models import CycleData, WeeklySummary, EmbodiedInfrastructure, EmbodiedSorbent


def main() -> None:
    st.set_page_config(
        page_title="Octavia Carbon | CAS",
        page_icon="🌍",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    init_db()

    # Apply brand CSS
    st.markdown(get_brand_css(), unsafe_allow_html=True)

    if not require_login():
        return

    # Sidebar with logo and branding
    render_logo(location="sidebar", width=200)
    st.sidebar.markdown("---")
    st.sidebar.markdown(
        f"<div style='color: #94A3B8; font-size: 0.85rem;'>"
        f"👤 <strong style='color: #F1F5F9;'>{st.session_state.get('username', 'User')}</strong> "
        f"<span style='opacity: 0.7;'>| {st.session_state.get('role', 'user').title()}</span>"
        f"</div>",
        unsafe_allow_html=True
    )
    
    # Render the Nelion pair filter (shared component)
    render_nelion_filter()
    
    st.sidebar.markdown("---")
    
    if st.sidebar.button("🚪 Logout", use_container_width=True):
        logout()
        st.rerun()

    # Main content header
    render_header_with_logo()

    # Get summary stats
    session = get_session()
    try:
        total_cycles = session.query(CycleData).count()
        total_weeks = session.query(WeeklySummary).count()
        infra_items = session.query(EmbodiedInfrastructure).count()
        sorbent_batches = session.query(EmbodiedSorbent).count()
        
        # Get latest summary
        latest = session.query(WeeklySummary).order_by(
            WeeklySummary.year.desc(), WeeklySummary.week_number.desc()
        ).first()
        
        # Get cumulative stats
        from sqlalchemy import func
        cumulative = session.query(
            func.sum(WeeklySummary.liquefied_co2_kg),
            func.sum(WeeklySummary.total_bag_co2_kg),
            func.sum(WeeklySummary.total_emissions_kg),
            func.sum(WeeklySummary.net_removal_kg),
        ).first()
        
        total_liquefied = cumulative[0] or 0
        total_bag = cumulative[1] or 0
        total_captured = total_liquefied if total_liquefied > 0 else total_bag
        total_emissions = cumulative[2] or 0
        total_net = cumulative[3] or 0
    finally:
        session.close()

    # Key Metrics Row
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        status_class = "positive" if total_net > 0 else ("negative" if total_net < 0 else "neutral")
        net_icon = "🌱" if total_net > 0 else "⚠️"
        st.markdown(f"""
        <div class="metric-card {status_class}">
            <h3>{net_icon} Lifetime Net Removal</h3>
            <div class="value">{total_net:,.1f} kg</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown(f"""
        <div class="metric-card positive">
            <h3>♻️ Total CO₂ Captured</h3>
            <div class="value">{total_captured:,.1f} kg</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col3:
        st.markdown(f"""
        <div class="metric-card negative">
            <h3>⚡ Total Emissions</h3>
            <div class="value">{total_emissions:,.1f} kg</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col4:
        st.markdown(f"""
        <div class="metric-card info">
            <h3>📅 Weeks Tracked</h3>
            <div class="value">{total_weeks}</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("---")

    # Process Flow Visualization
    st.markdown('<div class="section-header">🔄 CO₂ Capture Process Flow</div>', unsafe_allow_html=True)
    
    if latest:
        ads = latest.total_ads_co2_kg or 0
        des = latest.total_des_co2_kg or 0
        bag = latest.total_bag_co2_kg or 0
        liq = latest.liquefied_co2_kg or 0
        
        flow_cols = st.columns([3, 1, 3, 1, 3, 1, 3])
        
        with flow_cols[0]:
            st.markdown(f"""
            <div class="flow-card adsorbed">
                <div class="icon">🌬️</div>
                <div class="label">Adsorbed</div>
                <div class="value">{ads:.1f} kg</div>
            </div>
            """, unsafe_allow_html=True)
        
        with flow_cols[1]:
            st.markdown('<div class="flow-arrow">➜</div>', unsafe_allow_html=True)
        
        with flow_cols[2]:
            st.markdown(f"""
            <div class="flow-card desorbed">
                <div class="icon">🔥</div>
                <div class="label">Desorbed</div>
                <div class="value">{des:.1f} kg</div>
            </div>
            """, unsafe_allow_html=True)
        
        with flow_cols[3]:
            st.markdown('<div class="flow-arrow">➜</div>', unsafe_allow_html=True)
        
        with flow_cols[4]:
            st.markdown(f"""
            <div class="flow-card collected">
                <div class="icon">🎈</div>
                <div class="label">Collected</div>
                <div class="value">{bag:.1f} kg</div>
            </div>
            """, unsafe_allow_html=True)
        
        with flow_cols[5]:
            st.markdown('<div class="flow-arrow">➜</div>', unsafe_allow_html=True)
        
        with flow_cols[6]:
            liq_class = "liquefied" if liq > 0 else "inactive"
            st.markdown(f"""
            <div class="flow-card {liq_class}">
                <div class="icon">❄️</div>
                <div class="label">Liquefied</div>
                <div class="value">{liq:.1f} kg</div>
            </div>
            """, unsafe_allow_html=True)
        
        st.caption(f"📅 Latest: {latest.year}-W{latest.week_number:02d} ({latest.start_date} to {latest.end_date})")
    else:
        st.markdown("""
        <div class="info-box warning">
            📭 <strong>No weekly data yet.</strong> Import SCADA data and enter liquefied CO₂ in Data Entry.
        </div>
        """, unsafe_allow_html=True)

    st.markdown("---")

    # Quick Navigation
    st.markdown('<div class="section-header">📋 Quick Navigation</div>', unsafe_allow_html=True)
    
    nav_col1, nav_col2, nav_col3 = st.columns(3)
    
    with nav_col1:
        st.markdown("""
        <div class="nav-card teal">
            <h3>📊 Dashboard</h3>
            <p>View KPIs, trends, and net removal status</p>
        </div>
        """, unsafe_allow_html=True)
    
    with nav_col2:
        st.markdown("""
        <div class="nav-card purple">
            <h3>📥 Data Entry</h3>
            <p>Import SCADA data and enter liquefied CO₂</p>
        </div>
        """, unsafe_allow_html=True)
    
    with nav_col3:
        st.markdown("""
        <div class="nav-card cyan">
            <h3>🔋 Energy Scenarios</h3>
            <p>Compare grid vs geothermal operations</p>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("---")

    # System Status
    st.markdown('<div class="section-header">⚙️ System Status</div>', unsafe_allow_html=True)
    
    status_col1, status_col2, status_col3, status_col4 = st.columns(4)
    
    with status_col1:
        st.metric("Cycles Imported", f"{total_cycles:,}")
    with status_col2:
        st.metric("Infrastructure Items", infra_items)
    with status_col3:
        st.metric("Sorbent Batches", sorbent_batches)
    with status_col4:
        if infra_items == 0 and sorbent_batches == 0:
            st.warning("⚠️ No LCA data")
        else:
            st.success("✅ LCA configured")


if __name__ == "__main__":
    main()
