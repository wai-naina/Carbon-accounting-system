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
    
    /* Hide default Streamlit branding */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    
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
    </style>
    """
