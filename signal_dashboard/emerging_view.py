"""Emerging topics tab: clusters discovered from record embeddings, ranked and reviewable.

Drill path: ranked list / uniqueness-velocity map -> topic card (definition, weekly
additions by source, companies, records closest to the cluster centre) -> review actions.
"""

from datetime import timedelta

import pandas as pd
import streamlit as st

from signal_lib import charts, emerging as em

CACHE_TTL = timedelta(minutes=15)


def render(run):
    @st.cache_data(ttl=CACHE_TTL)
    def load_overview(version=1):
        return em.signals(run), em.weekly_all(run)

    @st.cache_data(ttl=CACHE_TTL, max_entries=64)
    def load_detail(cluster_id):
        return em.weekly(run, cluster_id), em.companies(run, cluster_id), em.members(run, cluster_id, 30)

    ss = st.session_state
    ss.setdefault("em_cluster", None)
    ss.setdefault("em_last_pick", None)

    st.caption(
        "Every CRM note, portfolio intro, expert call and external-scan record is embedded with Cortex "
        "`AI_EMBED`. Records that match no tracked theme are grouped by meaning as they arrive; a group "
        "becomes a cluster once enough similar records from several companies build up. Each cluster is "
        "scored on uniqueness, velocity and spread, and named by Cortex. "
        + " · ".join(f"**{k}**: {v}" for k, v in em.STATUS_HELP.items() if k in
                     ("New topic", "Emerging sub-topic", "Watch", "Noise"))
    )

    with st.spinner("Loading emerging topics…"):
        sig, wk_all = load_overview()
    if sig.empty:
        st.info("No clusters yet. They appear once enough similar, untracked records arrive.")
        return

    counts = em.status_counts(sig)
    with st.container(horizontal=True):
        st.metric("New topics", counts["New topic"], border=True, help=em.STATUS_HELP["New topic"])
        st.metric("Emerging sub-topics", counts["Emerging sub-topic"], border=True,
                  help=em.STATUS_HELP["Emerging sub-topic"])
        st.metric("Watch", counts["Watch"], border=True, help=em.STATUS_HELP["Watch"])
        st.metric("Noise", counts["Noise"], border=True, help=em.STATUS_HELP["Noise"])
        st.metric("Reviewed", int(sig["REVIEWED"].sum()), border=True,
                  help="Promoted, merged or dismissed by a reviewer")

    left, right = st.columns([3, 2])
    with left:
        with st.container(border=True):
            st.markdown("**Uniqueness vs velocity** · bubble size = companies · click a topic")
            event = st.altair_chart(charts.emergence_map(sig, ss.em_cluster),
                                    on_select="rerun", key="em_map", width="stretch")
            picks = ((event.selection or {}).get(charts.CLUSTER_PICK) or []) if event else []
            pick = picks[0].get("CLUSTER_ID") if picks else None
            if pick and pick != ss.em_last_pick:
                ss.em_last_pick = pick
                if pick != ss.em_cluster:
                    ss.em_cluster = pick
                    st.rerun()
    with right:
        with st.container(border=True):
            st.markdown("**Ranked by emergence score**")
            ranked = sig.assign(
                TOPIC=sig["TOPIC_NAME"].fillna(sig["CLUSTER_ID"]),
                TREND=[em.sparkline(wk_all, c) for c in sig["CLUSTER_ID"]],
            )
            table = st.dataframe(
                ranked[["TOPIC", "STATUS", "TREND", "ACCOUNTS", "VELOCITY", "EMERGENCE_SCORE", "CLUSTER_ID"]],
                hide_index=True, width="stretch", height=380,
                on_select="rerun", selection_mode="single-row", key="em_table",
                column_config={
                    "TOPIC": "Topic", "STATUS": "Status",
                    "TREND": st.column_config.LineChartColumn("Weekly additions (16 wks)", y_min=0),
                    "ACCOUNTS": "Companies",
                    "VELOCITY": st.column_config.NumberColumn("Velocity", format="%.2f×"),
                    "EMERGENCE_SCORE": st.column_config.NumberColumn("Score", format="%.2f"),
                    "CLUSTER_ID": "Id",
                },
            )
            rows = table.selection.rows if table else []
            if rows and ranked.iloc[rows[0]]["CLUSTER_ID"] != ss.em_cluster:
                ss.em_cluster = ranked.iloc[rows[0]]["CLUSTER_ID"]
                st.rerun()

    if not ss.em_cluster or ss.em_cluster not in set(sig["CLUSTER_ID"]):
        st.info("Select a topic in the map or table to see its evidence.")
        return
    _topic_card(run, sig.set_index("CLUSTER_ID").loc[ss.em_cluster], ss.em_cluster,
                *load_detail(ss.em_cluster), on_change=lambda: (load_overview.clear(), load_detail.clear()))


