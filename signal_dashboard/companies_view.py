"""Company fit tab: does each company's profile actually relate to the themes it talks about?

Drill path: theme -> fit-vs-mentions quadrant -> company card (profile, every theme's fit
vs mentions) -> that company's evidence on the selected theme.
"""

from datetime import timedelta

import pandas as pd
import streamlit as st

from signal_lib import charts, companies as co, evidence as ev

CACHE_TTL = timedelta(minutes=15)


def _clear_company():
    st.session_state.cf_company = None


def render(run, focus_theme, theme_names, fixed=False):
    """fixed=True renders for focus_theme without the tab's own theme picker."""
    @st.cache_data(ttl=CACHE_TTL, max_entries=64)
    def load_theme(theme):
        return co.theme_companies(run, theme)

    @st.cache_data(ttl=CACHE_TTL, max_entries=128)
    def load_card(name):
        return co.company_card(run, name)

    @st.cache_data(ttl=CACHE_TTL, max_entries=256)
    def load_evidence(theme, name):
        return ev.evidence(run, theme, None, name, None, 50)

    ss = st.session_state
    ss.setdefault("cf_company", None)
    ss.setdefault("cf_theme_seen", None)
    ss.setdefault("cf_last_pick", None)

    st.caption(
        "Company descriptions are matched to theme definitions with Cortex `AI_EMBED` "
        "(snowflake-arctic-embed-l-v2.0). A theme is a **profile fit** when it is in the "
        f"company's top {co.TOP_FIT_RANK} of 21 themes by similarity. "
        + " · ".join(f"**{k}**: {v}" for k, v in co.RELATIONSHIP_HELP.items())
    )

    theme = focus_theme if fixed else st.selectbox(
        "Theme", theme_names, index=theme_names.index(focus_theme) if focus_theme in theme_names else 0,
        key="cf_theme")
    if ss.cf_theme_seen != theme:
        ss.cf_theme_seen = theme
        ss.cf_company = None

    with st.spinner(f"Matching companies to {theme}…"):
        comps = load_theme(theme)
    counts = co.relationship_counts(comps)
    mentioners = counts["Confirmed"] + counts["Talking, off-profile"]

    with st.container(horizontal=True):
        st.metric("Confirmed", f"{counts['Confirmed']:,}", border=True,
                  help=co.RELATIONSHIP_HELP["Confirmed"])
        st.metric("Latent fit", f"{counts['Latent fit']:,}", border=True,
                  help=co.RELATIONSHIP_HELP["Latent fit"])
        st.metric("Talking, off-profile", f"{counts['Talking, off-profile']:,}", border=True,
                  help=co.RELATIONSHIP_HELP["Talking, off-profile"])
        st.metric("Mentioners on-profile",
                  f"{counts['Confirmed'] / mentioners:.0%}" if mentioners else "—",
                  f"of {mentioners:,} companies mentioning it", delta_color="off", border=True)

    left, right = st.columns([3, 2])
    with left:
        with st.container(border=True):
            st.markdown(f"**{theme} · profile fit vs CRM mentions** · click a company")
            event = st.altair_chart(charts.fit_quadrant(comps, ss.cf_company),
                                    on_select="rerun", key=f"cf_quadrant_{theme}", width="stretch")
            picks = ((event.selection or {}).get(charts.COMPANY_PICK) or []) if event else []
            pick = picks[0].get("ACCOUNT_NAME") if picks else None
            if pick and pick != ss.cf_last_pick:
                ss.cf_last_pick = pick
                if pick != ss.cf_company:
                    ss.cf_company = pick
                    st.rerun()
    with right:
        with st.container(border=True):
            st.markdown("**Outreach: latent fit** · fits the profile, not yet discussed")
            outreach = co.outreach_list(comps)
            st.dataframe(
                outreach[["ACCOUNT_NAME", "INDUSTRY", "SIMILARITY", "OWNER_NAME", "UNOWNED", "STALE"]],
                hide_index=True, width="stretch", height=330,
                column_config={
                    "ACCOUNT_NAME": "Company", "INDUSTRY": "Industry",
                    "SIMILARITY": st.column_config.NumberColumn("Fit", format="%.2f"),
                    "OWNER_NAME": "Owner",
                    "UNOWNED": st.column_config.CheckboxColumn("Unowned"),
                    "STALE": st.column_config.CheckboxColumn("90+ days"),
                },
            )
            st.download_button(":material/download: Outreach CSV",
                               outreach.to_csv(index=False).encode(),
                               file_name=f"latent_fit_{theme.lower().replace(' ', '_')}.csv",
                               mime="text/csv", key="cf_outreach_csv", type="tertiary")

    with st.container(border=True):
        rels = st.pills("Show", co.RELATIONSHIPS, selection_mode="multi",
                        default=["Confirmed", "Latent fit", "Talking, off-profile"], key="cf_rels")
        shown = comps[comps["RELATIONSHIP"].isin(rels or co.RELATIONSHIPS)].reset_index(drop=True)
        table = st.dataframe(
            shown, hide_index=True, width="stretch", height=320,
            on_select="rerun", selection_mode="single-row", key=f"cf_table_{theme}",
            column_config={
                "ACCOUNT_NAME": "Company", "INDUSTRY": "Industry", "RELATIONSHIP": "Relationship",
                "SIMILARITY": st.column_config.ProgressColumn("Fit", format="%.2f", min_value=0.0,
                                                              max_value=float(comps["SIMILARITY"].max() or 1)),
                "PROFILE_FIT": None, "FIT_RANK": st.column_config.NumberColumn("Fit rank", format="%d"),
                "STATED_PRIORITY": st.column_config.CheckboxColumn("Stated priority"),
                "CRM_MENTIONS": "Mentions", "CURRENT_MENTIONS": "Since Apr '26",
                "LAST_MENTION": st.column_config.DateColumn("Last mention"),
                "OTHER_SOURCE_HITS": "Other sources", "OWNER_NAME": "Owner",
                "UNOWNED": st.column_config.CheckboxColumn("Unowned"),
                "STALE": st.column_config.CheckboxColumn("90+ days"),
            },
        )
        rows = table.selection.rows if table else []
        if rows and shown.iloc[rows[0]]["ACCOUNT_NAME"] != ss.cf_company:
            ss.cf_company = shown.iloc[rows[0]]["ACCOUNT_NAME"]
            st.rerun()

    if not ss.cf_company:
        st.info("Select a company in the chart or table to see its profile and evidence.")
        return

    _company_card(load_card(ss.cf_company), ss.cf_company, theme,
                  load_evidence(theme, ss.cf_company))


