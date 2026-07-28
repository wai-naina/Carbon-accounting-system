"""Branding components for Octavia Carbon CAS - matching octaviacarbon.com design."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import streamlit as st


LOGO_CANDIDATES = [
    "assets/octavia_logo.png",
    "assets/octavia_logo.jpg",
    "assets/octavia_logo.jpeg",
    "assets/octavia_logo.svg",
    "assets/Octavia Logo White.png",
    "assets/Octavia_Logo_White.png",
]

# Octavia Carbon brand colors (from octaviacarbon.com)
BRAND_COLORS = {
    "primary": "#1A5F5F",         # Dark teal (main brand color)
    "primary_light": "#2D8F8F",   # Lighter teal
    "accent": "#3DB3B3",          # Accent teal
    "dark": "#0D3B3B",            # Very dark teal
    "darker": "#071F1F",          # Almost black teal
    "light": "#E8F4F4",           # Light teal bg
    "white": "#FFFFFF",
    "text_light": "#F1F5F9",
    "text_muted": "#94A3B8",
    "success": "#22C55E",
    "warning": "#F59E0B", 
    "danger": "#EF4444",
    "info": "#0EA5E9",
}


def get_logo_path() -> Optional[Path]:
    """Return the first logo path found in the assets folder."""
    root = Path(__file__).resolve().parents[2]
    for rel_path in LOGO_CANDIDATES:
        path = root / rel_path
        if path.exists():
            return path
    return None


def render_logo(location: str = "sidebar", width: int = 180) -> None:
    """Render the Octavia Carbon logo if present."""
    logo_path = get_logo_path()
    
    if logo_path:
        if location == "sidebar":
            st.sidebar.image(str(logo_path), width=width)
        else:
            st.image(str(logo_path), width=width)
    else:
        # Fallback text-based logo if no image found
        if location == "sidebar":
            st.sidebar.markdown("""
            <div style="padding: 10px 0; text-align: center;">
                <div style="font-size: 1rem; font-weight: 600; color: #3DB3B3; letter-spacing: 1px;">OCTAVIA</div>
                <div style="font-size: 1rem; font-weight: 600; color: #3DB3B3; letter-spacing: 1px;">CARBON</div>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown("""
            <div style="margin-bottom: 1rem;">
                <span style="font-size: 2rem; font-weight: 300; color: #3DB3B3; letter-spacing: 4px;">OCTAVIA</span>
                <span style="font-size: 2rem; font-weight: 300; color: #3DB3B3; letter-spacing: 4px; margin-left: 10px;">CARBON</span>
            </div>
            """, unsafe_allow_html=True)


def render_stat_tile(icon: str, color: str, label: str, value: str, sub: str = "") -> str:
    """Compact icon + label + value KPI tile (Athena-inspired). Returns HTML for st.markdown.

    Built as a single line deliberately: a blank (or whitespace-only) line inside an
    unsafe_allow_html block ends Streamlit/CommonMark's raw-HTML-block parsing early,
    so any indented lines after it (like the closing </div>s) get re-parsed as an
    indented code block and rendered as literal text instead of markup.
    """
    sub_html = f'<div class="stat-tile-sub">{sub}</div>' if sub else ""
    return (
        f'<div class="stat-tile">'
        f'<div class="stat-tile-icon {color}">{icon}</div>'
        f'<div>'
        f'<div class="stat-tile-label">{label}</div>'
        f'<div class="stat-tile-value">{value}</div>'
        f'{sub_html}'
        f'</div>'
        f'</div>'
    )


def render_hero_metric(label: str, value: str, color: str, sub: str = "") -> str:
    """The single headline figure a page leads with. Returns HTML for st.markdown.

    Single line for the same reason as render_stat_tile above — avoids a blank-line
    HTML-block termination bug in Streamlit's markdown renderer.
    """
    sub_html = f'<div class="hero-metric-sub">{sub}</div>' if sub else ""
    return (
        f'<div class="hero-metric">'
        f'<div class="hero-metric-label">{label}</div>'
        f'<div class="hero-metric-value" style="color:{color};">{value}</div>'
        f'{sub_html}'
        f'</div>'
    )


