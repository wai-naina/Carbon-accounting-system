"""Chart components for the Octavia CAS dashboard."""
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots


# Professional color palette optimized for dark theme visibility
COLORS = {
    "positive": "#22C55E",      # Bright green
    "negative": "#EF4444",      # Bright red
    "thermal": "#F97316",       # Bright orange
    "auxiliary": "#06B6D4",     # Cyan (legacy)
    "srv_lrvp": "#06B6D4",     # Cyan
    "ct": "#0EA5E9",           # Sky blue
    "fans": "#14B8A6",         # Teal
    "liquefaction": "#6366F1",  # Indigo
    "embodied": "#A855F7",      # Purple
    "captured": "#22C55E",      # Green
    "emissions": "#EF4444",     # Red
    "adsorbed": "#4ADE80",      # Light green
    "desorbed": "#FB923C",      # Light orange
    "collected": "#38BDF8",     # Sky blue
    "liquefied": "#22D3EE",     # Bright cyan
    "neutral": "#94A3B8",       # Slate
    "text_light": "#F1F5F9",    # Very light for dark bg
    "text_dark": "#1E293B",     # Dark for light bg
    "grid": "#334155",          # Grid lines
    "bg_transparent": "rgba(0,0,0,0)",
}


def apply_chart_layout(
    fig: go.Figure,
    *,
    title: str,
    height: int,
    xaxis_title: str | None = None,
    yaxis_title: str | None = None,
    showlegend: bool = True,
    extra_top_margin: int = 0,
    extra_bottom_margin: int = 0,
) -> None:
    """Apply a consistent layout with readable text and safe margins."""
    fig.update_layout(
        title=dict(
            text=title,
            font=dict(size=16, color=COLORS["text_light"], family="Inter, sans-serif"),
            x=0,
            xanchor="left",
        ),
        template="plotly_dark",
        height=height,
        margin=dict(l=70, r=50, t=80 + extra_top_margin, b=80 + extra_bottom_margin),
        paper_bgcolor=COLORS["bg_transparent"],
        plot_bgcolor=COLORS["bg_transparent"],
        font=dict(color=COLORS["text_light"], family="Inter, sans-serif"),
        uniformtext=dict(minsize=10, mode="hide"),
        showlegend=showlegend,
        xaxis=dict(
            title=dict(text=xaxis_title, font=dict(size=12, color=COLORS["text_light"])) if xaxis_title else None,
            automargin=True,
            tickangle=-30,
            gridcolor=COLORS["grid"],
            zerolinecolor=COLORS["neutral"],
            tickfont=dict(color=COLORS["text_light"], size=11),
            linecolor=COLORS["grid"],
        ),
        yaxis=dict(
            title=dict(text=yaxis_title, font=dict(size=12, color=COLORS["text_light"])) if yaxis_title else None,
            automargin=True,
            gridcolor=COLORS["grid"],
            zerolinecolor=COLORS["neutral"],
            tickfont=dict(color=COLORS["text_light"], size=11),
            linecolor=COLORS["grid"],
        ),
        legend=dict(
            font=dict(color=COLORS["text_light"], size=11),
            bgcolor="rgba(15, 23, 42, 0.8)",
            bordercolor=COLORS["grid"],
            borderwidth=1,
        ),
        hovermode="x unified",
        hoverlabel=dict(
            bgcolor="#1E293B",
            font=dict(color=COLORS["text_light"], size=12),
            bordercolor=COLORS["grid"],
        ),
    )


def trend_chart(df: pd.DataFrame) -> go.Figure:
    """Net CO2 removal trend with positive/negative coloring."""
    if df.empty:
        return None
    
    fig = go.Figure()
    
    # Add filled area
    colors = [COLORS["positive"] if v >= 0 else COLORS["negative"] for v in df["net_removal_kg"]]
    
    fig.add_trace(go.Scatter(
        x=df["week_label"],
        y=df["net_removal_kg"],
        mode="lines+markers",
        name="Net Removal",
        line=dict(color=COLORS["positive"], width=3),
        marker=dict(size=10, color=colors, line=dict(width=2, color="white")),
        fill="tozeroy",
        fillcolor="rgba(34, 197, 94, 0.2)",
        hovertemplate="<b>%{x}</b><br>Net: %{y:,.1f} kg CO₂<extra></extra>",
    ))
    
    # Add zero line
    fig.add_hline(y=0, line_dash="dash", line_color=COLORS["neutral"], annotation_text="Break-even")
    
    apply_chart_layout(
        fig,
        title="📈 Net CO₂ Removal Trend",
        height=400,
        xaxis_title="Week",
        yaxis_title="Net Removal (kg CO₂)",
    )
    
    return fig


