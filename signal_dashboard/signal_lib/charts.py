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


# ------------------------------------------------------------------ evidence / attribution

THEME_PICK = "theme_pick"


def _source_scale() -> alt.Scale:
    return alt.Scale(domain=list(t.SOURCE_COLORS), range=list(t.SOURCE_COLORS.values()))


def attribution_bars(attr: pd.DataFrame, corr: pd.DataFrame, selected: Optional[str] = None) -> alt.Chart:
    """100% stacked bars of each theme's evidence by source. Click a bar to pick its theme.

    The point selection is named ``THEME_PICK``; read it from
    ``st.altair_chart(..., on_select="rerun")``. ``selected`` dims the other themes.
    """
    labels = corr.assign(
        LABEL=corr["THEME"] + "  ·  " + corr["SOURCE_FAMILIES"].astype(int).astype(str) + " sources"
    )
    order = labels.sort_values(["SOURCE_FAMILIES", "MULTI_SOURCE_ENTITIES"], ascending=False)["LABEL"].tolist()
    df = attr.assign(SOURCE=attr["SOURCE"].astype(str)).merge(
        labels[["THEME", "LABEL", "CONFIDENCE"]], on="THEME", how="left")
    df["FOCUS"] = (df["THEME"] == selected) if selected else True
    pick = alt.selection_point(name=THEME_PICK, fields=["THEME"], on="click")
    bars = alt.Chart(df).mark_bar(cornerRadius=2).encode(
        x=alt.X("EVIDENCE_ITEMS:Q", stack="normalize", title="Share of theme evidence",
                axis=alt.Axis(format="%")),
        y=alt.Y("LABEL:N", sort=order, title=None),
        color=alt.Color("SOURCE:N", scale=_source_scale(), title=None),
        opacity=alt.condition("datum.FOCUS", alt.value(1.0), alt.value(0.3)),
        tooltip=[alt.Tooltip("THEME:N"), alt.Tooltip("SOURCE:N"),
                 alt.Tooltip("EVIDENCE_ITEMS:Q", title="Items"),
                 alt.Tooltip("SHARE_OF_THEME:Q", format=".0%", title="Share"),
                 alt.Tooltip("ENTITIES:Q", title="Companies"),
                 alt.Tooltip("CONFIDENCE:N")],
    ).add_params(pick)
    return t.style(bars.properties(height=max(320, 22 * df["THEME"].nunique())))


def evidence_timeline(tl: pd.DataFrame) -> alt.Chart:
    """Monthly stacked bars of dated evidence by source for one theme."""
    chart = alt.Chart(tl).mark_bar().encode(
        x=alt.X("MONTH:T", title=None),
        y=alt.Y("ITEMS:Q", title="Evidence items", stack="zero"),
        color=alt.Color("SOURCE:N", scale=_source_scale(), title=None),
        tooltip=[alt.Tooltip("MONTH:T", format="%b %Y"), "SOURCE:N", "ITEMS:Q"],
    )
    return t.style(chart.properties(height=220))


def source_dot_matrix(matrix: pd.DataFrame, sources, top: int = 15) -> alt.Chart:
    """Company x source dot grid (dot size = items) for the top companies in a theme."""
    head = matrix.head(top)
    long = head.melt(id_vars=["ENTITY_NAME", "SOURCE_FAMILIES", "TOTAL"], value_vars=list(sources),
                     var_name="SOURCE", value_name="ITEMS")
    long = long[long["ITEMS"] > 0]
    chart = alt.Chart(long).mark_circle(opacity=0.9).encode(
        x=alt.X("SOURCE:N", sort=list(sources), title=None,
                axis=alt.Axis(labelAngle=0, orient="top")),
        y=alt.Y("ENTITY_NAME:N", sort=head["ENTITY_NAME"].tolist(), title=None),
        size=alt.Size("ITEMS:Q", scale=alt.Scale(range=[60, 900]), legend=None),
        color=alt.Color("SOURCE:N", scale=_source_scale(), legend=None),
        tooltip=["ENTITY_NAME:N", "SOURCE:N", "ITEMS:Q",
                 alt.Tooltip("SOURCE_FAMILIES:Q", title="Independent sources")],
    )
    return t.style(chart.properties(height=max(220, 24 * len(head))))


# ------------------------------------------------------------------ company fit

COMPANY_PICK = "company_pick"


def _rel_scale() -> alt.Scale:
    return alt.Scale(domain=list(t.RELATIONSHIP_COLORS), range=list(t.RELATIONSHIP_COLORS.values()))


