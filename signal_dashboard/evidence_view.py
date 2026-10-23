"""Evidence Explorer tab: attribution overview and Theme › Source › Company › evidence drill-down."""

from datetime import timedelta

import pandas as pd
import streamlit as st

from signal_lib import charts, evidence as ev

CACHE_TTL = timedelta(minutes=15)
PAGE_SIZES = [25, 50, 100, 200]
EXPLAIN = {
    "CRM note": "Direct CRM call, meeting or email that mentions the theme",
    "Portco intro": "CRM note where the conversation came via a portfolio company",
    "Portco network": "Enterprise named alongside a portfolio company on the theme",
    "Expert call": "Expert network call document on the theme",
    "External scan": "Company surfaced by the external market scan",
}


def _state():
    ss = st.session_state
    ss.setdefault("ev_theme", None)
    ss.setdefault("ev_entity", None)
    ss.setdefault("ev_sources", list(ev.SOURCES))
    ss.setdefault("ev_search", "")
    ss.setdefault("ev_focus_seen", None)
    ss.setdefault("ev_last_pick", None)
    return ss


def _clear_entity():
    st.session_state.ev_entity = None


def _clear_all():
    ss = st.session_state
    ss.ev_entity = None
    ss.ev_sources = list(ev.SOURCES)
    ss.ev_search = ""


def render(run, focus_theme, lifted, saved, show_overview=True):
    """show_overview=False hides the all-theme attribution chart and pins the explorer to focus_theme."""
    @st.cache_data(ttl=CACHE_TTL)
    def load_overview(version=2):  # bump to drop results cached by older code
        return ev.attribution_shares(ev.attribution(run)), ev.corroboration(run)

    @st.cache_data(ttl=CACHE_TTL, max_entries=64)
    def load_theme(theme):
        return ev.source_matrix(ev.entity_sources(run, theme)), ev.timeline(run, theme)

    @st.cache_data(ttl=CACHE_TTL, max_entries=256)
    def load_items(theme, sources, entity, search, limit):
        return (ev.evidence(run, theme, list(sources), entity, search or None, limit),
                ev.evidence_count(run, theme, list(sources), entity, search or None))

    @st.cache_data(ttl=CACHE_TTL, max_entries=128)
    def load_profile(entity):
        return ev.entity_profile(run, entity)

    ss = _state()
    # The sidebar focus theme seeds the explorer; a later sidebar change re-seeds it.
    if ss.ev_focus_seen != focus_theme:
        ss.ev_focus_seen = focus_theme
        ss.ev_theme = focus_theme
        ss.ev_entity = None

    with st.spinner("Loading attribution…"):
        attr, corr = load_overview()

    # ---------------------------------------------------------- 1. attribution overview
    if show_overview:
        with st.container(border=True):
            st.markdown("**Where each theme's evidence comes from** · click a bar to drill into a theme")
            event = st.altair_chart(
                charts.attribution_bars(attr, corr, ss.ev_theme),
                on_select="rerun", key="ev_attr_chart", width="stretch",
            )
            picks = (event.selection or {}).get(charts.THEME_PICK) or [] if event else []
            pick = picks[0].get("THEME") if picks else None
            if pick and pick != ss.ev_last_pick:
                ss.ev_last_pick = pick
                if pick != ss.ev_theme:
                    ss.ev_theme = pick
                    ss.ev_entity = None
                    st.rerun()
            st.caption(" · ".join(f"**{k}**: {v}" for k, v in EXPLAIN.items()))

    theme = ss.ev_theme if show_overview else focus_theme
    if not theme:
        st.info("Pick a theme above to see its evidence.")
        return

    # ---------------------------------------------------------- 2. breadcrumb + theme summary
    with st.container(horizontal=True, vertical_alignment="center"):
        crumb = [f":material/label: **{theme}**"]
        if set(ss.ev_sources) != set(ev.SOURCES):
            crumb.append(":material/filter_alt: " + ", ".join(ss.ev_sources))
        if ss.ev_entity:
            crumb.append(f":material/apartment: **{ss.ev_entity}**")
        if ss.ev_search:
            crumb.append(f':material/search: "{ss.ev_search}"')
        st.markdown("  ›  ".join(crumb))
        st.button(":material/close: Reset drill-down", on_click=_clear_all, key="ev_reset",
                  type="tertiary")

    c = corr.set_index("THEME").loc[theme] if theme in set(corr["THEME"]) else None
    t_attr = attr[attr["THEME"] == theme]
    intro = ev.intro_share_check(t_attr, saved["themes"])
    with st.container(horizontal=True):
        if c is not None:
            st.metric("Confidence", c["CONFIDENCE"], f"{int(c['SOURCE_FAMILIES'])} of 4 independent sources",
                      delta_color="off", border=True)
            st.metric("Companies in 2+ sources", int(c["MULTI_SOURCE_ENTITIES"]), border=True)
        st.metric("Evidence items", f"{int(t_attr['EVIDENCE_ITEMS'].sum()):,}", border=True)
        if len(intro) and pd.notna(intro.loc[0, "CRM_INTRO_SHARE"]):
            saved_share = intro.loc[0, "SHARE_FROM_PORTCO_INTROS"]
            st.metric("CRM notes via portco intros", f"{intro.loc[0, 'CRM_INTRO_SHARE']:.0%}",
                      f"{saved_share:.0%} in the current window" if pd.notna(saved_share) else None,
                      delta_color="off", border=True,
                      help="All-time share of this theme's CRM notes that came through a portfolio-"
                           "company intro, with the Apr–Oct 2026 share from DERIVED.ENTERPRISE_THEMES.")

    matrix, tl = load_theme(theme)

    left, right = st.columns([3, 2])
    with left:
        with st.container(border=True):
            st.markdown("**Evidence over time by source**")
            if tl.empty:
                st.caption("No dated evidence for this theme.")
            else:
                st.altair_chart(charts.evidence_timeline(tl), width="stretch")
    with right:
        with st.container(border=True):
            st.markdown("**Top companies × source**")
            if matrix.empty:
                st.caption("No company-level evidence.")
            else:
                st.altair_chart(charts.source_dot_matrix(matrix, ev.SOURCES), width="stretch")

    # ---------------------------------------------------------- 3. companies (row select drills in)
    with st.container(border=True):
        st.markdown("**Companies behind this theme** · select a row to see that company's evidence")
        table = st.dataframe(
            matrix, hide_index=True, width="stretch", height=300,
            on_select="rerun", selection_mode="single-row", key=f"ev_entities_{theme}",
            column_config={
                "ENTITY_NAME": "Company", "ENTITY_TYPE": "Type",
                **{s: st.column_config.NumberColumn(s, format="%d") for s in ev.SOURCES},
                "TOTAL": st.column_config.ProgressColumn(
                    "Total", format="%d", min_value=0,
                    max_value=int(matrix["TOTAL"].max()) if len(matrix) else 1),
                "SOURCE_FAMILIES": st.column_config.NumberColumn("Independent sources", format="%d"),
                "LAST_SEEN": st.column_config.DateColumn("Last seen"),
            },
        )
        rows = table.selection.rows if table else []
        if rows:
            picked = matrix.iloc[rows[0]]["ENTITY_NAME"]
            if picked != ss.ev_entity:
                ss.ev_entity = picked
                st.rerun()

    # ---------------------------------------------------------- 4. evidence cards + 5. profile
    with st.container(horizontal=True, vertical_alignment="bottom"):
        st.pills("Sources", ev.SOURCES, selection_mode="multi", key="ev_sources")
        st.text_input("Search evidence", key="ev_search", placeholder="e.g. pilot, budget, Harbor",
                      width=280)
        limit = st.selectbox("Show", PAGE_SIZES, index=0, key="ev_limit", width=110)
        if ss.ev_entity:
            st.button(f":material/close: {ss.ev_entity}", on_click=_clear_entity, key="ev_clear_entity")

    sources = tuple(s for s in ev.SOURCES if s in (ss.ev_sources or []))
    if not sources:
        st.warning("Select at least one source.")
        return
    with st.spinner("Finding evidence…"):
        items, total = load_items(theme, sources, ss.ev_entity, ss.ev_search.strip(), limit)

    cards_col, profile_col = st.columns([3, 2]) if ss.ev_entity else (st.container(), None)
    with cards_col:
        with st.container(horizontal=True, vertical_alignment="center"):
            st.markdown(f"**{len(items):,} of {total:,} evidence items**")
            st.download_button(":material/download: CSV", items.to_csv(index=False).encode(),
                               file_name="evidence.csv", mime="text/csv", key="ev_csv",
                               type="tertiary")
        if items.empty:
            st.caption("No evidence matches these filters.")
        for row in items.itertuples(index=False):
            with st.container(border=True):
                when = f"{pd.to_datetime(row.EVIDENCE_DATE):%b %d, %Y}" if pd.notna(row.EVIDENCE_DATE) else "undated"
                who = f" · {row.RECORDED_BY}" if row.RECORDED_BY else ""
                st.markdown(f"{_badge(row.SOURCE)} **{row.ENTITY_NAME}** · {when}{who}")
                st.text(row.SNIPPET)
                foot = f"source: {row.SOURCE_TABLE} · {row.SOURCE_KEY} · id {row.EVIDENCE_ID}"
                if row.LINK:
                    st.caption(f"{foot} · [open link]({row.LINK})")
                else:
                    st.caption(foot)

    if profile_col is not None:
        with profile_col:
            _profile(load_profile(ss.ev_entity), ss.ev_entity)


