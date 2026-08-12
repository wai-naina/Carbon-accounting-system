"""Shared sidebar components for all pages."""
from typing import Tuple

import streamlit as st


def render_module_filter() -> str:
    """
    Render the Module pair filter in the sidebar and return the selected filter value.
    
    Returns:
        str or None: "1n3", "2n4", or None for "all"
    """
    st.sidebar.markdown("""
    <div style="margin-top: 1rem; margin-bottom: 0.5rem;">
        <span style="font-size: 0.75rem; color: #6B7280; letter-spacing: 0.5px; text-transform: uppercase; font-weight: 500;">
            Data Filter
        </span>
    </div>
    """, unsafe_allow_html=True)
    
    pair_options = {
        "all": "All Modules (Combined)",
        "1n3": "Module 1 & 3",
        "2n4": "Module 2 & 4",
    }
    
    # Initialize session state if not exists
    if "module_pair_filter" not in st.session_state:
        st.session_state.module_pair_filter = "all"
    
    selected_pair = st.sidebar.radio(
        "View data for:",
        options=list(pair_options.keys()),
        format_func=lambda x: pair_options[x],
        key="module_pair_filter",
        help="Filter all dashboard and report data by Module pair",
        label_visibility="collapsed"
    )
    
    # Show filter indicator with custom styling
    if selected_pair != "all":
        pair_name = "Module 1 & 3" if selected_pair == "1n3" else "Module 2 & 4"
        st.sidebar.markdown(f"""
        <div style="
            background: #1A5F5F;
            color: white;
            padding: 0.5rem 0.75rem;
            border-radius: 4px;
            font-size: 0.875rem;
            margin-top: 0.5rem;
            text-align: center;
        ">
            Filtering: <strong>{pair_name}</strong>
        </div>
        """, unsafe_allow_html=True)
    
    # Return None for "all", otherwise return the pair
    return None if selected_pair == "all" else selected_pair


def get_filter_display_name(pair_filter: str, with_emoji: bool = False) -> str:
    """Get display name for the current filter."""
    if pair_filter == "1n3":
        return "Module 1 & 3"
    elif pair_filter == "2n4":
        return "Module 2 & 4"
    return "All Modules"


def render_filter_indicator(pair_filter: str) -> None:
    """Render a filter indicator banner in the main content area."""
    if pair_filter:
        pair_name = get_filter_display_name(pair_filter)
        st.markdown(f"""
        <div class="filter-badge">
            Filtered: <strong>{pair_name}</strong>
            <span style="opacity: 0.7; font-size: 0.75rem;">• Change in sidebar</span>
        </div>
        """, unsafe_allow_html=True)


def render_series_filter() -> str:
    """
    Render the Carbon Nest series filter (1n3 / 2n4) in the sidebar.

    Uses its own session-state key (cn_series_filter) so it never collides
    with the Miniplant 2.0 module_pair_filter.

    Returns:
        str or None: "1n3", "2n4", or None for "all"
    """
    st.sidebar.markdown("""
    <div style="margin-top: 1rem; margin-bottom: 0.5rem;">
        <span style="font-size: 0.75rem; color: #6B7280; letter-spacing: 0.5px; text-transform: uppercase; font-weight: 500;">
            Data Filter
        </span>
    </div>
    """, unsafe_allow_html=True)

    series_options = {
        "all": "All Series (Combined)",
        "1n3": "Series 1 & 3 (Group A)",
        "2n4": "Series 2 & 4 (Group B)",
    }

    if "cn_series_filter" not in st.session_state:
        st.session_state.cn_series_filter = "all"

    selected_series = st.sidebar.radio(
        "View data for:",
        options=list(series_options.keys()),
        format_func=lambda x: series_options[x],
        key="cn_series_filter",
        help="Filter Carbon Nest dashboard and report data by series. Per-Nelion "
        "filtering isn't available yet — SCADA can't distinguish Nelion 1 vs 2 "
        "on interleaved cycles.",
        label_visibility="collapsed",
    )

    if selected_series != "all":
        series_name = series_options[selected_series]
        st.sidebar.markdown(f"""
        <div style="
            background: #1A5F5F;
            color: white;
            padding: 0.5rem 0.75rem;
            border-radius: 4px;
            font-size: 0.875rem;
            margin-top: 0.5rem;
            text-align: center;
        ">
            Filtering: <strong>{series_name}</strong>
        </div>
        """, unsafe_allow_html=True)

    return None if selected_series == "all" else selected_series


