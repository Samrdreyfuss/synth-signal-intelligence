"""Shared palette and Altair styling. Colours match .streamlit/config.toml."""

from __future__ import annotations

BACKGROUND = "#0B1020"
SURFACE = "#141B2E"
GRID = "#25304A"
TEXT = "#E6EAF2"
MUTED = "#8A94AD"
PRIMARY = "#5EEAD4"   # teal accent
ACCENT = "#A78BFA"    # violet
WARN = "#FBBF24"
DANGER = "#F87171"

CATEGORICAL = [
    "#5EEAD4", "#A78BFA", "#60A5FA", "#F472B6", "#FBBF24",
    "#34D399", "#F87171", "#22D3EE", "#C084FC", "#FB923C",
]

SIGNAL_COLORS = {
    "Outpacing baseline": PRIMARY,
    "Matching baseline": "#60A5FA",
    "Lagging baseline": WARN,
    "Cooling": DANGER,
    "Baseline": MUTED,
}

STATUS_COLORS = {
    "In Salesforce": "#60A5FA",
    "Possible match": WARN,
    "Not in Salesforce": PRIMARY,
}


def style(chart):
    """Apply the dashboard look to an Altair chart (transparent so it sits on the theme)."""
    return (
        chart.configure(background="transparent", font="Inter, sans-serif")
        .configure_view(strokeWidth=0)
        .configure_axis(
            gridColor=GRID, domainColor=GRID, tickColor=GRID,
            labelColor=MUTED, titleColor=MUTED, labelFontSize=11, titleFontSize=12,
        )
        .configure_legend(labelColor=TEXT, titleColor=MUTED, orient="bottom")
        .configure_title(color=TEXT, fontSize=14, anchor="start")
    )
