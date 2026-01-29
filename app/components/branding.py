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
                <div style="font-size: 1.1rem; font-weight: 300; color: #3DB3B3; letter-spacing: 3px;">OCTAVIA</div>
                <div style="font-size: 1.1rem; font-weight: 300; color: #3DB3B3; letter-spacing: 3px;">CARBON</div>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown("""
            <div style="margin-bottom: 1rem;">
                <span style="font-size: 2rem; font-weight: 300; color: #1A5F5F; letter-spacing: 4px;">OCTAVIA</span>
                <span style="font-size: 2rem; font-weight: 300; color: #1A5F5F; letter-spacing: 4px; margin-left: 10px;">CARBON</span>
            </div>
            """, unsafe_allow_html=True)


def render_header_with_logo() -> None:
    """Render a professional header matching octaviacarbon.com style."""
    logo_path = get_logo_path()
    
    st.markdown("""
    <div style="margin-bottom: 2rem;">
        <h1 style="
            font-size: 2.5rem;
            font-weight: 300;
            color: #F1F5F9;
            letter-spacing: 2px;
            margin: 0 0 0.5rem 0;
            font-family: 'Inter', 'Segoe UI', sans-serif;
        ">
            Carbon Accounting System
        </h1>
        <p style="
            color: #94A3B8;
            font-size: 1rem;
            letter-spacing: 1px;
            margin: 0;
            font-weight: 300;
        ">
            Direct Air Capture • Project Hummingbird Phase 1 • Gilgil, Kenya
        </p>
    </div>
    """, unsafe_allow_html=True)


