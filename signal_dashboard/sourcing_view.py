"""Sourcing view: companies we have not spoken with, for a theme or a discovered topic.

Drill path: ranked target list (filters: basis, stage) -> company card (profile, fit across
themes, every signal from expert calls, portfolio-company notes and the external scan).
"""

from datetime import timedelta

import pandas as pd
import streamlit as st

from signal_lib import data, sourcing as so

CACHE_TTL = timedelta(minutes=15)


@st.cache_data(ttl=CACHE_TTL, max_entries=64)
def _theme_targets(_run, theme, version=1):
    return so.theme_targets(_run, theme)


@st.cache_data(ttl=CACHE_TTL, max_entries=64)
def _topic_targets(_run, cluster_id, version=1):
    return so.topic_targets(_run, cluster_id)


@st.cache_data(ttl=CACHE_TTL, max_entries=256)
def _card(_run, company_id, version=1):
    return so.company_signals(_run, company_id), so.company_fit(_run, company_id)


def render(run, theme=None, cluster_id=None, topic_name=None):
    """Pass theme (tracked) or cluster_id (discovered)."""
    ss = st.session_state
    key = theme or cluster_id
    ss.setdefault("so_company", {})
    name = theme or topic_name or cluster_id

    if theme:
        st.caption(
            f"Companies with **no CRM relationship** that fit **{name}**: their description matches the "
            "theme (Cortex `AI_EMBED`) and/or they have surfaced on it in expert calls, portfolio-company "
            "notes or the external scan. Score = 0.5 profile fit + 0.3 signals (up to 3) + 0.2 recency "
            "(signal in last 90 days = full, 180 = half). "
            + " · ".join(f"**{k}**: {v}" for k, v in so.BASIS_HELP.items())
        )
        targets = _theme_targets(run, theme)
    else:
        st.caption(f"Companies with **no CRM relationship** whose description is closest to the centre of "
                   f"**{name}** (Cortex `AI_EMBED` similarity). Discovered topics have no definition yet, so "
                   "this is a starting list, not a scored ranking.")
        targets = _topic_targets(run, cluster_id)

    if targets.empty:
        st.info("No uncontacted companies match this topic yet.")
        return

    if theme:
        counts = so.basis_counts(targets)
        with st.container(horizontal=True):
            st.metric("Companies to source", f"{len(targets):,}", border=True)
            st.metric("Fit + signal", counts["Fit + signal"], border=True, help=so.BASIS_HELP["Fit + signal"])
            st.metric("Signal only", counts["Signal only"], border=True, help=so.BASIS_HELP["Signal only"])
            st.metric("Fit only", counts["Fit only"], border=True, help=so.BASIS_HELP["Fit only"])
            st.metric("Seen in last 90 days", so.recent_signal_count(targets, data.AS_OF), border=True)
        with st.container(horizontal=True, vertical_alignment="bottom"):
            bases = st.pills("Basis", so.BASES, selection_mode="multi", default=so.BASES, key=f"so_basis_{key}")
            stages = st.pills("Stage", so.STAGES, selection_mode="multi", key=f"so_stage_{key}")
        shown = so.filter_targets(targets, bases or so.BASES, stages)
    else:
        stages = st.pills("Stage", so.STAGES, selection_mode="multi", key=f"so_stage_{key}")
        shown = targets[targets["STAGE"].isin(stages)].reset_index(drop=True) if stages else targets

    left, right = st.columns([3, 2])
    with left:
        with st.container(border=True):
            st.markdown(f"**{len(shown)} companies to source** · select a row for the company card")
            cols = (["COMPANY_NAME", "SOURCING_SCORE", "BASIS", "STAGE", "HEADCOUNT", "INDUSTRY",
                     "THEME_SIGNALS", "LAST_SIGNAL", "SIGNAL_SOURCES", "PORTCOS"] if theme else
                    ["COMPANY_NAME", "SIMILARITY", "STAGE", "HEADCOUNT", "INDUSTRY", "ALL_SIGNALS", "LAST_SIGNAL"])
            table = st.dataframe(
                shown[cols], hide_index=True, width="stretch", height=430,
                on_select="rerun", selection_mode="single-row", key=f"so_table_{key}",
                column_config={
                    "COMPANY_NAME": "Company", "BASIS": "Basis", "STAGE": "Stage", "HEADCOUNT": "Headcount",
                    "INDUSTRY": "Industry",
                    "SOURCING_SCORE": st.column_config.ProgressColumn("Score", format="%.2f", min_value=0.0,
                                                                      max_value=1.0),
                    "SIMILARITY": st.column_config.ProgressColumn(
                        "Similarity", format="%.2f", min_value=0.0,
                        max_value=float(shown["SIMILARITY"].max() or 1) if len(shown) else 1.0),
                    "THEME_SIGNALS": st.column_config.NumberColumn("Signals", format="%d"),
                    "ALL_SIGNALS": st.column_config.NumberColumn("Signals (all themes)", format="%d"),
                    "LAST_SIGNAL": st.column_config.DateColumn("Last seen"),
                    "SIGNAL_SOURCES": "Seen in", "PORTCOS": "Portcos",
                },
            )
            st.download_button(":material/download: Sourcing list CSV",
                               shown.drop(columns=["DESCRIPTION"]).to_csv(index=False).encode(),
                               file_name=f"sourcing_{str(name).lower().replace(' ', '_')}.csv",
                               mime="text/csv", key=f"so_csv_{key}", type="tertiary")
            rows = table.selection.rows if table else []
            if rows:
                ss.so_company[key] = shown.iloc[rows[0]]["COMPANY_ID"]
    with right:
        cid = ss.so_company.get(key)
        if cid not in set(shown["COMPANY_ID"]):
            cid = shown.iloc[0]["COMPANY_ID"] if len(shown) else None
        if cid:
            _company_card(run, shown.set_index("COMPANY_ID").loc[cid], cid, theme)


def _company_card(run, c, company_id, theme):
    signals, fit = _card(run, company_id)
    with st.container(border=True):
        st.markdown(f"#### :material/travel_explore: {c['COMPANY_NAME']}")
        st.markdown(f":green-badge[Not in CRM] :blue-badge[{c['STAGE']}] "
                    f"{int(c['HEADCOUNT']):,} people · {c['HQ_REGION']} · founded {int(c['FOUNDED_YEAR'])}")
        st.caption(f"{c['INDUSTRY']} · {c['SUB_INDUSTRY']} · {c['DOMAIN']}")
        st.write(c["DESCRIPTION"])
        if len(fit):
            st.markdown("**Best-fitting themes** (Cortex)")
            top = fit.head(5)
            st.dataframe(top, hide_index=True, width="stretch",
                         column_config={"THEME": "Theme", "FIT_RANK": st.column_config.NumberColumn("Rank", format="%d"),
                                        "SIMILARITY": st.column_config.ProgressColumn(
                                            "Fit", format="%.2f", min_value=0.0,
                                            max_value=float(fit["SIMILARITY"].max() or 1))})
        st.markdown(f"**Signals** · {len(signals)}")
        if signals.empty:
            st.caption("Not yet seen in any source. Found by profile fit only.")
        for r in signals.head(8).itertuples(index=False):
            on_topic = " :violet-badge[this theme]" if theme and r.THEME == theme else ""
            st.markdown(f":gray-badge[{r.SOURCE}]{on_topic} {pd.to_datetime(r.SIGNAL_DATE):%b %d, %Y}")
            st.caption(r.SNIPPET)