# Preset supply scenarios, in kg CO2e/kWh — the unit grid_ef is stored and
# calculated in. Labels quote g/kWh instead, because that's the scale grid
# factors and PPA offers are actually published at, and 0.0579 vs 0.024 is
# harder to read at a glance than 57.9 vs 24.
ENERGY_SCENARIO_PRESETS = {
    "clean_24": 0.024,
    "zero": 0.0,
}


def render_energy_scenario(configured_ef: float) -> Tuple[float, str, bool]:
    """Sidebar what-if selector for the grid emission factor. Display only.

    Returns (ef_kg_per_kwh, label, is_scenario). `is_scenario` is False whenever
    the selection resolves back to the saved config value, so callers can leave
    the default view unmistakably "these are the real numbers" and only badge a
    page once a hypothetical factor is actually in play.

    Nothing here writes to system_config: switching supply changes what the page
    computes, never what's stored. Committing a new EF for real stays an Admin
    action, since that also requires recalculating the saved weekly summaries.
    """
    st.sidebar.markdown("""
    <div style="margin-top: 1.25rem; margin-bottom: 0.5rem;">
        <span style="font-size: 0.75rem; color: #6B7280; letter-spacing: 0.5px; text-transform: uppercase; font-weight: 500;">
            Energy Supply (what-if)
        </span>
    </div>
    """, unsafe_allow_html=True)

    scenario_labels = {
        "configured": f"As configured — {configured_ef * 1000:,.1f} g/kWh",
        "clean_24": "Cleaner supply — 24 g/kWh",
        "zero": "Zero-carbon supply — 0 g/kWh",
        "custom": "Custom…",
    }

    if "cn_energy_scenario" not in st.session_state:
        st.session_state.cn_energy_scenario = "configured"

    choice = st.sidebar.radio(
        "Assume this energy supply:",
        options=list(scenario_labels.keys()),
        format_func=lambda x: scenario_labels[x],
        key="cn_energy_scenario",
        help="Recomputes operational emissions — and so net removal and removal "
        "efficiency — at a different grid emission factor. Nothing is saved; the "
        "stored weekly summaries and the Home page keep showing actuals.",
        label_visibility="collapsed",
    )

    if choice == "custom":
        # Entered in g/kWh to match the labels above, converted back to the
        # kg/kWh that calculate_weekly_metrics() expects.
        custom_g_per_kwh = st.sidebar.number_input(
            "Grid EF (g CO₂e/kWh)",
            min_value=0.0,
            max_value=2000.0,
            value=float(round(configured_ef * 1000, 1)),
            step=1.0,
            key="cn_energy_scenario_custom",
        )
        ef = custom_g_per_kwh / 1000.0
    elif choice == "configured":
        ef = configured_ef
    else:
        ef = ENERGY_SCENARIO_PRESETS[choice]

    # Float tolerance rather than != so a custom entry typed back to the
    # configured value doesn't leave the page badged as a scenario.
    is_scenario = abs(ef - configured_ef) > 1e-9
    label = f"{ef * 1000:,.1f} g CO₂e/kWh"

    if is_scenario:
        st.sidebar.markdown(f"""
        <div style="
            background: #B45309;
            color: white;
            padding: 0.5rem 0.75rem;
            border-radius: 4px;
            font-size: 0.8125rem;
            margin-top: 0.5rem;
            text-align: center;
            line-height: 1.35;
        ">
            What-if: <strong>{label}</strong><br>
            <span style="opacity: 0.85; font-size: 0.75rem;">not saved</span>
        </div>
        """, unsafe_allow_html=True)

    return ef, label, is_scenario