def render_header_with_logo() -> None:
    """Render a professional header for dark theme."""
    st.markdown("""
    <div style="margin-bottom: 2rem;">
        <h1 style="
            font-size: 2rem;
            font-weight: 600;
            color: #F1F5F9;
            margin: 0 0 0.5rem 0;
            font-family: 'Inter', 'Segoe UI', sans-serif;
        ">
            Carbon Accounting System
        </h1>
        <p style="
            color: #94A3B8;
            font-size: 0.875rem;
            margin: 0;
            font-weight: 400;
        ">
            Direct Air Capture • Project Hummingbird Phase 1 • Gilgil, Kenya
        </p>
    </div>
    """, unsafe_allow_html=True)


def get_brand_css() -> str:
    """Return CSS styles for professional dark theme design."""
    return """
    <style>
    /* Import Inter font */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
    
    /* Global styles - Dark theme */
    .stApp {
        font-family: 'Inter', 'Segoe UI', -apple-system, sans-serif;
        background-color: #0F172A !important;
    }
    
    .main .block-container {
        background-color: #0F172A !important;
        padding-top: 2rem;
        padding-bottom: 2rem;
    }
    
    /* Hide default Streamlit branding.
       Note: header/[data-testid="stHeader"] is intentionally NOT hidden —
       it's also the container Streamlit renders the sidebar's
       expand/collapse control (stExpandSidebarButton) into. Hiding the
       whole header makes that control invisible AND unclickable, which
       permanently traps a collapsed sidebar with no way to reopen it.
       Instead we keep the header itself but make it blend into the dark
       theme, and hide only the specific chrome elements we don't want. */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    [data-testid="stHeader"] {
        background: transparent !important;
        box-shadow: none !important;
    }
    [data-testid="stToolbar"] {visibility: hidden;}
    [data-testid="stDecoration"] {display: none;}
    [data-testid="stDeployButton"] {display: none;}
    [data-testid="stStatusWidget"] {display: none !important;}
    [data-testid="manage-app-button"] {display: none !important;}
    [data-testid="stExpandSidebarButton"] {
        visibility: visible !important;
        opacity: 1 !important;
        pointer-events: auto !important;
    }
    .viewerBadge_container__r5tak {display: none !important;}
    .viewerBadge_link__qRIco {display: none !important;}
    #stDecoration {display: none !important;}
    a[href="https://streamlit.io/cloud"] {display: none !important;}
    div[class*="viewerBadge"] {display: none !important;}
    
    /* Custom scrollbar - Dark theme */
    ::-webkit-scrollbar {
        width: 8px;
        height: 8px;
    }
    ::-webkit-scrollbar-track {
        background: #1E293B;
    }
    ::-webkit-scrollbar-thumb {
        background: #475569;
        border-radius: 4px;
    }
    ::-webkit-scrollbar-thumb:hover {
        background: #64748B;
    }
    
    /* Sidebar styling - Dark theme */
    [data-testid="stSidebar"] {
        background: #1E293B !important;
        border-right: 1px solid #334155 !important;
    }
    
    [data-testid="stSidebar"] .stMarkdown {
        color: #F1F5F9 !important;
    }
    
    [data-testid="stSidebar"] hr {
        border-color: #334155 !important;
    }
    
    /* Metric cards - Dark theme */
    .metric-card {
        background: #1E293B;
        border-radius: 6px;
        padding: 1.25rem;
        border: 1px solid #334155;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.3);
        position: relative;
    }
    
    .metric-card::before {
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        height: 3px;
        background: #3DB3B3;
    }
    
    .metric-card h3 {
        font-size: 0.75rem;
        color: #94A3B8;
        margin-bottom: 0.5rem;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        font-weight: 500;
    }
    
    .metric-card .value {
        font-size: 1.75rem;
        font-weight: 600;
        color: #F1F5F9;
    }
    
    /* Card variants */
    .metric-card.positive::before { background: #22C55E; }
    .metric-card.positive .value { color: #22C55E; }
    
    .metric-card.negative::before { background: #EF4444; }
    .metric-card.negative .value { color: #EF4444; }
    
    .metric-card.neutral::before { background: #3DB3B3; }
    .metric-card.neutral .value { color: #3DB3B3; }
    
    .metric-card.info::before { background: #0EA5E9; }
    .metric-card.info .value { color: #0EA5E9; }
    
    /* Process flow cards - Dark theme */
    .flow-card {
        text-align: center;
        padding: 1.25rem 1rem;
        border-radius: 6px;
        border: 1px solid;
        background: #1E293B;
    }
    
    .flow-card .icon {
        font-size: 1.5rem;
        margin-bottom: 0.5rem;
    }
    
    .flow-card .label {
        font-size: 0.7rem;
        font-weight: 500;
        letter-spacing: 0.5px;
        text-transform: uppercase;
        margin-bottom: 0.5rem;
        color: #94A3B8;
    }
    
    .flow-card .value {
        font-size: 1.5rem;
        font-weight: 600;
        color: #F1F5F9;
    }
    
    .flow-card.adsorbed {
        background: #1E3A2E;
        border-color: #22C55E;
    }
    .flow-card.adsorbed .label { color: #86EFAC; }
    .flow-card.adsorbed .value { color: #22C55E; }
    
    .flow-card.desorbed {
        background: #3A2E1E;
        border-color: #F59E0B;
    }
    .flow-card.desorbed .label { color: #FCD34D; }
    .flow-card.desorbed .value { color: #F59E0B; }
    
    .flow-card.collected {
        background: #1E293B;
        border-color: #3B82F6;
    }
    .flow-card.collected .label { color: #93C5FD; }
    .flow-card.collected .value { color: #3B82F6; }
    
    .flow-card.liquefied {
        background: #1E293B;
        border-color: #06B6D4;
    }
    .flow-card.liquefied .label { color: #67E8F9; }
    .flow-card.liquefied .value { color: #06B6D4; }
    
    .flow-card.inactive {
        background: #1E293B;
        border-color: #475569;
    }
    .flow-card.inactive .label { color: #64748B; }
    .flow-card.inactive .value { color: #64748B; }
    
    /* Flow arrow - Dark theme */
    .flow-arrow {
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 1.25rem;
        color: #94A3B8;
    }
    
    /* Navigation cards - Dark theme */
    .nav-card {
        padding: 1.25rem;
        border-radius: 6px;
        border: 1px solid #334155;
        background: #1E293B;
    }
    
    .nav-card h3 {
        margin: 0 0 0.5rem 0;
        color: #F1F5F9;
        font-weight: 600;
        font-size: 1rem;
    }
    
    .nav-card p {
        color: #94A3B8;
        margin: 0;
        font-size: 0.875rem;
        font-weight: 400;
    }
    
    .nav-card.teal { border-left: 3px solid #1A5F5F; }
    .nav-card.purple { border-left: 3px solid #7C3AED; }
    .nav-card.cyan { border-left: 3px solid #0891B2; }
    .nav-card.emerald { border-left: 3px solid #059669; }
    .nav-card.orange { border-left: 3px solid #EA580C; }
    
    /* Buttons - Dark theme */
    .stButton > button {
        background: #3DB3B3 !important;
        color: #0F172A !important;
        border: none !important;
        border-radius: 4px !important;
        padding: 0.5rem 1.25rem !important;
        font-weight: 500 !important;
        transition: background-color 0.2s ease !important;
    }
    
    .stButton > button:hover {
        background: #2D8F8F !important;
        color: white !important;
    }
    
    /* Sidebar buttons */
    [data-testid="stSidebar"] .stButton > button {
        background: #3DB3B3 !important;
        color: #0F172A !important;
    }
    
    [data-testid="stSidebar"] .stButton > button:hover {
        background: #2D8F8F !important;
        color: white !important;
    }
    
    /* Section headers - Dark theme */
    .section-header {
        font-size: 1.125rem;
        font-weight: 600;
        color: #F1F5F9 !important;
        margin: 2rem 0 1rem 0;
        padding-bottom: 0.5rem;
        border-bottom: 1px solid #334155;
    }
    
    /* Info boxes - Dark theme */
    .info-box {
        background: #1E293B;
        border: 1px solid #334155;
        border-left: 3px solid #3DB3B3;
        border-radius: 4px;
        padding: 1rem 1.25rem;
        margin: 1rem 0;
        color: #F1F5F9 !important;
    }
    
    .info-box.warning {
        background: #3A2E1E;
        border-left-color: #F59E0B;
    }
    
    .info-box.success {
        background: #1E3A2E;
        border-left-color: #22C55E;
    }
    
    /* Data tables */
    .stDataFrame {
        border-radius: 12px !important;
        overflow: hidden !important;
    }
    
    /* Tabs styling - Dark theme */
    .stTabs [data-baseweb="tab-list"] {
        gap: 4px;
        background: transparent;
    }
    
    .stTabs [data-baseweb="tab"] {
        background: #1E293B;
        border-radius: 4px;
        color: #94A3B8;
        padding: 8px 16px;
        border: 1px solid #334155;
    }
    
    .stTabs [aria-selected="true"] {
        background: #3DB3B3 !important;
        color: #0F172A !important;
        border-color: #3DB3B3 !important;
    }
    
    /* Expanders - Dark theme */
    .streamlit-expanderHeader {
        background: #1E293B;
        border-radius: 4px;
        border: 1px solid #334155;
        color: #F1F5F9;
    }
    
    /* Filter indicator - Dark theme */
    .filter-badge {
        background: #3DB3B3;
        color: #0F172A;
        padding: 0.375rem 0.75rem;
        border-radius: 4px;
        font-size: 0.875rem;
        display: inline-flex;
        align-items: center;
        margin-bottom: 1rem;
    }
    
    /* Dividers - Dark theme */
    hr {
        border: none;
        height: 1px;
        background: #334155;
        margin: 2rem 0;
    }
    
    /* Text colors for dark theme */
    h1, h2, h3, h4, h5, h6 {
        color: #F1F5F9 !important;
    }
    
    p, span, div, label {
        color: #F1F5F9;
    }
    
    /* Streamlit default text inputs and forms - Dark theme */
    .stTextInput > div > div > input {
        background-color: #1E293B;
        color: #F1F5F9;
        border-color: #475569;
    }
    
    .stTextInput > div > div > input:focus {
        border-color: #3DB3B3;
    }

    /* Selectbox/multiselect controls open a dropdown on click, but their underlying
       BaseWeb element is a (readonly) <input>, which browsers default to an I-beam
       text cursor — misleading since there's nothing to type/select as text here. */
    [data-baseweb="select"] > div,
    [data-baseweb="select"] input {
        cursor: pointer !important;
    }

    /* Metrics - Dark theme */
    [data-testid="stMetricValue"] {
        color: #F1F5F9;
    }
    
    [data-testid="stMetricLabel"] {
        color: #94A3B8;
    }
    
    /* Success/Warning/Error messages - Dark theme */
    .stSuccess {
        background-color: #1E3A2E;
        border-left: 3px solid #22C55E;
        color: #86EFAC;
    }
    
    .stWarning {
        background-color: #3A2E1E;
        border-left: 3px solid #F59E0B;
        color: #FCD34D;
    }
    
    .stError {
        background-color: #3A1E1E;
        border-left: 3px solid #EF4444;
        color: #FCA5A5;
    }
    
    .stInfo {
        background-color: #1E293B;
        border-left: 3px solid #0EA5E9;
        color: #7DD3FC;
    }
    
    /* Sidebar form elements - Dark theme */
    [data-testid="stSidebar"] .stRadio > label {
        color: #F1F5F9 !important;
    }
    
    [data-testid="stSidebar"] .stRadio [data-baseweb="radio"] {
        color: #3DB3B3 !important;
    }
    
    [data-testid="stSidebar"] .stSelectbox > label {
        color: #F1F5F9 !important;
    }
    
    [data-testid="stSidebar"] .stTextInput > label {
        color: #F1F5F9 !important;
    }
    
    [data-testid="stSidebar"] .stNumberInput > label {
        color: #F1F5F9 !important;
    }
    
    /* Data tables - Dark theme */
    .stDataFrame {
        border-radius: 4px !important;
        overflow: hidden !important;
        background-color: #1E293B !important;
    }
    
    /* Force dark theme for all Streamlit elements */
    .stApp > header {
        background-color: #0F172A !important;
    }
    
    /* Main content area background */
    section[data-testid="stAppViewContainer"] {
        background-color: #0F172A !important;
    }
    
    div[data-testid="stAppViewContainer"] > div {
        background-color: #0F172A !important;
    }
    
    /* Ensure all text is light on dark background */
    .element-container {
        color: #F1F5F9;
    }
    
    /* Captions */
    .stCaption {
        color: #94A3B8 !important;
    }
    
    /* Code blocks */
    .stCodeBlock {
        background-color: #1E293B;
        border: 1px solid #334155;
        color: #F1F5F9;
    }
    
    /* Markdown text */
    .stMarkdown {
        color: #F1F5F9;
    }
    
    [data-testid="stMarkdownContainer"] {
        color: #F1F5F9;
    }
    
    /* Selectbox and other inputs */
    .stSelectbox > label,
    .stTextInput > label,
    .stNumberInput > label,
    .stDateInput > label,
    .stTextArea > label,
    .stFileUploader > label {
        color: #F1F5F9 !important;
    }
    
    /* Radio buttons */
    .stRadio > label {
        color: #F1F5F9 !important;
    }
    
    /* Checkboxes */
    .stCheckbox > label {
        color: #F1F5F9 !important;
    }
    
    /* Dataframe styling */
    .stDataFrame table {
        background-color: #1E293B !important;
        color: #F1F5F9 !important;
    }
    
    .stDataFrame th {
        background-color: #334155 !important;
        color: #F1F5F9 !important;
    }
    
    .stDataFrame td {
        background-color: #1E293B !important;
        color: #F1F5F9 !important;
    }

    /* Hero metric — the single headline figure a page leads with */
    .hero-metric {
        background: linear-gradient(135deg, #1E293B 0%, #16212F 100%);
        border: 1px solid #334155;
        border-radius: 10px;
        padding: 1.5rem 1.75rem;
        height: 100%;
    }

    .hero-metric-label {
        font-size: 0.72rem;
        font-weight: 600;
        letter-spacing: 0.6px;
        color: #94A3B8;
        text-transform: uppercase;
        margin-bottom: 0.5rem;
    }

    .hero-metric-value {
        font-size: 3rem;
        font-weight: 700;
        line-height: 1.1;
        margin-bottom: 0.5rem;
    }

    .hero-metric-sub {
        font-size: 0.78rem;
        color: #94A3B8;
    }

    /* Plant environment picker — post-login system chooser */
    .env-picker-header {
        text-align: center;
        padding: 2rem 0 0.5rem 0;
    }

    .env-picker-icon {
        width: 64px;
        height: 64px;
        margin: 0 auto 1.25rem auto;
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 1.75rem;
        background: rgba(61, 179, 179, 0.12);
        border: 1px solid rgba(61, 179, 179, 0.35);
        box-shadow: 0 0 0 8px rgba(61, 179, 179, 0.06), 0 0 0 16px rgba(61, 179, 179, 0.03);
    }

    .env-picker-title {
        font-size: 1.75rem;
        font-weight: 700;
        color: #F1F5F9;
        margin: 0 0 0.35rem 0;
    }

    .env-picker-subtitle {
        color: #94A3B8;
        font-size: 0.9rem;
        margin: 0 0 1rem 0;
    }

    .env-user-pill {
        display: inline-flex;
        align-items: center;
        gap: 0.4rem;
        background: #1E293B;
        border: 1px solid #334155;
        color: #CBD5E1;
        padding: 0.3rem 0.9rem;
        border-radius: 999px;
        font-size: 0.8rem;
    }

    .env-card-header {
        display: flex;
        align-items: center;
        gap: 0.9rem;
        margin: -1rem -1rem 0.9rem -1rem;
        padding: 1.1rem 1.1rem 1rem 1.1rem;
        border-radius: 8px 8px 0 0;
    }

    .env-card-header.active {
        background: linear-gradient(135deg, #1D6E6E 0%, #175454 100%);
    }

    .env-card-header.archive {
        background: #263447;
    }

    .env-card-icon-badge {
        width: 42px;
        height: 42px;
        border-radius: 10px;
        background: rgba(255, 255, 255, 0.14);
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 1.3rem;
        flex-shrink: 0;
    }

    .env-card-title {
        font-size: 1.15rem;
        font-weight: 700;
        color: #F8FAFC;
        margin-bottom: 0.3rem;
    }

    .env-status-pill {
        display: inline-flex;
        align-items: center;
        gap: 0.3rem;
        font-size: 0.68rem;
        font-weight: 600;
        letter-spacing: 0.5px;
        padding: 0.15rem 0.55rem;
        border-radius: 999px;
    }

    .env-status-pill.active {
        background: rgba(34, 197, 94, 0.2);
        color: #4ADE80;
    }

    .env-status-pill.archive {
        background: rgba(148, 163, 184, 0.2);
        color: #CBD5E1;
    }

    .env-card-desc {
        color: #94A3B8;
        font-size: 0.85rem;
        line-height: 1.5;
        margin-bottom: 0.9rem;
    }

    .env-card-features {
        list-style: none;
        padding: 0;
        margin: 0 0 1rem 0;
    }

    .env-card-features li {
        color: #CBD5E1;
        font-size: 0.82rem;
        padding: 0.2rem 0;
    }

    /* Archive card's CTA reads as secondary/muted, not a second primary action */
    .st-key-picker_miniplant .stButton > button {
        background: transparent !important;
        color: #CBD5E1 !important;
        border: 1px solid #64748B !important;
    }

    .st-key-picker_miniplant .stButton > button:hover {
        background: #263447 !important;
        color: #F1F5F9 !important;
    }

    /* Stat tiles — compact icon + label + value KPI cards (Athena-inspired) */
    .stat-tile {
        display: flex;
        align-items: center;
        gap: 0.85rem;
        background: #1E293B;
        border: 1px solid #334155;
        border-radius: 8px;
        padding: 0.9rem 1.1rem;
        height: 100%;
    }

    .stat-tile-icon {
        width: 40px;
        height: 40px;
        border-radius: 10px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 1.15rem;
        flex-shrink: 0;
    }

    .stat-tile-icon.green { background: rgba(34, 197, 94, 0.16); color: #4ADE80; }
    .stat-tile-icon.blue { background: rgba(14, 165, 233, 0.16); color: #38BDF8; }
    .stat-tile-icon.purple { background: rgba(124, 58, 237, 0.16); color: #C4B5FD; }
    .stat-tile-icon.teal { background: rgba(61, 179, 179, 0.16); color: #5EEAD4; }
    .stat-tile-icon.amber { background: rgba(245, 158, 11, 0.16); color: #FCD34D; }
    .stat-tile-icon.red { background: rgba(239, 68, 68, 0.16); color: #FCA5A5; }

    .stat-tile-label {
        font-size: 0.72rem;
        color: #94A3B8;
        text-transform: uppercase;
        letter-spacing: 0.4px;
        margin-bottom: 0.15rem;
        white-space: nowrap;
    }

    .stat-tile-value {
        font-size: 1.35rem;
        font-weight: 700;
        color: #F1F5F9;
        line-height: 1.15;
    }

    .stat-tile-sub {
        font-size: 0.68rem;
        color: #94A3B8;
        margin-top: 0.1rem;
    }

    /* Quick-navigation cards — now backed by real st.page_link targets */
    [data-testid="stPageLink"] {
        border-radius: 6px;
    }

    [data-testid="stPageLink"] p {
        font-weight: 600 !important;
        font-size: 0.95rem !important;
    }
    </style>
    """