def fit_quadrant(companies: pd.DataFrame, selected: Optional[str] = None) -> alt.Chart:
    """Profile fit (Cortex similarity, x) vs CRM mentions (y), one dot per company.

    Click a dot to pick a company (selection ``COMPANY_PICK``, field ACCOUNT_NAME).
    """
    df = companies.assign(SELECTED=companies["ACCOUNT_NAME"] == selected)
    pick = alt.selection_point(name=COMPANY_PICK, fields=["ACCOUNT_NAME"], on="click")
    base = alt.Chart(df)
    dots = base.mark_circle(opacity=0.8, stroke=t.BACKGROUND, strokeWidth=0.5).encode(
        x=alt.X("SIMILARITY:Q", title="Profile fit (Cortex similarity to theme)",
                scale=alt.Scale(zero=False)),
        y=alt.Y("CRM_MENTIONS:Q", title="CRM mentions since Jul 2024"),
        size=alt.condition("datum.SELECTED", alt.value(320), alt.value(60)),
        color=alt.Color("RELATIONSHIP:N", scale=_rel_scale(), title=None),
        tooltip=[alt.Tooltip("ACCOUNT_NAME:N", title="Company"), "INDUSTRY:N", "RELATIONSHIP:N",
                 alt.Tooltip("SIMILARITY:Q", format=".2f", title="Fit"),
                 alt.Tooltip("FIT_RANK:Q", title="Fit rank (of 21)"),
                 alt.Tooltip("CRM_MENTIONS:Q", title="Mentions"),
                 alt.Tooltip("STATED_PRIORITY:N", title="Stated priority")],
    ).add_params(pick)
    halo = base.transform_filter("datum.SELECTED").mark_circle(
        fill=None, stroke=t.TEXT, strokeWidth=2, size=700
    ).encode(x="SIMILARITY:Q", y="CRM_MENTIONS:Q")
    return t.style((dots + halo).properties(height=420))


def company_theme_bars(themes: pd.DataFrame) -> alt.Chart:
    """For one company: fit per theme (bars) with CRM mentions (ticks on second axis)."""
    order = themes.sort_values("SIMILARITY", ascending=False)["THEME"].tolist()
    base = alt.Chart(themes).encode(y=alt.Y("THEME:N", sort=order, title=None))
    bars = base.mark_bar(cornerRadius=2).encode(
        x=alt.X("SIMILARITY:Q", title="Profile fit", scale=alt.Scale(zero=False)),
        color=alt.Color("RELATIONSHIP:N", scale=_rel_scale(), title=None),
        tooltip=["THEME:N", "RELATIONSHIP:N", alt.Tooltip("SIMILARITY:Q", format=".2f"),
                 "FIT_RANK:Q", "CRM_MENTIONS:Q", "STATED_PRIORITY:N"],
    )
    mentions = base.mark_text(align="left", dx=4, color=t.TEXT, fontSize=11).encode(
        x="SIMILARITY:Q",
        text=alt.Text("CRM_MENTIONS:Q", format="d"),
    )
    return t.style((bars + mentions).properties(height=max(300, 20 * len(themes))))


# ------------------------------------------------------------------ emerging topics

CLUSTER_PICK = "cluster_pick"


def _emerging_scale() -> alt.Scale:
    return alt.Scale(domain=list(t.EMERGING_COLORS), range=list(t.EMERGING_COLORS.values()))


def emergence_map(sig: pd.DataFrame, selected: Optional[str] = None) -> alt.Chart:
    """Uniqueness (distance from nearest theme) vs velocity, bubble = companies. Click to pick."""
    df = sig.assign(SELECTED=sig["CLUSTER_ID"] == selected,
                    LABEL=sig["TOPIC_NAME"].fillna(sig["CLUSTER_ID"]))
    pick = alt.selection_point(name=CLUSTER_PICK, fields=["CLUSTER_ID"], on="click")
    base = alt.Chart(df)
    dots = base.mark_circle(opacity=0.85, stroke=t.BACKGROUND, strokeWidth=1).encode(
        x=alt.X("UNIQUENESS:Q", title="Uniqueness (1 − similarity to nearest theme)",
                scale=alt.Scale(zero=False, padding=30)),
        y=alt.Y("VELOCITY:Q", title="Velocity (recent 8 weeks ÷ prior 8 weeks)",
                scale=alt.Scale(type="log")),
        size=alt.Size("ACCOUNTS:Q", scale=alt.Scale(range=[120, 2200]), legend=None),
        color=alt.Color("STATUS:N", scale=_emerging_scale(), title=None),
        tooltip=[alt.Tooltip("LABEL:N", title="Topic"), "STATUS:N",
                 alt.Tooltip("RECORDS:Q", title="Records"), alt.Tooltip("ACCOUNTS:Q", title="Companies"),
                 alt.Tooltip("VELOCITY:Q", format=".2f"), alt.Tooltip("UNIQUENESS:Q", format=".2f"),
                 alt.Tooltip("NEAREST_THEME:N", title="Nearest theme"), "SOURCE_LIST:N"],
    ).add_params(pick)
    labels = base.mark_text(align="left", dx=12, dy=-6, fontSize=11, color=t.TEXT).encode(
        x="UNIQUENESS:Q", y="VELOCITY:Q", text="LABEL:N")
    halo = base.transform_filter("datum.SELECTED").mark_circle(
        fill=None, stroke=t.TEXT, strokeWidth=2, size=2600).encode(x="UNIQUENESS:Q", y="VELOCITY:Q")
    return t.style((dots + halo + labels).properties(height=380))


