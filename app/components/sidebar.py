"""Shared sidebar components for all pages."""
import streamlit as st


def render_nelion_filter() -> str:
    """
    Render the Nelion pair filter in the sidebar and return the selected filter value.
    
    Returns:
        str or None: "1n3", "2n4", or None for "all"
    """
    st.sidebar.markdown("""
    <div style="margin-top: 1rem; margin-bottom: 0.5rem;">
        <span style="font-size: 0.8rem; color: #94A3B8; letter-spacing: 1px; text-transform: uppercase;">
            🔬 Data Filter
        </span>
    </div>
    """, unsafe_allow_html=True)
    
    pair_options = {
        "all": "🔄 All Nelions (Combined)",
        "1n3": "🌟 Nelion 1 & 3 (Better Sorbent)",
        "2n4": "⚙️ Nelion 2 & 4",
    }
    
    # Initialize session state if not exists
    if "nelion_pair_filter" not in st.session_state:
        st.session_state.nelion_pair_filter = "all"
    
    selected_pair = st.sidebar.radio(
        "View data for:",
        options=list(pair_options.keys()),
        format_func=lambda x: pair_options[x],
        key="nelion_pair_filter",
        help="Filter all dashboard and report data by Nelion pair",
        label_visibility="collapsed"
    )
    
    # Show filter indicator with custom styling
    if selected_pair != "all":
        pair_name = "Nelion 1 & 3" if selected_pair == "1n3" else "Nelion 2 & 4"
        st.sidebar.markdown(f"""
        <div style="
            background: linear-gradient(135deg, #1A5F5F 0%, #2D8F8F 100%);
            color: white;
            padding: 0.5rem 0.75rem;
            border-radius: 8px;
            font-size: 0.8rem;
            margin-top: 0.5rem;
            text-align: center;
        ">
            ✅ Filtering: <strong>{pair_name}</strong>
        </div>
        """, unsafe_allow_html=True)
    
    # Return None for "all", otherwise return the pair
    return None if selected_pair == "all" else selected_pair


def get_filter_display_name(pair_filter: str, with_emoji: bool = True) -> str:
    """Get display name for the current filter."""
    if pair_filter == "1n3":
        return "Nelion 1 & 3 (Better Sorbent)" if not with_emoji else "Nelion 1 & 3 🌟"
    elif pair_filter == "2n4":
        return "Nelion 2 & 4"
    return "All Nelions"


def render_filter_indicator(pair_filter: str) -> None:
    """Render a filter indicator banner in the main content area."""
    if pair_filter:
        pair_name = get_filter_display_name(pair_filter)
        st.markdown(f"""
        <div class="filter-badge">
            🔬 Filtered: <strong>{pair_name}</strong>
            <span style="opacity: 0.7; font-size: 0.75rem;">• Change in sidebar</span>
        </div>
        """, unsafe_allow_html=True)
