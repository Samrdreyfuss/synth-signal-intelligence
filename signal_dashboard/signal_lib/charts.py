"""Altair chart builders. Each takes a prepared DataFrame and returns a styled chart."""

from __future__ import annotations

from typing import Iterable, Optional

import altair as alt
import pandas as pd

from . import theme as t


def _signal_scale() -> alt.Scale:
    return alt.Scale(domain=list(t.SIGNAL_COLORS), range=list(t.SIGNAL_COLORS.values()))


def theme_radar(lifted: pd.DataFrame, selected: Optional[str] = None) -> alt.Chart:
    """Bubble chart: lift vs baseline (x) against enterprises (y), sized by mentions."""
    df = lifted.copy()
    df["SELECTED"] = df["THEME"] == selected
    base = alt.Chart(df)
    rule = alt.Chart(pd.DataFrame({"x": [1.0]})).mark_rule(
        color=t.MUTED, strokeDash=[4, 4]
    ).encode(x="x:Q")
    bubbles = base.mark_circle(opacity=0.85, stroke=t.BACKGROUND, strokeWidth=1).encode(
        x=alt.X("LIFT:Q", title="Lift vs AI-agents baseline (1.0 = matching)",
                scale=alt.Scale(zero=False, padding=20)),
        y=alt.Y("CURRENT_ENTERPRISES:Q", title="Enterprises mentioning (current window)"),
        size=alt.Size("CURRENT_MENTIONS:Q", title="Current mentions",
                      scale=alt.Scale(range=[80, 1800]), legend=None),
        color=alt.Color("SIGNAL:N", scale=_signal_scale(), title=None),
        tooltip=[
            alt.Tooltip("THEME:N", title="Theme"),
            alt.Tooltip("LIFT:Q", format=".2f", title="Lift"),
            alt.Tooltip("MONTHLY_RATE_RATIO:Q", format=".2f", title="Rate ratio"),
            alt.Tooltip("CURRENT_MENTIONS:Q", title="Current mentions"),
            alt.Tooltip("PRIOR_MENTIONS:Q", title="Prior mentions"),
            alt.Tooltip("CURRENT_ENTERPRISES:Q", title="Enterprises"),
            alt.Tooltip("SCAN:N", title="Scan"),
            alt.Tooltip("EXAMPLE_ENTERPRISES:N", title="Examples"),
        ],
    )
    labels = base.transform_filter(
        (alt.datum.LIFT >= 1.1) | alt.datum.SELECTED | alt.datum.IS_BASELINE
    ).mark_text(align="left", dx=10, dy=-6, fontSize=11, color=t.TEXT).encode(
        x="LIFT:Q", y="CURRENT_ENTERPRISES:Q", text="THEME:N"
    )
    halo = base.transform_filter(alt.datum.SELECTED).mark_circle(
        fill=None, stroke=t.TEXT, strokeWidth=2, size=2400
    ).encode(x="LIFT:Q", y="CURRENT_ENTERPRISES:Q")
    return t.style((rule + bubbles + halo + labels).properties(height=440))


def lift_bars(lifted: pd.DataFrame) -> alt.Chart:
    """Diverging bars of lift minus 1, so themes beating the baseline point right."""
    df = lifted[~lifted["IS_BASELINE"]].copy()
    df["DELTA"] = df["LIFT"] - 1
    chart = alt.Chart(df).mark_bar(cornerRadius=3).encode(
        x=alt.X("DELTA:Q", title="Lift − 1", axis=alt.Axis(format="+.0%")),
        y=alt.Y("THEME:N", sort="-x", title=None),
        color=alt.Color("SIGNAL:N", scale=_signal_scale(), legend=None),
        tooltip=[alt.Tooltip("THEME:N"), alt.Tooltip("LIFT:Q", format=".2f")],
    )
    return t.style(chart.properties(height=max(260, 22 * len(df))))