def get_brand_css() -> str:
    """Return CSS styles matching octaviacarbon.com professional design."""
    return """
    <style>
    /* Import Inter font */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
    
    /* Global styles */
    .stApp {
        font-family: 'Inter', 'Segoe UI', -apple-system, sans-serif;
    }
    
    /* Hide default Streamlit branding */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    
    /* Custom scrollbar */
    ::-webkit-scrollbar {
        width: 8px;
        height: 8px;
    }
    ::-webkit-scrollbar-track {
        background: #0D3B3B;
    }
    ::-webkit-scrollbar-thumb {
        background: #1A5F5F;
        border-radius: 4px;
    }
    ::-webkit-scrollbar-thumb:hover {
        background: #2D8F8F;
    }
    
    /* Sidebar styling */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0D3B3B 0%, #071F1F 100%) !important;
        border-right: 1px solid #1A5F5F;
    }
    
    [data-testid="stSidebar"] .stMarkdown {
        color: #F1F5F9;
    }
    
    /* Metric cards - Octavia style */
    .metric-card {
        background: linear-gradient(135deg, #FFFFFF 0%, #F8FAFC 100%);
        border-radius: 16px;
        padding: 1.5rem;
        border: 1px solid #E2E8F0;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.08);
        transition: all 0.3s ease;
        position: relative;
        overflow: hidden;
    }
    
    .metric-card::before {
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        height: 4px;
        background: linear-gradient(90deg, #1A5F5F 0%, #3DB3B3 100%);
    }
    
    .metric-card:hover {
        transform: translateY(-4px);
        box-shadow: 0 8px 30px rgba(0, 0, 0, 0.12);
    }
    
    .metric-card h3 {
        font-size: 0.75rem;
        color: #64748B;
        margin-bottom: 0.75rem;
        text-transform: uppercase;
        letter-spacing: 1.5px;
        font-weight: 500;
        display: flex;
        align-items: center;
        gap: 6px;
    }
    
    .metric-card .value {
        font-size: 2rem;
        font-weight: 600;
        letter-spacing: -0.5px;
    }
    
    /* Card variants */
    .metric-card.positive::before { background: linear-gradient(90deg, #22C55E 0%, #4ADE80 100%); }
    .metric-card.positive .value { color: #16A34A; }
    
    .metric-card.negative::before { background: linear-gradient(90deg, #EF4444 0%, #F87171 100%); }
    .metric-card.negative .value { color: #DC2626; }
    
    .metric-card.neutral::before { background: linear-gradient(90deg, #1A5F5F 0%, #3DB3B3 100%); }
    .metric-card.neutral .value { color: #1A5F5F; }
    
    .metric-card.info::before { background: linear-gradient(90deg, #0EA5E9 0%, #38BDF8 100%); }
    .metric-card.info .value { color: #0284C7; }
    
    /* Process flow cards */
    .flow-card {
        text-align: center;
        padding: 1.5rem 1rem;
        border-radius: 16px;
        border: 1px solid;
        transition: all 0.3s ease;
    }
    
    .flow-card:hover {
        transform: translateY(-2px);
    }
    
    .flow-card .icon {
        font-size: 2rem;
        margin-bottom: 0.5rem;
    }
    
    .flow-card .label {
        font-size: 0.7rem;
        font-weight: 600;
        letter-spacing: 1.5px;
        text-transform: uppercase;
        margin-bottom: 0.25rem;
    }
    
    .flow-card .value {
        font-size: 1.5rem;
        font-weight: 700;
    }
    
    .flow-card.adsorbed {
        background: linear-gradient(135deg, #DCFCE7 0%, #BBF7D0 100%);
        border-color: #86EFAC;
    }
    .flow-card.adsorbed .label { color: #166534; }
    .flow-card.adsorbed .value { color: #15803D; }
    
    .flow-card.desorbed {
        background: linear-gradient(135deg, #FEF3C7 0%, #FDE68A 100%);
        border-color: #FCD34D;
    }
    .flow-card.desorbed .label { color: #B45309; }
    .flow-card.desorbed .value { color: #D97706; }
    
    .flow-card.collected {
        background: linear-gradient(135deg, #DBEAFE 0%, #BFDBFE 100%);
        border-color: #93C5FD;
    }
    .flow-card.collected .label { color: #1D4ED8; }
    .flow-card.collected .value { color: #2563EB; }
    
    .flow-card.liquefied {
        background: linear-gradient(135deg, #CFFAFE 0%, #A5F3FC 100%);
        border-color: #22D3EE;
    }
    .flow-card.liquefied .label { color: #0E7490; }
    .flow-card.liquefied .value { color: #0891B2; }
    
    .flow-card.inactive {
        background: linear-gradient(135deg, #F1F5F9 0%, #E2E8F0 100%);
        border-color: #CBD5E1;
    }
    .flow-card.inactive .label { color: #64748B; }
    .flow-card.inactive .value { color: #64748B; }
    
    /* Flow arrow */
    .flow-arrow {
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 1.5rem;
        color: #22C55E;
    }
    
    /* Navigation cards - Octavia gradient style */
    .nav-card {
        padding: 1.5rem;
        border-radius: 16px;
        color: white;
        transition: all 0.3s ease;
        position: relative;
        overflow: hidden;
    }
    
    .nav-card::after {
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        background: linear-gradient(135deg, rgba(255,255,255,0.1) 0%, rgba(255,255,255,0) 100%);
        opacity: 0;
        transition: opacity 0.3s ease;
    }
    
    .nav-card:hover {
        transform: translateY(-4px);
        box-shadow: 0 12px 40px rgba(0, 0, 0, 0.3);
    }
    
    .nav-card:hover::after {
        opacity: 1;
    }
    
    .nav-card h3 {
        margin: 0;
        color: white;
        font-weight: 500;
        font-size: 1.1rem;
    }
    
    .nav-card p {
        opacity: 0.85;
        margin: 0.5rem 0 0 0;
        font-size: 0.9rem;
        font-weight: 300;
    }
    
    .nav-card.teal { background: linear-gradient(135deg, #1A5F5F 0%, #2D8F8F 100%); }
    .nav-card.purple { background: linear-gradient(135deg, #6D28D9 0%, #8B5CF6 100%); }
    .nav-card.cyan { background: linear-gradient(135deg, #0891B2 0%, #22D3EE 100%); }
    .nav-card.emerald { background: linear-gradient(135deg, #059669 0%, #34D399 100%); }
    .nav-card.orange { background: linear-gradient(135deg, #EA580C 0%, #FB923C 100%); }
    
    /* Buttons - Octavia style */
    .stButton > button {
        background: linear-gradient(135deg, #1A5F5F 0%, #2D8F8F 100%) !important;
        color: white !important;
        border: none !important;
        border-radius: 12px !important;
        padding: 0.6rem 1.5rem !important;
        font-weight: 500 !important;
        letter-spacing: 0.5px !important;
        transition: all 0.3s ease !important;
        box-shadow: 0 4px 15px rgba(26, 95, 95, 0.3) !important;
    }
    
    .stButton > button:hover {
        background: linear-gradient(135deg, #2D8F8F 0%, #3DB3B3 100%) !important;
        transform: translateY(-2px) !important;
        box-shadow: 0 6px 20px rgba(26, 95, 95, 0.4) !important;
    }
    
    /* Section headers */
    .section-header {
        font-size: 1.25rem;
        font-weight: 500;
        color: #F1F5F9;
        margin: 2rem 0 1rem 0;
        padding-bottom: 0.5rem;
        border-bottom: 2px solid #1A5F5F;
        display: flex;
        align-items: center;
        gap: 0.5rem;
    }
    
    /* Info boxes */
    .info-box {
        background: linear-gradient(135deg, rgba(26, 95, 95, 0.1) 0%, rgba(61, 179, 179, 0.1) 100%);
        border: 1px solid #1A5F5F;
        border-radius: 12px;
        padding: 1rem 1.25rem;
        margin: 1rem 0;
        color: #F1F5F9;
    }
    
    .info-box.warning {
        background: linear-gradient(135deg, rgba(245, 158, 11, 0.1) 0%, rgba(251, 191, 36, 0.1) 100%);
        border-color: #F59E0B;
    }
    
    .info-box.success {
        background: linear-gradient(135deg, rgba(34, 197, 94, 0.1) 0%, rgba(74, 222, 128, 0.1) 100%);
        border-color: #22C55E;
    }
    
    /* Data tables */
    .stDataFrame {
        border-radius: 12px !important;
        overflow: hidden !important;
    }
    
    /* Tabs styling */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        background: transparent;
    }
    
    .stTabs [data-baseweb="tab"] {
        background: rgba(26, 95, 95, 0.2);
        border-radius: 8px;
        color: #94A3B8;
        padding: 10px 20px;
        border: 1px solid transparent;
    }
    
    .stTabs [aria-selected="true"] {
        background: linear-gradient(135deg, #1A5F5F 0%, #2D8F8F 100%) !important;
        color: white !important;
        border-color: #3DB3B3 !important;
    }
    
    /* Expanders */
    .streamlit-expanderHeader {
        background: rgba(26, 95, 95, 0.1);
        border-radius: 8px;
        border: 1px solid #1A5F5F;
    }
    
    /* Filter indicator */
    .filter-badge {
        background: linear-gradient(135deg, #1A5F5F 0%, #2D8F8F 100%);
        color: white;
        padding: 0.5rem 1rem;
        border-radius: 20px;
        font-size: 0.85rem;
        display: inline-flex;
        align-items: center;
        gap: 0.5rem;
        margin-bottom: 1rem;
    }
    
    /* Dividers */
    hr {
        border: none;
        height: 1px;
        background: linear-gradient(90deg, transparent 0%, #1A5F5F 50%, transparent 100%);
        margin: 2rem 0;
    }
    </style>
    """