def _topic_card(run, s, cluster_id, weekly, comps, mem, on_change):
    with st.container(border=True):
        name = s["TOPIC_NAME"] if pd.notna(s["TOPIC_NAME"]) else cluster_id
        with st.container(horizontal=True, vertical_alignment="center"):
            st.markdown(f"### :material/bubble_chart: {name}")
            st.markdown(f":violet-badge[{s['STATUS']}]")
        if pd.notna(s["DEFINITION"]):
            st.write(s["DEFINITION"])
        if pd.notna(s["REASON"]):
            st.caption(f"Cortex: {s['REASON']}")
        related = s["RELATED_THEME"] if pd.notna(s["RELATED_THEME"]) else None
        st.caption(
            (f"Sub-topic of **{related}**" if related else f"Nearest tracked theme: **{s['NEAREST_THEME']}** "
             f"(similarity {s['THEME_SIMILARITY']:.2f})")
            + f" · emerged {pd.to_datetime(s['EMERGED_ON']):%b %d, %Y} · cluster {cluster_id}"
        )
        with st.container(horizontal=True):
            st.metric("Records", int(s["RECORDS"]), f"{int(s['RECENT_RECORDS'])} in last 8 weeks",
                      delta_color="off", border=True)
            st.metric("Velocity", f"{s['VELOCITY']:.2f}×", "recent vs prior 8 weeks", delta_color="off",
                      border=True)
            st.metric("Companies", int(s["ACCOUNTS"]), f"{int(s['REPS'])} reps · {int(s['INDUSTRIES'])} industries",
                      delta_color="off", border=True)
            st.metric("Sources", int(s["SOURCES"]), s["SOURCE_LIST"], delta_color="off", border=True)
            st.metric("Top company share", f"{s['TOP_ACCOUNT_SHARE']:.0%}",
                      "noise if above 50%", delta_color="off", border=True)

        left, right = st.columns([3, 2])
        with left:
            st.markdown("**Weekly additions by source**")
            st.altair_chart(charts.cluster_timeline(weekly), width="stretch")
            st.markdown("**Records closest to the cluster centre**")
            for row in mem.head(12).itertuples(index=False):
                with st.container(border=True):
                    st.markdown(f":blue-badge[{row.SOURCE}] **{row.ENTITY_NAME}** · "
                                f"{pd.to_datetime(row.RECORD_DATE):%b %d, %Y} · similarity {row.SIMILARITY:.2f}")
                    st.text(row.TEXT)
                    st.caption(f"record {row.RECORD_ID}")
        with right:
            st.markdown("**Companies**")
            st.dataframe(
                comps, hide_index=True, width="stretch", height=320,
                column_config={"ENTITY_NAME": "Company", "INDUSTRY": "Industry", "RECORDS": "Records",
                               "LAST_SEEN": st.column_config.DateColumn("Last seen"),
                               "SOURCES": "Sources", "OWNER_NAME": "Owner"},
            )
            st.download_button(":material/download: Topic records CSV", mem.to_csv(index=False).encode(),
                               file_name=f"emerging_{cluster_id}.csv", mime="text/csv",
                               key=f"em_csv_{cluster_id}", type="tertiary")
            _review(run, s, cluster_id, name, on_change)


def _review(run, s, cluster_id, name, on_change):
    st.markdown("**Review**")
    with st.form(f"em_promote_{cluster_id}", border=True):
        st.caption("Promote adds this topic to the tracked themes, so every tab picks it up.")
        theme = st.text_input("Theme name", value=str(name))
        phrase = st.text_input("CRM match phrase", value=em.suggested_phrase(s["TOPIC_NAME"], s["KEY_TERMS"]),
                               help="Notes containing this phrase are counted for the theme.")
        definition = st.text_area("Definition", value=str(s["DEFINITION"] or ""), height=80)
        if st.form_submit_button(":material/upgrade: Promote to theme", type="primary"):
            if theme.strip() and phrase.strip() and definition.strip():
                st.success(em.promote(run, cluster_id, theme, phrase, definition))
                on_change()
            else:
                st.warning("Theme name, phrase and definition are all required.")
    with st.container(horizontal=True):
        if st.button(":material/call_merge: Merge into nearest theme", key=f"em_merge_{cluster_id}"):
            st.success(em.review(run, cluster_id, "Merged", s["RELATED_THEME"] or s["NEAREST_THEME"]))
            on_change()
        if st.button(":material/block: Dismiss", key=f"em_dismiss_{cluster_id}"):
            st.success(em.review(run, cluster_id, "Dismissed"))
            on_change()
        if s["REVIEWED"] and st.button(":material/undo: Reopen", key=f"em_reopen_{cluster_id}"):
            st.success(em.review(run, cluster_id, "Reopen"))
            on_change()