def _company_card(card, name, theme, items):
    prof, themes = card["profile"], card["themes"]
    with st.container(border=True):
        with st.container(horizontal=True, vertical_alignment="center"):
            st.markdown(f"### :material/apartment: {name}")
            st.button(":material/close: Close", on_click=_clear_company, key="cf_close", type="tertiary")
        if len(prof):
            p = prof.iloc[0]
            st.markdown(
                f"{p['INDUSTRY']} · {p['SUB_INDUSTRY']} · {p['EMPLOYEE_BAND']} employees · "
                f"{p['HQ_REGION']} · founded {p['FOUNDED_YEAR']} · {p['SEGMENT']} · "
                f"owner **{p['OWNER_NAME'] or 'unassigned'}**"
            )
            st.text(p["DESCRIPTION"])
            st.caption(f"Stated priorities: {p['STATED_PRIORITIES']}")
        sel = themes[themes["THEME"] == theme]
        share = co.on_profile_share(themes)
        with st.container(horizontal=True):
            if len(sel):
                s = sel.iloc[0]
                st.metric(f"{theme}", s["RELATIONSHIP"],
                          f"fit rank {int(s['FIT_RANK'])} of 21 · {int(s['CRM_MENTIONS'])} mentions",
                          delta_color="off", border=True)
            st.metric("CRM mentions on-profile", f"{share:.0%}" if share is not None else "—",
                      f"{int(themes['CRM_MENTIONS'].sum())} theme mentions in total",
                      delta_color="off", border=True,
                      help=f"Share of this company's theme mentions that fall on its top "
                           f"{co.TOP_FIT_RANK} Cortex-matched themes.")
        left, right = st.columns([2, 3])
        with left:
            st.markdown("**Fit vs mentions, every theme** (number = CRM mentions)")
            st.altair_chart(charts.company_theme_bars(themes), width="stretch")
        with right:
            st.markdown(f"**Evidence: {name} × {theme}**")
            if items.empty:
                st.caption("No evidence for this company on this theme. "
                           "If it is a latent fit, this is an outreach opportunity.")
            for row in items.head(20).itertuples(index=False):
                with st.container(border=True):
                    when = (f"{pd.to_datetime(row.EVIDENCE_DATE):%b %d, %Y}"
                            if pd.notna(row.EVIDENCE_DATE) else "undated")
                    st.markdown(f":blue-badge[{row.SOURCE}] {when}"
                                + (f" · {row.RECORDED_BY}" if row.RECORDED_BY else ""))
                    st.text(row.SNIPPET)
                    st.caption(f"source: {row.SOURCE_TABLE} · {row.SOURCE_KEY}")
