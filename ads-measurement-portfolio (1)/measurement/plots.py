"""Plotly figure builders shared by the Streamlit pages.

Design rules: one y-axis per chart, thin marks, a legend whenever there are two
series, and colors taken from a fixed order (blue, then orange) so identity is
never carried by color alone: the counterfactual is also dashed.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

BLUE = "#2a78d6"
ORANGE = "#eb6834"
GRAY = "#9a9994"
LIGHT_GRAY = "rgba(154,153,148,0.35)"

_LAYOUT = dict(
    margin=dict(l=10, r=10, t=40, b=10),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    hovermode="x unified",
)


def counterfactual_chart(series: pd.DataFrame, title: str) -> go.Figure:
    """Actual treated conversions against the modelled counterfactual."""
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=series.index, y=series["actual"], name="Actual", mode="lines", line=dict(color=BLUE, width=2)))
    fig.add_trace(
        go.Scatter(
            x=series.index,
            y=series["counterfactual"],
            name="Counterfactual",
            mode="lines",
            line=dict(color=ORANGE, width=2, dash="dash"),
        )
    )
    post_dates = series.index[series["post"]]
    if len(post_dates):
        start = pd.Timestamp(post_dates[0])
        fig.add_shape(type="line", x0=start, x1=start, y0=0, y1=1, xref="x", yref="paper", line=dict(color=GRAY, width=1, dash="dot"))
        fig.add_annotation(x=start, y=1, xref="x", yref="paper", text="Test start", showarrow=False, xanchor="left", yanchor="bottom", font=dict(size=11))
    fig.update_layout(title=title, yaxis_title="Daily conversions", **_LAYOUT)
    return fig


def estimator_chart(primary, others) -> go.Figure:
    """Lift by estimator with intervals where available, on a single axis."""
    results = [primary, *others]
    names = [r.method for r in results]
    lifts = [r.lift * 100 for r in results]
    err_plus = [((r.lift_high - r.lift) * 100) if r.lift_high is not None else 0 for r in results]
    err_minus = [((r.lift - r.lift_low) * 100) if r.lift_low is not None else 0 for r in results]

    fig = go.Figure(
        go.Scatter(
            x=lifts,
            y=names,
            mode="markers",
            marker=dict(color=BLUE, size=10, line=dict(color="white", width=2)),
            error_x=dict(type="data", symmetric=False, array=err_plus, arrayminus=err_minus, color=BLUE, thickness=2),
            hovertemplate="%{y}: %{x:.1f}%<extra></extra>",
            showlegend=False,
        )
    )
    fig.add_vline(x=0, line=dict(color=GRAY, width=1, dash="dot"))
    fig.update_layout(
        title="Measured lift by method (95% interval where available)",
        xaxis_title="Lift in conversions (%)",
        yaxis=dict(autorange="reversed"),
        margin=dict(l=10, r=10, t=40, b=10),
        height=260,
    )
    return fig


def duration_chart(table: pd.DataFrame, max_days: int) -> go.Figure:
    labels = [f"{x:.1%}" for x in table["target_lift"]]
    fig = go.Figure(go.Bar(x=labels, y=table["duration_days"], marker=dict(color=BLUE), name="Days required", hovertemplate="%{x} lift: %{y} days<extra></extra>"))
    fig.add_hline(y=max_days, line=dict(color=ORANGE, width=2, dash="dash"), annotation_text=f"Limit: {max_days} days", annotation_position="top left")
    fig.update_layout(title="User-level test duration by target lift", xaxis_title="Target lift", yaxis_title="Days", margin=dict(l=10, r=10, t=40, b=10), height=320)
    return fig


def power_chart(table: pd.DataFrame) -> go.Figure:
    labels = [f"{x:.1%}" for x in table["target_lift"]]
    fig = go.Figure(go.Scatter(x=labels, y=table["geo_power"] * 100, mode="lines+markers", line=dict(color=BLUE, width=2), marker=dict(size=8, line=dict(color="white", width=2)), name="Geo power", hovertemplate="%{x} lift: %{y:.0f}% power<extra></extra>"))
    fig.add_hline(y=80, line=dict(color=ORANGE, width=2, dash="dash"), annotation_text="80% target", annotation_position="bottom right")
    fig.update_layout(title="Geo experiment power by target lift", xaxis_title="Target lift", yaxis=dict(title="Power (%)", range=[0, 105]), margin=dict(l=10, r=10, t=40, b=10), height=320)
    return fig


def audit_chart(checks) -> go.Figure:
    names = [c.name for c in checks]
    earned = [c.points for c in checks]
    gap = [c.weight - c.points for c in checks]
    fig = go.Figure()
    fig.add_trace(go.Bar(y=names, x=earned, orientation="h", name="Points earned", marker=dict(color=BLUE), hovertemplate="%{y}: %{x:.0f} earned<extra></extra>"))
    fig.add_trace(go.Bar(y=names, x=gap, orientation="h", name="Available to recover", marker=dict(color=LIGHT_GRAY), hovertemplate="%{y}: %{x:.0f} available<extra></extra>"))
    fig.update_layout(barmode="stack", title="Score by check", xaxis_title="Points", yaxis=dict(autorange="reversed"), legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0), margin=dict(l=10, r=10, t=40, b=10), height=320)
    return fig