def share_lines(shares: pd.DataFrame, highlight: Iterable[str] = ()) -> alt.Chart:
    """Quarterly share-of-activity per theme; highlighted themes drawn bold."""
    df = shares.copy()
    hl = set(highlight)
    df["HL"] = df["THEME"].isin(hl) if hl else True
    chart = alt.Chart(df).mark_line(point=True, interpolate="monotone").encode(
        x=alt.X("QUARTER:O", title=None),
        y=alt.Y("SHARE:Q", title="Share of enterprise activities", axis=alt.Axis(format=".1%")),
        color=alt.condition(
            "datum.HL",
            alt.Color("THEME:N", scale=alt.Scale(range=t.CATEGORICAL), title=None),
            alt.value(t.GRID),
        ),
        strokeWidth=alt.condition("datum.HL", alt.value(3), alt.value(1)),
        detail="THEME:N",
        tooltip=[alt.Tooltip("THEME:N"), alt.Tooltip("QUARTER:O"),
                 alt.Tooltip("SHARE:Q", format=".2%"), alt.Tooltip("MENTIONS:Q")],
    )
    return t.style(chart.properties(height=380))


def fde_chart(fde: pd.DataFrame) -> alt.Chart:
    """Enterprise FDE activities (bars) with expert documents (line) on a second axis."""
    base = alt.Chart(fde).encode(x=alt.X("QUARTER:O", title=None))
    bars = base.mark_bar(color=t.ACCENT, opacity=0.7, cornerRadiusTopLeft=3,
                         cornerRadiusTopRight=3).encode(
        y=alt.Y("ENTERPRISE_FDE_ACTIVITIES:Q", title="Enterprise activities"),
        tooltip=["QUARTER", "ENTERPRISE_FDE_ACTIVITIES", "EXPERT_FDE_DOCS"],
    )
    line = base.mark_line(color=t.PRIMARY, strokeWidth=3, point=alt.OverlayMarkDef(
        color=t.PRIMARY, size=60)).encode(
        y=alt.Y("EXPERT_FDE_DOCS:Q", title="Expert documents"),
    )
    return t.style(alt.layer(bars, line).resolve_scale(y="independent").properties(height=300))


def monthly_area(monthly: pd.DataFrame) -> alt.Chart:
    """Monthly share of CRM events mentioning a theme (live data)."""
    chart = alt.Chart(monthly).mark_area(
        line={"color": t.PRIMARY, "strokeWidth": 2},
        color=alt.Gradient(
            gradient="linear",
            stops=[alt.GradientStop(color=t.BACKGROUND, offset=0),
                   alt.GradientStop(color=t.PRIMARY, offset=1)],
            x1=1, x2=1, y1=1, y2=0,
        ),
        opacity=0.6, interpolate="monotone",
    ).encode(
        x=alt.X("MONTH:T", title=None),
        y=alt.Y("SHARE:Q", title="Share of CRM events", axis=alt.Axis(format=".1%")),
        tooltip=[alt.Tooltip("MONTH:T", format="%b %Y"), alt.Tooltip("MENTIONS:Q"),
                 alt.Tooltip("SHARE:Q", format=".2%")],
    )
    return t.style(chart.properties(height=260))


def portco_heatmap(matrix: pd.DataFrame) -> alt.Chart:
    chart = alt.Chart(matrix).mark_rect(cornerRadius=3).encode(
        x=alt.X("PORTCO:N", title=None, sort="-color", axis=alt.Axis(labelAngle=-35)),
        y=alt.Y("THEME:N", title=None, sort="-color"),
        color=alt.Color("ACTIVITIES:Q", title="Activities",
                        scale=alt.Scale(range=[t.SURFACE, t.ACCENT, t.PRIMARY])),
        tooltip=["THEME", "PORTCO", "ACTIVITIES"],
    )
    text = alt.Chart(matrix).mark_text(color=t.TEXT, fontSize=11).encode(
        x=alt.X("PORTCO:N", sort="-color"), y=alt.Y("THEME:N", sort="-color"),
        text="ACTIVITIES:Q",
    )
    return t.style((chart + text).properties(height=max(300, 26 * matrix["THEME"].nunique())))


def scan_status_bars(counts: pd.DataFrame) -> alt.Chart:
    chart = alt.Chart(counts).mark_bar(cornerRadius=3).encode(
        x=alt.X("COMPANIES:Q", title="Companies", stack="zero"),
        y=alt.Y("THEME:N", title=None, sort="-x"),
        color=alt.Color("SALESFORCE_STATUS:N", title=None,
                        scale=alt.Scale(domain=list(t.STATUS_COLORS),
                                        range=list(t.STATUS_COLORS.values()))),
        tooltip=["THEME", "SALESFORCE_STATUS", "COMPANIES"],
    )
    return t.style(chart.properties(height=260))
