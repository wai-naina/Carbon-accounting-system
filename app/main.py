"""Octavia Carbon Accounting System - Main Entry Point."""
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
APP_DIR = Path(__file__).resolve().parent

import streamlit as st

from app.auth.authentication import logout, require_login
from app.components.branding import (
    render_logo,
    get_brand_css,
    render_header_with_logo,
    render_hero_metric,
    render_stat_tile,
)
from app.components.sidebar import render_module_filter
from app.database.connection import get_session, init_db
from app.database.models import CarbonNestCycleData, CarbonNestWeeklySummary, WeeklySummary
from app.services.carbon_nest_aggregation import get_carbon_nest_week_bounds
from app.services.carbon_nest_working_capacity import weekly_working_capacity_cached


def render_system_picker() -> None:
    """Post-login chooser between Miniplant 2.0 (archive) and Carbon Nest.

    Mirrors the SCADA historian (Athena) pattern: pick a system first, then
    everything downstream — nav, dashboard, reports — operates on that
    system's data only. Miniplant 2.0 and Carbon Nest are stored in fully
    separate tables, so there's no risk of cycle numbering or data mixing
    between them regardless of which is picked.
    """
    username = st.session_state.get("username", "User")
    st.markdown(
        f"""
        <div class="env-picker-header">
            <div class="env-picker-icon">🌍</div>
            <div class="env-picker-title">Select Plant Environment</div>
            <div class="env-picker-subtitle">Octavia Carbon &middot; Carbon Accounting System</div>
            <div class="env-user-pill">👤 {username}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.write("")

    col1, col2 = st.columns(2, gap="large")

    with col1:
        with st.container(key="picker_carbon_nest", border=True):
            st.markdown(
                """
                <div class="env-card-header active">
                    <div class="env-card-icon-badge">🌿</div>
                    <div>
                        <div class="env-card-title">Carbon Nest</div>
                        <span class="env-status-pill active">● ACTIVE PLANT</span>
                    </div>
                </div>
                <div class="env-card-desc">
                    Current data system — Nelion 1 &amp; 2 live. Real-time cycle capture, weekly
                    Athena reporting, and output-based embodied emissions.
                </div>
                <ul class="env-card-features">
                    <li>✓ Live cycle &amp; energy data</li>
                    <li>✓ Weekly data entry enabled</li>
                </ul>
                """,
                unsafe_allow_html=True,
            )
            if st.button("→ Enter Carbon Nest", key="pick_carbon_nest", width="stretch", type="primary"):
                st.session_state.data_system = "carbon_nest"
                st.rerun()

    with col2:
        with st.container(key="picker_miniplant", border=True):
            st.markdown(
                """
                <div class="env-card-header archive">
                    <div class="env-card-icon-badge">📦</div>
                    <div>
                        <div class="env-card-title">Miniplant 2.0</div>
                        <span class="env-status-pill archive">🔒 ARCHIVE</span>
                    </div>
                </div>
                <div class="env-card-desc">
                    Historical plant data preserved for reference and reporting. Read-only —
                    the original SCADA/data source, frozen as-is.
                </div>
                <ul class="env-card-features">
                    <li>🕐 Historical cycles &amp; trends</li>
                    <li>👁 Read-only access</li>
                </ul>
                """,
                unsafe_allow_html=True,
            )
            if st.button("📁 View Archive", key="pick_miniplant", width="stretch"):
                st.session_state.data_system = "miniplant"
                st.rerun()

    st.markdown("<div style='text-align:center; margin-top:1.5rem;'>", unsafe_allow_html=True)
    signout_col = st.columns([2, 1, 2])[1]
    with signout_col:
        if st.button("⏻ Sign out", key="picker_signout", width="stretch"):
            logout()
            st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)


def render_switch_system_control() -> None:
    st.sidebar.markdown("---")
    system_label = "🏭 Miniplant 2.0" if st.session_state.data_system == "miniplant" else "🌿 Carbon Nest"
    st.sidebar.markdown(
        f"<div style='color:#94A3B8;font-size:0.8rem;'>DATA SYSTEM</div>"
        f"<div style='color:#F1F5F9;font-weight:600;margin-bottom:0.5rem;'>{system_label}</div>",
        unsafe_allow_html=True,
    )
    if st.sidebar.button("🔀 Switch System", use_container_width=True):
        st.session_state.data_system = None
        st.rerun()


def _render_quick_nav(items: list) -> None:
    """Render working navigation cards. Each item is (path, title, icon, description)."""
    cols = st.columns(len(items))
    for col, (path, title, icon, description) in zip(cols, items):
        with col:
            with st.container(border=True):
                st.page_link(st.Page(path, title=title, icon=icon), width="stretch")
                st.caption(description)


def render_miniplant_home() -> None:
    render_header_with_logo()
    render_module_filter()

    session = get_session()
    try:
        total_weeks = session.query(WeeklySummary).count()
        latest = session.query(WeeklySummary).order_by(
            WeeklySummary.year.desc(), WeeklySummary.week_number.desc()
        ).first()

        from sqlalchemy import func
        cumulative = session.query(
            func.sum(WeeklySummary.total_ads_co2_kg),
            func.sum(WeeklySummary.total_des_co2_kg),
            func.sum(WeeklySummary.total_bag_co2_kg),
            func.sum(WeeklySummary.liquefied_co2_kg),
            func.sum(WeeklySummary.total_emissions_kg),
            func.sum(WeeklySummary.net_removal_kg),
        ).first()

        total_ads = (cumulative[0] or 0) if cumulative else 0
        total_des = (cumulative[1] or 0) if cumulative else 0
        total_bag = (cumulative[2] or 0) if cumulative else 0
        total_liquefied = (cumulative[3] or 0) if cumulative else 0
        total_emissions = (cumulative[4] or 0) if cumulative else 0
        total_net = (cumulative[5] or 0) if cumulative else 0

        liquefaction_weeks = (
            session.query(WeeklySummary)
            .filter(WeeklySummary.liquefied_co2_kg.isnot(None), WeeklySummary.liquefied_co2_kg > 0)
            .count()
        )
    finally:
        session.close()

    col1, col2, col3, col4 = st.columns(4)

    tracking_label = (
        f"Total across {total_weeks} tracked week{'s' if total_weeks != 1 else ''}"
        if total_weeks
        else "No weeks tracked yet"
    )

    with col1:
        status_class = "positive" if total_net > 0 else ("negative" if total_net < 0 else "neutral")
        net_icon = "🌱" if total_net > 0 else "⚠️"
        st.markdown(f"""
        <div class="metric-card {status_class}">
            <h3>{net_icon} Cumulative Net Removal</h3>
            <div class="value">{total_net:,.1f} kg</div>
            <div class="subtitle">{tracking_label}</div>
        </div>
        """, unsafe_allow_html=True)

    with col2:
        st.markdown(f"""
        <div class="metric-card positive">
            <h3>🎈 Total CO₂ Collected (Bag)</h3>
            <div class="value">{total_bag:,.1f} kg</div>
        </div>
        """, unsafe_allow_html=True)

    with col3:
        liquefied_label = (
            f"Tracked in {liquefaction_weeks} week{'s' if liquefaction_weeks != 1 else ''}"
            if total_liquefied > 0
            else "No liquefaction data yet"
        )
        st.markdown(f"""
        <div class="metric-card info">
            <h3>❄️ Total CO₂ Liquefied</h3>
            <div class="value">{total_liquefied:,.1f} kg</div>
            <div class="subtitle">{liquefied_label}</div>
        </div>
        """, unsafe_allow_html=True)

    with col4:
        st.markdown(f"""
        <div class="metric-card negative">
            <h3>⚡ Total Emissions</h3>
            <div class="value">{total_emissions:,.1f} kg</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("---")
    st.markdown('<div class="section-header">🔄 CO₂ Capture Process Flow</div>', unsafe_allow_html=True)

    if total_weeks > 0 and (total_ads > 0 or total_des > 0 or total_bag > 0 or total_liquefied > 0):
        ads, des, bag, liq = total_ads, total_des, total_bag, total_liquefied

        flow_cols = st.columns([3, 1, 3, 1, 3, 1, 3])
        with flow_cols[0]:
            st.markdown(f"""<div class="flow-card adsorbed"><div class="icon">🌬️</div><div class="label">Adsorbed</div><div class="value">{ads:.1f} kg</div></div>""", unsafe_allow_html=True)
        with flow_cols[1]:
            st.markdown('<div class="flow-arrow">➜</div>', unsafe_allow_html=True)
        with flow_cols[2]:
            st.markdown(f"""<div class="flow-card desorbed"><div class="icon">🔥</div><div class="label">Desorbed</div><div class="value">{des:.1f} kg</div></div>""", unsafe_allow_html=True)
        with flow_cols[3]:
            st.markdown('<div class="flow-arrow">➜</div>', unsafe_allow_html=True)
        with flow_cols[4]:
            st.markdown(f"""<div class="flow-card collected"><div class="icon">🎈</div><div class="label">Collected</div><div class="value">{bag:.1f} kg</div></div>""", unsafe_allow_html=True)
        with flow_cols[5]:
            st.markdown('<div class="flow-arrow">➜</div>', unsafe_allow_html=True)
        with flow_cols[6]:
            liq_class = "liquefied" if liq > 0 else "inactive"
            st.markdown(f"""<div class="flow-card {liq_class}"><div class="icon">❄️</div><div class="label">Liquefied</div><div class="value">{liq:.1f} kg</div></div>""", unsafe_allow_html=True)

        caption_parts = [f"📈 Cumulative totals across {total_weeks} tracked week{'s' if total_weeks != 1 else ''}."]
        if latest:
            caption_parts.append(f" Latest week: {latest.year}-W{latest.week_number:02d} ({latest.start_date} to {latest.end_date}).")
        if total_liquefied > 0 and liquefaction_weeks < total_weeks:
            caption_parts.append(f" Liquefied CO₂ data currently available for {liquefaction_weeks} of {total_weeks} weeks.")
        st.caption(" ".join(caption_parts))
    else:
        st.markdown("""
        <div class="info-box warning">
            📭 <strong>No weekly data yet.</strong> Import SCADA data and enter liquefied CO₂ in Data Entry.
        </div>
        """, unsafe_allow_html=True)

    st.markdown("---")
    st.markdown('<div class="section-header">📋 Quick Navigation</div>', unsafe_allow_html=True)
    nav_items = [
        (APP_DIR / "pages" / "1_dashboard.py", "Dashboard", "📊", "View KPIs, trends, and net removal status"),
        (APP_DIR / "pages" / "3_reports.py", "Reports", "📈", "Weekly reports and historical trends"),
        (APP_DIR / "pages" / "4_simulations.py", "Simulations", "🎲", "Compare grid vs geothermal scenarios"),
    ]
    if st.session_state.get("role") == "admin":
        nav_items.insert(1, (APP_DIR / "pages" / "2_data_entry.py", "Data Entry", "📥", "Import SCADA data and enter liquefied CO₂"))
    _render_quick_nav(nav_items)


def render_carbon_nest_home() -> None:
    render_header_with_logo()
    st.caption("Nelion 1 & 2 live · Athena weekly reporting · separate from Miniplant 2.0 history")

    session = get_session()
    try:
        latest_summary = (
            session.query(CarbonNestWeeklySummary)
            .order_by(CarbonNestWeeklySummary.start_date.desc())
            .first()
        )

        latest_cycle = (
            session.query(CarbonNestCycleData)
            .order_by(CarbonNestCycleData.start_time.desc())
            .first()
        )

        # Working capacity is a weekly-report metric, so anchor it on the most
        # recent COMPLETED Carbon Nest week (Sat-18:00 boundary), not on the
        # week containing the newest cycle: an export taken just after the
        # Saturday rollover carries the first cycle or two of a brand-new week,
        # and averaging those would present a 1-cycle figure as "the week".
        # Falls back to the in-progress week only when no completed week has
        # any cycles yet (fresh deployment).
        current_week_start, _ = get_carbon_nest_week_bounds(datetime.now())
        wc_anchor_cycle = (
            session.query(CarbonNestCycleData)
            .filter(CarbonNestCycleData.start_time < current_week_start)
            .order_by(CarbonNestCycleData.start_time.desc())
            .first()
        ) or latest_cycle
        working_capacity = weekly_working_capacity_cached(session, wc_anchor_cycle.start_time) if wc_anchor_cycle else None

        live_cycles = []
        if latest_cycle:
            week_start, week_end = get_carbon_nest_week_bounds(latest_cycle.start_time)
            live_cycles = (
                session.query(CarbonNestCycleData)
                .filter(
                    CarbonNestCycleData.start_time >= week_start,
                    CarbonNestCycleData.start_time < week_end,
                )
                .all()
            )
        live_ads = sum(c.ads_co2_kg or 0 for c in live_cycles)
        live_bag = sum(c.bag_co2_kg or 0 for c in live_cycles)
        live_steam = sum(c.steam_kg or 0 for c in live_cycles)
        collection_efficiency = (live_bag / live_ads * 100) if live_ads > 0 else None

        # Steam intensity (kg steam per tonne CO2 captured) needs the weekly
        # gross-captured figure, so like liquefaction efficiency it comes from
        # the most recently CALCULATED week rather than the live cycles.
        if latest_summary and latest_summary.gross_captured_kg:
            steam_intensity = (
                (latest_summary.total_steam_kg or 0) / (latest_summary.gross_captured_kg / 1000)
            )
        else:
            steam_intensity = None

        # Liquefaction is only ever recorded at the weekly-summary level (a manual
        # entry, not per-cycle), so unlike collection efficiency this can't be
        # computed "live" from this week's raw cycles — it uses the most recently
        # calculated week's own bag/liquefied figures instead.
        if latest_summary and latest_summary.total_bag_co2_kg:
            liquefaction_efficiency = (
                (latest_summary.liquefied_co2_kg or 0) / latest_summary.total_bag_co2_kg * 100
            )
        else:
            liquefaction_efficiency = None

        total_weeks = session.query(CarbonNestWeeklySummary).count()

        from sqlalchemy import func
        cumulative = session.query(
            func.sum(CarbonNestWeeklySummary.total_bag_co2_kg),
            func.sum(CarbonNestWeeklySummary.liquefied_co2_kg),
            func.sum(CarbonNestWeeklySummary.total_emissions_kg),
            func.sum(CarbonNestWeeklySummary.net_removal_kg),
            func.sum(CarbonNestWeeklySummary.total_steam_kg),
        ).first()

        total_bag = (cumulative[0] or 0) if cumulative else 0
        total_liquefied = (cumulative[1] or 0) if cumulative else 0
        total_emissions = (cumulative[2] or 0) if cumulative else 0
        total_net = (cumulative[3] or 0) if cumulative else 0
        total_steam = (cumulative[4] or 0) if cumulative else 0
    finally:
        session.close()

    # --- Hero: removal efficiency = (Captured - Emitted) / Captured, using the
    # most recently CALCULATED week's real gross captured CO2 and real total
    # emissions (metered operational + output-based embodied). This is the
    # same shape as the LCA workbook's own "capture efficiency" headline, but
    # driven by what actually happened this week rather than a fixed,
    # theoretical design-capacity scenario.
    st.markdown('<h2 class="section-header">🎯 Capture &amp; Removal Efficiency</h2>', unsafe_allow_html=True)

    gross_captured = latest_summary.gross_captured_kg if latest_summary else None
    if not latest_summary or not gross_captured:
        st.markdown("""
        <div class="info-box warning">
            📭 <strong>No calculated week yet.</strong> Import cycles and complete a weekly
            summary in Data Entry to see removal efficiency.
        </div>
        """, unsafe_allow_html=True)
    else:
        week_emissions = latest_summary.total_emissions_kg or 0
        week_net = latest_summary.net_removal_kg or 0
        removal_efficiency = week_net / gross_captured * 100
        eff_color = "#22C55E" if removal_efficiency > 0 else "#EF4444"
        hero_col1, hero_col2, hero_col3 = st.columns([2, 1, 1])
        with hero_col1:
            st.markdown(
                render_hero_metric(
                    "NET REMOVAL &divide; GROSS CAPTURED",
                    f"{removal_efficiency:+.1f}%",
                    eff_color,
                    f"Week of {latest_summary.start_date.strftime('%b %d')} &ndash; "
                    f"{latest_summary.end_date.strftime('%b %d, %Y')} &middot; real metered "
                    f"operational emissions + output-based embodied",
                ),
                unsafe_allow_html=True,
            )
        with hero_col2:
            st.markdown(f"""
            <div class="metric-card info">
                <h3>Gross Captured</h3>
                <div class="value">{gross_captured:,.1f} kg</div>
            </div>
            """, unsafe_allow_html=True)
        with hero_col3:
            st.markdown(f"""
            <div class="metric-card negative">
                <h3>Total Emissions</h3>
                <div class="value">{week_emissions:,.1f} kg</div>
            </div>
            """, unsafe_allow_html=True)
        st.caption(
            f"{gross_captured:.1f} kg captured − {week_emissions:.1f} kg emitted = "
            f"{week_net:+.1f} kg net removal → {removal_efficiency:+.1f}% of what was captured."
        )

    st.markdown("---")

    # --- Secondary: process efficiencies + cumulative mass totals ---
    st.markdown('<h2 class="section-header">📊 Operational &amp; Cumulative Figures</h2>', unsafe_allow_html=True)
    st.caption(
        "Collection and Liquefaction Efficiency are pure process measurements — they don't "
        "touch emissions. Collection Efficiency reflects this week's live cycles; Liquefaction "
        "Efficiency reflects the most recently calculated week (liquefaction is only ever "
        "logged at the weekly level)."
    )

    tile_col1, tile_col2, tile_col3, tile_col4 = st.columns(4)
    with tile_col1:
        st.markdown(
            render_stat_tile(
                "🔄", "teal", "Collection Efficiency",
                f"{collection_efficiency:.1f}%" if collection_efficiency is not None else "—",
                "Collected ÷ Adsorbed, this week",
            ),
            unsafe_allow_html=True,
        )
    with tile_col2:
        st.markdown(
            render_stat_tile(
                "❄️", "blue", "Liquefaction Efficiency",
                f"{liquefaction_efficiency:.1f}%" if liquefaction_efficiency is not None else "—",
                "Liquefied ÷ Collected, latest week",
            ),
            unsafe_allow_html=True,
        )
    with tile_col3:
        st.markdown(
            render_stat_tile("🎈", "green", "Total CO₂ Collected", f"{total_bag:,.1f} kg"),
            unsafe_allow_html=True,
        )
    with tile_col4:
        st.markdown(
            render_stat_tile("💧", "purple", "Total CO₂ Liquefied", f"{total_liquefied:,.1f} kg"),
            unsafe_allow_html=True,
        )

    # --- Desorption steam: the input that releases captured CO2 from the
    # sorbent bed. Steam Used reflects this week's live cycles (like Collection
    # Efficiency); Steam Intensity reflects the most recently calculated week
    # (it needs the weekly gross-captured denominator, like Liquefaction
    # Efficiency); Total Steam is cumulative across all tracked weeks.
    steam_col1, steam_col2, steam_col3 = st.columns(3)
    with steam_col1:
        st.markdown(
            render_stat_tile(
                "💨", "blue", "Steam Used",
                f"{live_steam:,.0f} kg",
                "Desorption steam, this week's cycles",
            ),
            unsafe_allow_html=True,
        )
    with steam_col2:
        st.markdown(
            render_stat_tile(
                "🌡️", "amber", "Steam Intensity",
                f"{steam_intensity:,.0f} kg/t CO₂" if steam_intensity else "—",
                "Steam per tonne captured, latest calculated week",
            ),
            unsafe_allow_html=True,
        )
    with steam_col3:
        st.markdown(
            render_stat_tile(
                "♨️", "teal", "Total Steam Used",
                f"{total_steam:,.0f} kg",
                "Cumulative across all tracked weeks",
            ),
            unsafe_allow_html=True,
        )

    if total_weeks:
        st.caption(
            f"Cumulative across {total_weeks} tracked week{'s' if total_weeks != 1 else ''}: "
            f"{total_net:,.1f} kg net removal · {total_emissions:,.1f} kg total emissions."
        )
    else:
        st.markdown("""
        <div class="info-box warning" style="margin-top:1rem;">
            📭 <strong>No weekly summaries yet.</strong> Once cycles are imported, calculate a weekly summary in Data Entry to see these figures.
        </div>
        """, unsafe_allow_html=True)

    st.markdown("---")

    # --- Sorbent working capacity: desorption-based material-science metric,
    # reproducing an existing hand-calculated report. Not a percentage, not
    # normalised for hold time — see weekly_working_capacity() docstrings.
    st.markdown('<h2 class="section-header">🧪 Sorbent Working Capacity</h2>', unsafe_allow_html=True)
    wc_caption = (
        "Desorption-based sorbent capacity — mol CO&#8322; released per m&#179; of bed, "
        "averaged across the reporting week's valid cycles. Not adsorption uptake, not "
        "normalised for hold time."
    )
    if working_capacity:
        wc_caption += (
            f" Reporting week: {working_capacity['week_start'].strftime('%b %d, %H:%M')} → "
            f"{working_capacity['week_end'].strftime('%b %d, %Y %H:%M')} "
            "(most recent completed week with cycle data)."
        )
    st.caption(wc_caption)
    if not working_capacity:
        st.markdown('<div class="info-box warning">📭 <strong>No cycle data yet.</strong> Import cycles in Data Entry to see working capacity.</div>', unsafe_allow_html=True)
    else:
        wc_col1, wc_col2 = st.columns(2)
        for col, group_key in zip((wc_col1, wc_col2), ("A", "B")):
            with col:
                group = working_capacity["groups"][group_key]
                capacity = group["avg_working_capacity_mol_per_m3"]
                value_str = f"{capacity:.2f} mol/m³" if capacity is not None else "—"
                sub = (
                    f"{group['n_cycles_used']} of {group['n_cycles_in_window']} cycles · "
                    f"week of {working_capacity['week_start'].strftime('%b %d')}"
                )
                st.markdown(
                    render_stat_tile(
                        "🧪", "teal" if group_key == "A" else "purple",
                        group["label"], value_str, sub,
                    ),
                    unsafe_allow_html=True,
                )
                if group["config_anomalies"]:
                    bad_cycles = ", ".join(str(a["cycle_number"]) for a in group["config_anomalies"])
                    st.caption(f"⚠️ cycle {bad_cycles} has an unusual implied bed volume — check sorbent config")

    st.markdown("---")
    st.markdown('<h2 class="section-header">📋 Quick Navigation</h2>', unsafe_allow_html=True)
    nav_items = [
        (APP_DIR / "pages" / "cn_dashboard.py", "Dashboard", "📊", "View KPIs, trends, and net removal status"),
        (APP_DIR / "pages" / "cn_reports.py", "Reports", "📈", "Weekly reports and historical trends"),
        (APP_DIR / "pages" / "cn_embodied.py", "Embodied Emissions", "🏗️", "See the output-based embodied breakdown"),
    ]
    if st.session_state.get("role") == "admin":
        nav_items.insert(1, (APP_DIR / "pages" / "cn_data_entry.py", "Data Entry", "📥", "Import Carbon Nest CSV exports"))
    _render_quick_nav(nav_items)


def build_pages(system: str) -> list:
    role = st.session_state.get("role", "user")
    is_admin = role == "admin"

    if system == "miniplant":
        pages = [
            st.Page(render_miniplant_home, title="Home", icon="🏠", default=True),
            st.Page(APP_DIR / "pages" / "1_dashboard.py", title="Dashboard", icon="📊"),
            st.Page(APP_DIR / "pages" / "3_reports.py", title="Reports", icon="📈"),
            st.Page(APP_DIR / "pages" / "4_simulations.py", title="Simulations", icon="🎲"),
        ]
        if is_admin:
            pages.append(st.Page(APP_DIR / "pages" / "2_data_entry.py", title="Data Entry", icon="📥"))
            pages.append(st.Page(APP_DIR / "pages" / "6_admin.py", title="Admin", icon="👥"))
        return pages

    # carbon_nest
    pages = [
        st.Page(render_carbon_nest_home, title="Home", icon="🏠", default=True),
        st.Page(APP_DIR / "pages" / "cn_dashboard.py", title="Dashboard", icon="📊"),
        st.Page(APP_DIR / "pages" / "cn_reports.py", title="Reports", icon="📈"),
        st.Page(APP_DIR / "pages" / "cn_embodied.py", title="Embodied Emissions", icon="🏗️"),
    ]
    if is_admin:
        pages.append(st.Page(APP_DIR / "pages" / "cn_data_entry.py", title="Data Entry", icon="📥"))
        pages.append(st.Page(APP_DIR / "pages" / "6_admin.py", title="Admin", icon="👥"))
    return pages


def main() -> None:
    st.set_page_config(
        page_title="Octavia Carbon | CAS",
        page_icon="🌍",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    init_db()

    st.markdown(get_brand_css(), unsafe_allow_html=True)

    if not st.session_state.get("authenticated", False):
        # Always route through st.navigation(), even for the login screen —
        # same reasoning as the picker below: otherwise Streamlit falls back
        # to auto-discovering app/pages/*.py, leaking every page's name into
        # the sidebar before anyone's even logged in.
        login_page = st.Page(require_login, title="Login", icon="🔒", default=True)
        pg = st.navigation([login_page], position="hidden")
        pg.run()
        return

    render_logo(location="sidebar", width=200)
    st.sidebar.markdown("---")
    st.sidebar.markdown(
        f"<div style='color: #94A3B8; font-size: 0.85rem;'>"
        f"👤 <strong style='color: #F1F5F9;'>{st.session_state.get('username', 'User')}</strong> "
        f"<span style='opacity: 0.7;'>| {st.session_state.get('role', 'user').title()}</span>"
        f"</div>",
        unsafe_allow_html=True,
    )

    if "data_system" not in st.session_state:
        st.session_state.data_system = None

    if st.session_state.data_system is None:
        # Sign out lives in the picker's own main content (matching Athena's
        # layout) — no need to duplicate it in the sidebar for this screen.
        # Always route through st.navigation(), even for the picker screen —
        # otherwise Streamlit falls back to auto-discovering app/pages/*.py,
        # which would leak both systems' pages into the sidebar before a
        # system has even been chosen.
        picker_page = st.Page(render_system_picker, title="Choose System", icon="🔀", default=True)
        pg = st.navigation([picker_page], position="hidden")
        pg.run()
        return

    render_switch_system_control()

    if st.sidebar.button("🚪 Logout", use_container_width=True, key="logout_button"):
        logout()
        st.rerun()

    pages = build_pages(st.session_state.data_system)
    pg = st.navigation(pages)
    pg.run()


if __name__ == "__main__":
    main()