def cluster_timeline(weekly: pd.DataFrame) -> alt.Chart:
    """Weekly additions to one cluster, stacked by source."""
    chart = alt.Chart(weekly).mark_bar().encode(
        x=alt.X("WEEK:T", title=None),
        y=alt.Y("RECORDS:Q", title="Records added", stack="zero"),
        color=alt.Color("SOURCE:N", scale=_source_scale(), title=None),
        tooltip=[alt.Tooltip("WEEK:T", format="%b %d, %Y"), "SOURCE:N", "RECORDS:Q"],
    )
    return t.style(chart.properties(height=220))


TOPIC_PICK = "topic_pick"


def _topic_panel(df: pd.DataFrame, pick, title: str, y_title: str, log_y: bool, label_top: int,
                 topics_statuses) -> alt.LayerChart:
    colors = {k: v for k, v in {**t.SIGNAL_COLORS, **t.EMERGING_COLORS}.items()
              if k in set(topics_statuses)}
    df = df.assign(
        LABEL=df["TOPIC"].where(df["SELECTED"] | (df["MOMENTUM"].rank(ascending=False, method="first") <= label_top), ""),
        M=df["MOMENTUM"].clip(lower=0.1))
    pad = 0.15 * max(1.0, float(df["COMPANIES"].max() - df["COMPANIES"].min())) if len(df) else 1
    enc = dict(
        x=alt.X("COMPANIES:Q", title="Reach (companies)",
                scale=alt.Scale(zero=False, nice=True,
                                domain=[max(0, float(df["COMPANIES"].min()) - pad), float(df["COMPANIES"].max()) + pad]
                                if len(df) else alt.Undefined)),
        y=alt.Y("M:Q", title=y_title,
                scale=alt.Scale(type="log", nice=False, domain=[0.8, float(df["M"].max()) * 1.6]) if log_y else alt.Scale(zero=False, nice=True, padding=20)),
    )
    base = alt.Chart(df)
    dots = base.mark_circle(opacity=0.9, stroke=t.BACKGROUND, strokeWidth=1).encode(
        **enc,
        size=alt.Size("MENTIONS:Q", scale=alt.Scale(range=[80, 700]), legend=None),
        color=alt.Color("STATUS:N", title=None,
                        scale=alt.Scale(domain=list(colors), range=list(colors.values()))),
        tooltip=[alt.Tooltip("TOPIC:N", title="Topic"), "STATUS:N",
                 alt.Tooltip("MOMENTUM:Q", format=".2f", title="Momentum"),
                 alt.Tooltip("COMPANIES:Q", title="Companies"), alt.Tooltip("MENTIONS:Q", title="Mentions")],
    ).add_params(pick)
    rule = alt.Chart(pd.DataFrame({"M": [1.0]})).mark_rule(color=t.MUTED, strokeDash=[4, 4]).encode(y="M:Q")
    labels = base.mark_text(align="left", dx=11, dy=alt.expr("datum.COMPANIES % 2 ? 9 : -9"), fontSize=10, color=t.TEXT).encode(**enc, text="LABEL:N")
    halo = base.transform_filter("datum.SELECTED").mark_circle(
        fill=None, stroke=t.TEXT, strokeWidth=2, size=1100).encode(**enc)
    return (rule + dots + halo + labels).properties(title=title, height=360, width=560)


def topic_map(topics: pd.DataFrame, selected: Optional[str] = None) -> alt.Chart:
    """Two panels, each on its own scale: tracked themes (lift vs reach) and discovered topics
    (velocity vs reach). Their momentum ranges differ by an order of magnitude, so one shared
    axis squashes the themes. Bubble = mentions; click either panel to pick (``TOPIC_PICK``)."""
    df = topics.drop(columns=["TREND", "FIRST_SEEN", "DEFINITION"], errors="ignore").assign(
        SELECTED=topics["TOPIC_ID"] == selected)
    pick = alt.selection_point(name=TOPIC_PICK, fields=["TOPIC_ID"], on="click")
    panels = []
    themes = df[df["KIND"] == "Tracked theme"]
    found = df[df["KIND"] == "Discovered"]
    if len(themes):
        panels.append(_topic_panel(themes, pick, "Tracked themes", "Lift vs baseline", False, 6, df["STATUS"]))
    if len(found):
        panels.append(_topic_panel(found, pick, "Discovered topics", "Velocity (last 8 wks ÷ prior 8, log)",
                                   True, 8, df["STATUS"]))
    if not panels:
        return t.style(alt.Chart(pd.DataFrame({"x": []})).mark_point())
    chart = alt.hconcat(*panels).resolve_scale(x="independent", y="independent", size="independent")
    return t.style(chart)


def topic_weekly(weekly: pd.DataFrame) -> alt.Chart:
    """Weekly CRM mentions for one tracked theme."""
    chart = alt.Chart(weekly).mark_area(color=t.PRIMARY, opacity=0.35, line={"color": t.PRIMARY}).encode(
        x=alt.X("WEEK:T", title=None), y=alt.Y("RECORDS:Q", title="Mentions per week"),
        tooltip=[alt.Tooltip("WEEK:T", format="%b %d, %Y"), "RECORDS:Q"])
    return t.style(chart.properties(height=220))