def _badge(source):
    color = {"CRM note": "blue", "Portco intro": "green", "Portco network": "violet",
             "Expert call": "red", "External scan": "orange"}.get(source, "gray")
    return f":{color}-badge[{source}]"


def _profile(profile, entity):
    with st.container(border=True):
        st.markdown(f"#### :material/apartment: {entity}")
        acct = profile["account"]
        if len(acct):
            a = acct.iloc[0]
            flags = []
            if a["UNOWNED"]:
                flags.append(":orange-badge[Unowned]")
            if a["STALE"]:
                flags.append(":red-badge[No touch 90+ days]")
            st.markdown(
                f"{a['SEGMENT']} · owner **{a['OWNER_NAME'] or '—'}** · last activity "
                f"{pd.to_datetime(a['DATE_OF_LAST_ACTIVITY']):%b %d, %Y}" if pd.notna(a["DATE_OF_LAST_ACTIVITY"])
                else f"{a['SEGMENT']} · owner **{a['OWNER_NAME'] or '—'}** · no recorded activity"
            )
            if flags:
                st.markdown(" ".join(flags))
            if a["WEBSITE"]:
                st.caption(a["WEBSITE"])
        else:
            st.caption("Not matched to a CRM account.")
        mix = profile["mix"]
        if len(mix):
            st.markdown("**Evidence across all themes**")
            wide = mix.pivot_table(index="THEME", columns="SOURCE", values="ITEMS",
                                   aggfunc="sum", fill_value=0)
            wide = wide[[s for s in ev.SOURCES if s in wide.columns]]
            wide["TOTAL"] = wide.sum(axis=1)
            st.dataframe(wide.sort_values("TOTAL", ascending=False), width="stretch")