def co2_flow_chart(df: pd.DataFrame) -> go.Figure:
    """CO2 flow through process stages over time."""
    if df.empty:
        return None
    
    fig = go.Figure()
    
    fig.add_trace(go.Scatter(
        x=df["week_label"],
        y=df.get("total_ads_co2_kg", [0] * len(df)),
        mode="lines+markers",
        name="Adsorbed",
        line=dict(color=COLORS["adsorbed"], width=2),
        marker=dict(size=8),
        hovertemplate="<b>%{x}</b><br>Adsorbed: %{y:,.1f} kg<extra></extra>",
    ))
    
    fig.add_trace(go.Scatter(
        x=df["week_label"],
        y=df.get("total_des_co2_kg", [0] * len(df)),
        mode="lines+markers",
        name="Desorbed",
        line=dict(color=COLORS["desorbed"], width=2),
        marker=dict(size=8),
        hovertemplate="<b>%{x}</b><br>Desorbed: %{y:,.1f} kg<extra></extra>",
    ))
    
    fig.add_trace(go.Scatter(
        x=df["week_label"],
        y=df.get("total_bag_co2_kg", [0] * len(df)),
        mode="lines+markers",
        name="Collected (Bag)",
        line=dict(color=COLORS["collected"], width=2),
        marker=dict(size=8),
        hovertemplate="<b>%{x}</b><br>Collected: %{y:,.1f} kg<extra></extra>",
    ))
    
    fig.add_trace(go.Scatter(
        x=df["week_label"],
        y=df.get("liquefied_co2_kg", [0] * len(df)),
        mode="lines+markers",
        name="Liquefied",
        line=dict(color=COLORS["liquefied"], width=3),
        marker=dict(size=10),
        hovertemplate="<b>%{x}</b><br>Liquefied: %{y:,.1f} kg<extra></extra>",
    ))
    
    apply_chart_layout(
        fig,
        title="🔄 CO₂ Flow Through Process Stages",
        height=400,
        xaxis_title="Week",
        yaxis_title="CO₂ (kg)",
    )
    fig.update_layout(legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
    
    return fig


def emissions_breakdown_pie(df: pd.DataFrame) -> go.Figure:
    """Pie chart of emissions by category (thermal, non-thermal components, embodied)."""
    if df.empty:
        return None
    
    latest = df.iloc[-1]
    thermal = latest.get("thermal_emissions_kg", 0) or 0
    auxiliary_total = latest.get("auxiliary_emissions_kg", 0) or 0
    embodied = latest.get("total_embodied_emissions_kg", 0) or 0
    
    # Split auxiliary emissions by component energy share
    auxiliary_energy = latest.get("auxiliary_energy_kwh", 0) or 0
    srv_kwh = latest.get("srv_lrvp_kwh", 0) or 0
    ct_kwh = latest.get("ct_kwh", 0) or 0
    fans_kwh = latest.get("fans_kwh", 0) or 0
    liq_kwh = latest.get("liquefaction_energy_kwh", 0) or 0
    
    if auxiliary_energy > 0 and auxiliary_total > 0:
        srv_em = auxiliary_total * (srv_kwh / auxiliary_energy)
        ct_em = auxiliary_total * (ct_kwh / auxiliary_energy)
        fans_em = auxiliary_total * (fans_kwh / auxiliary_energy)
        liq_em = auxiliary_total * (liq_kwh / auxiliary_energy)
    else:
        srv_em = ct_em = fans_em = liq_em = 0
    
    labels = ["Thermal (Boiler)", "SRV/LRVP", "CT", "Fans", "Liquefaction", "Embodied"]
    values = [thermal, srv_em, ct_em, fans_em, liq_em, embodied]
    colors = [COLORS["thermal"], COLORS["srv_lrvp"], COLORS["ct"], COLORS["fans"], COLORS["liquefaction"], COLORS["embodied"]]
    
    # Filter out zero values for cleaner display
    non_zero = [(l, v, c) for l, v, c in zip(labels, values, colors) if v > 0]
    if not non_zero:
        return None
    labels, values, colors = zip(*non_zero)
    
    total = sum(values)
    if total == 0:
        return None
    
    week_label = latest.get("week_label", "Selected Week")
    
    fig = go.Figure(data=[go.Pie(
        labels=list(labels),
        values=list(values),
        hole=0.45,
        marker_colors=list(colors),
        textinfo="percent",
        textposition="inside",
        textfont=dict(color="white", size=13, family="Inter, sans-serif"),
        hovertemplate="<b>%{label}</b><br>%{value:,.1f} kg CO₂<br>%{percent}<extra></extra>",
    )])
    
    fig.update_traces(
        marker=dict(line=dict(color="#1E293B", width=2)),
    )
    apply_chart_layout(
        fig,
        title=f"🥧 Emissions Breakdown ({week_label})",
        height=400,
        showlegend=True,
    )
    fig.update_layout(
        annotations=[dict(
            text=f"<b>{total:.0f}</b><br>kg CO₂",
            x=0.5,
            y=0.5,
            font_size=14,
            showarrow=False,
            font=dict(color=COLORS["text_light"], family="Inter, sans-serif"),
        )],
        legend=dict(orientation="h", yanchor="bottom", y=-0.15, xanchor="center", x=0.5),
    )
    
    return fig


def energy_intensity_chart(df: pd.DataFrame) -> go.Figure:
    """Energy intensity bar chart with improved visibility."""
    if df.empty:
        return None
    
    values = df["energy_intensity_kwh_per_tonne"].tolist()
    
    # Format values for display (use k suffix for thousands)
    def format_value(v):
        if v >= 10000:
            return f"{v/1000:.0f}k"
        elif v >= 1000:
            return f"{v/1000:.1f}k"
        elif v > 0:
            return f"{v:.0f}"
        return "0"
    
    fig = go.Figure()
    
    fig.add_trace(go.Bar(
        x=df["week_label"],
        y=values,
        marker_color=COLORS["thermal"],
        marker_line_color=COLORS["text_light"],
        marker_line_width=1,
        text=[format_value(v) for v in values],
        textposition="inside",
        textangle=0,
        insidetextanchor="middle",
        textfont=dict(color="white", size=12, family="Inter, sans-serif"),
        hovertemplate="<b>%{x}</b><br>%{y:,.0f} kWh/tCO₂<extra></extra>",
    ))
    
    # Calculate y-axis range with proper padding
    if values:
        max_val = max(values) if max(values) > 0 else 100
        y_max = max_val * 1.15
    else:
        y_max = 100
    
    apply_chart_layout(
        fig,
        title="⚡ Energy Intensity (kWh/tCO₂)",
        height=380,
        xaxis_title="Week",
        yaxis_title="kWh per tonne CO₂",
    )
    fig.update_layout(
        yaxis=dict(range=[0, y_max], tickformat=","),
        bargap=0.3,
    )
    
    return fig


def loss_analysis_chart(df: pd.DataFrame) -> go.Figure:
    """Stacked bar chart showing CO2 losses at each stage."""
    if df.empty:
        return None
    
    fig = go.Figure()
    
    # Use distinct, colorblind-friendly colors for each stage
    stage_colors = {
        "stage1": "#14B8A6",  # Teal for Stage 1 (Ads→Des)
        "stage2": "#F59E0B",  # Amber for Stage 2 (Des→Bag)
        "stage3": "#F43F5E",  # Rose for Stage 3 (Bag→Liq)
    }
    
    fig.add_trace(go.Bar(
        name="Stage 1 (Ads→Des)",
        x=df["week_label"],
        y=df.get("loss_stage_1_kg", [0] * len(df)),
        marker_color=stage_colors["stage1"],
        marker_line_color="#1E293B",
        marker_line_width=1,
        hovertemplate="<b>%{x}</b><br>Stage 1 Loss: %{y:,.1f} kg<extra></extra>",
    ))
    
    fig.add_trace(go.Bar(
        name="Stage 2 (Des→Bag)",
        x=df["week_label"],
        y=df.get("loss_stage_2_kg", [0] * len(df)),
        marker_color=stage_colors["stage2"],
        marker_line_color="#1E293B",
        marker_line_width=1,
        hovertemplate="<b>%{x}</b><br>Stage 2 Loss: %{y:,.1f} kg<extra></extra>",
    ))
    
    fig.add_trace(go.Bar(
        name="Stage 3 (Bag→Liq)",
        x=df["week_label"],
        y=df.get("loss_stage_3_kg", [0] * len(df)),
        marker_color=stage_colors["stage3"],
        marker_line_color="#1E293B",
        marker_line_width=1,
        hovertemplate="<b>%{x}</b><br>Stage 3 Loss: %{y:,.1f} kg<extra></extra>",
    ))
    
    apply_chart_layout(
        fig,
        title="📉 CO₂ Losses by Process Stage",
        height=380,
        xaxis_title="Week",
        yaxis_title="CO₂ Lost (kg)",
    )
    fig.update_layout(
        barmode="stack",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        bargap=0.3,
    )
    
    return fig


def cumulative_chart(df: pd.DataFrame) -> go.Figure:
    """Cumulative captured vs emissions over time."""
    if df.empty:
        return None
    
    df = df.copy()
    
    # Use collected CO₂ (bag or liquefied based on availability)
    collected_col = df["liquefied_co2_kg"].copy()
    if collected_col.sum() == 0:
        collected_col = df.get("total_bag_co2_kg", df["liquefied_co2_kg"])
    
    df["cumulative_captured"] = collected_col.cumsum()
    df["cumulative_emissions"] = df["total_emissions_kg"].cumsum()
    df["cumulative_net"] = df["net_removal_kg"].cumsum()
    
    fig = go.Figure()
    
    fig.add_trace(go.Scatter(
        x=df["week_label"],
        y=df["cumulative_captured"],
        mode="lines+markers",
        name="Cumulative Captured",
        line=dict(color=COLORS["captured"], width=3),
        fill="tozeroy",
        fillcolor="rgba(34, 197, 94, 0.15)",
        hovertemplate="<b>%{x}</b><br>Captured: %{y:,.1f} kg<extra></extra>",
    ))
    
    fig.add_trace(go.Scatter(
        x=df["week_label"],
        y=df["cumulative_emissions"],
        mode="lines+markers",
        name="Cumulative Emissions",
        line=dict(color=COLORS["emissions"], width=3),
        fill="tozeroy",
        fillcolor="rgba(239, 68, 68, 0.15)",
        hovertemplate="<b>%{x}</b><br>Emissions: %{y:,.1f} kg<extra></extra>",
    ))
    
    fig.add_trace(go.Scatter(
        x=df["week_label"],
        y=df["cumulative_net"],
        mode="lines+markers",
        name="Cumulative Net",
        line=dict(color="#3B82F6", width=3, dash="dash"),
        hovertemplate="<b>%{x}</b><br>Net: %{y:,.1f} kg<extra></extra>",
    ))
    
    # Add zero line
    fig.add_hline(y=0, line_dash="dot", line_color=COLORS["neutral"])
    
    apply_chart_layout(
        fig,
        title="📊 Cumulative Carbon Balance",
        height=400,
        xaxis_title="Week",
        yaxis_title="kg CO₂",
    )
    fig.update_layout(legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
    
    return fig


def energy_breakdown_chart(df: pd.DataFrame) -> go.Figure:
    """Stacked bar showing thermal and non-thermal energy by component (SRV/LRVP, CT, Fans, Liquefaction)."""
    if df.empty:
        return None
    
    fig = go.Figure()
    
    fig.add_trace(go.Bar(
        name="Thermal (Boiler)",
        x=df["week_label"],
        y=df.get("thermal_energy_kwh", [0] * len(df)),
        marker_color=COLORS["thermal"],
        marker_line_color="#1E293B",
        marker_line_width=1,
        hovertemplate="<b>%{x}</b><br>Thermal (Boiler): %{y:,.0f} kWh<extra></extra>",
    ))
    
    fig.add_trace(go.Bar(
        name="SRV/LRVP",
        x=df["week_label"],
        y=df.get("srv_lrvp_kwh", [0] * len(df)),
        marker_color=COLORS["srv_lrvp"],
        marker_line_color="#1E293B",
        marker_line_width=1,
        hovertemplate="<b>%{x}</b><br>SRV/LRVP: %{y:,.0f} kWh<extra></extra>",
    ))
    
    fig.add_trace(go.Bar(
        name="CT",
        x=df["week_label"],
        y=df.get("ct_kwh", [0] * len(df)),
        marker_color=COLORS["ct"],
        marker_line_color="#1E293B",
        marker_line_width=1,
        hovertemplate="<b>%{x}</b><br>CT: %{y:,.0f} kWh<extra></extra>",
    ))
    
    fig.add_trace(go.Bar(
        name="Fans",
        x=df["week_label"],
        y=df.get("fans_kwh", [0] * len(df)),
        marker_color=COLORS["fans"],
        marker_line_color="#1E293B",
        marker_line_width=1,
        hovertemplate="<b>%{x}</b><br>Fans: %{y:,.0f} kWh<extra></extra>",
    ))
    
    fig.add_trace(go.Bar(
        name="Liquefaction",
        x=df["week_label"],
        y=df.get("liquefaction_energy_kwh", [0] * len(df)),
        marker_color=COLORS["liquefaction"],
        marker_line_color="#1E293B",
        marker_line_width=1,
        hovertemplate="<b>%{x}</b><br>Liquefaction: %{y:,.0f} kWh<extra></extra>",
    ))
    
    apply_chart_layout(
        fig,
        title="⚡ Energy Consumption by Component",
        height=380,
        xaxis_title="Week",
        yaxis_title="Energy (kWh)",
    )
    fig.update_layout(
        barmode="stack",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        bargap=0.3,
    )
    
    return fig


def scenario_comparison_chart(current_emissions: float, geothermal_emissions: float) -> go.Figure:
    """Bar chart comparing current vs geothermal scenario."""
    fig = go.Figure()
    
    fig.add_trace(go.Bar(
        name="Current (Grid)",
        x=["Operational Emissions"],
        y=[current_emissions],
        marker_color=COLORS["thermal"],
        marker_line_color="#1E293B",
        marker_line_width=1,
        text=[f"{current_emissions:.1f}"],
        textposition="outside",
        textfont=dict(color=COLORS["text_light"], size=14, family="Inter, sans-serif"),
        hovertemplate="<b>Current</b><br>%{y:,.1f} kg CO₂<extra></extra>",
    ))
    
    fig.add_trace(go.Bar(
        name="Geothermal Scenario",
        x=["Operational Emissions"],
        y=[geothermal_emissions],
        marker_color=COLORS["captured"],
        marker_line_color="#1E293B",
        marker_line_width=1,
        text=[f"{geothermal_emissions:.1f}"],
        textposition="outside",
        textfont=dict(color=COLORS["text_light"], size=14, family="Inter, sans-serif"),
        hovertemplate="<b>Geothermal</b><br>%{y:,.1f} kg CO₂<extra></extra>",
    ))
    
    reduction = current_emissions - geothermal_emissions
    reduction_pct = (reduction / current_emissions * 100) if current_emissions > 0 else 0
    
    max_val = max(current_emissions, geothermal_emissions)
    
    apply_chart_layout(
        fig,
        title=f"🔋 Energy Scenario Comparison ({reduction_pct:.1f}% reduction)",
        height=380,
        yaxis_title="kg CO₂",
        extra_top_margin=20,
    )
    fig.update_layout(
        barmode="group",
        yaxis=dict(range=[0, max_val * 1.25]),
        bargap=0.3,
    )
    
    return fig


def waterfall_chart(captured: float, operational: float, embodied: float) -> go.Figure:
    """Waterfall chart showing how we get to net removal - with improved visibility."""
    net = captured - operational - embodied
    
    # Create custom colors based on whether values are positive or negative contribution
    bar_colors = [
        COLORS["captured"],    # CO₂ Captured - always positive (green)
        COLORS["negative"],    # Operational - negative contribution (red)
        COLORS["negative"],    # Embodied - negative contribution (red)  
        COLORS["positive"] if net >= 0 else COLORS["negative"],  # Net - depends on result
    ]
    
    fig = go.Figure(go.Waterfall(
        name="Carbon Balance",
        orientation="v",
        measure=["absolute", "relative", "relative", "total"],
        x=["CO₂ Captured", "Operational<br>Emissions", "Embodied<br>Emissions", "Net Removal"],
        y=[captured, -operational, -embodied, net],
        connector={"line": {"color": COLORS["neutral"], "width": 1, "dash": "dot"}},
        increasing={"marker": {"color": COLORS["captured"], "line": {"color": "#1E293B", "width": 1}}},
        decreasing={"marker": {"color": COLORS["negative"], "line": {"color": "#1E293B", "width": 1}}},
        totals={"marker": {"color": COLORS["positive"] if net >= 0 else COLORS["negative"], "line": {"color": "#1E293B", "width": 1}}},
        textposition="outside",
        text=[f"+{captured:.1f}", f"-{operational:.1f}", f"-{embodied:.1f}", f"{net:.1f}"],
        textfont=dict(color=COLORS["text_light"], size=13, family="Inter, sans-serif"),
        hovertemplate="<b>%{x}</b><br>%{text} kg CO₂<extra></extra>",
    ))
    
    # Calculate y-axis range to accommodate all values and labels
    all_values = [captured, -operational, -embodied, net]
    y_min = min(all_values + [0])
    y_max = max(all_values + [0])
    y_range = y_max - y_min
    padding = y_range * 0.25  # 25% padding for labels
    
    apply_chart_layout(
        fig,
        title="💧 Carbon Balance Waterfall",
        height=450,
        yaxis_title="kg CO₂",
        showlegend=False,
        extra_top_margin=30,
        extra_bottom_margin=20,
    )
    
    fig.update_layout(
        yaxis=dict(
            range=[y_min - padding, y_max + padding],
            zeroline=True,
            zerolinecolor=COLORS["neutral"],
            zerolinewidth=2,
        ),
        xaxis=dict(tickangle=0),
    )
    
    # Add a zero line annotation
    fig.add_hline(y=0, line_dash="solid", line_color=COLORS["neutral"], line_width=1)
    
    return fig


def module_comparison_chart(pair_data: dict) -> go.Figure:
    """Create a comparison chart between Module pairs."""
    if not pair_data:
        return None
    
    categories = ["Cycles", "Collected CO₂ (kg)", "Efficiency (%)"]
    
    n13_values = [
        pair_data.get("1n3", {}).get("cycles", 0),
        pair_data.get("1n3", {}).get("collected", 0),
        pair_data.get("1n3", {}).get("efficiency", 0),
    ]
    
    n24_values = [
        pair_data.get("2n4", {}).get("cycles", 0),
        pair_data.get("2n4", {}).get("collected", 0),
        pair_data.get("2n4", {}).get("efficiency", 0),
    ]
    
    fig = go.Figure()
    
    fig.add_trace(go.Bar(
        name="Module 1 & 3 🌟",
        x=categories,
        y=n13_values,
        marker_color="#22C55E",
        marker_line_color="#1E293B",
        marker_line_width=1,
        text=[f"{v:.1f}" if isinstance(v, float) else str(v) for v in n13_values],
        textposition="outside",
        textfont=dict(color=COLORS["text_light"], size=12),
    ))
    
    fig.add_trace(go.Bar(
        name="Module 2 & 4",
        x=categories,
        y=n24_values,
        marker_color="#3B82F6",
        marker_line_color="#1E293B",
        marker_line_width=1,
        text=[f"{v:.1f}" if isinstance(v, float) else str(v) for v in n24_values],
        textposition="outside",
        textfont=dict(color=COLORS["text_light"], size=12),
    ))
    
    apply_chart_layout(
        fig,
        title="🔬 Module Pair Performance Comparison",
        height=400,
        extra_top_margin=20,
    )
    fig.update_layout(
        barmode="group",
        bargap=0.3,
        xaxis=dict(tickangle=0),
    )
    
    return fig
