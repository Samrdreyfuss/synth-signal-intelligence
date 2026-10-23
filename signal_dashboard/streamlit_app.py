import importlib
import os
import sys
from datetime import timedelta

import pandas as pd
import streamlit as st

# A running app process keeps already-imported modules, so after files change it can mix new
# streamlit_app.py with an old signal_lib. Reload everything when the library version differs.
CODE_VERSION = 7
if "signal_lib" in sys.modules and getattr(sys.modules["signal_lib"], "CODE_VERSION", None) != CODE_VERSION:
    for _name in ["signal_lib.theme", "signal_lib.data", "signal_lib.metrics", "signal_lib.evidence",
                  "signal_lib.companies", "signal_lib.emerging", "signal_lib.topics", "signal_lib.sourcing", "signal_lib.charts",
                  "signal_lib", "evidence_view", "companies_view", "emerging_view", "sourcing_view"]:
        if _name in sys.modules:
            importlib.reload(sys.modules[_name])
        else:
            importlib.import_module(_name)

import companies_view
import emerging_view
import evidence_view
import sourcing_view
from signal_lib import charts, data, emerging as em, evidence as ev, metrics, topics as tp

st.set_page_config(
    page_title="Signal Intelligence",
    page_icon=":material/radar:",
    layout="wide",
)

CACHE_TTL = timedelta(minutes=15)
# Bump when the shape or types of loaded data change, so cached results from older code are dropped.
DATA_VERSION = 4
TOPICS_TAB = ":material/radar: Topics"
RESEARCH_TAB = ":material/manage_search: Research a topic"
SECTIONS = {
    "Overview": ":material/insights:", "Evidence": ":material/fact_check:",
    "Companies": ":material/apartment:", "Actions": ":material/task_alt:", "Context": ":material/hub:",
}
CURRENT_WINDOW_MONTHS = 200 / (365.25 / 12)  # Apr 1 - Oct 17 2026, same as DERIVED.ENTERPRISE_THEMES

conn = st.connection("snowflake", ttl=os.getenv("SNOWFLAKE_CONNECTION_TTL"))


def run(sql, params=None):
    # ttl=0: no query-level cache. Caching lives only in the @st.cache_data loaders,
    # so "Refresh data" and DATA_VERSION control every cached result.
    return conn.query(sql, params=params, ttl=0)


# ------------------------------------------------------------------ cached loaders

@st.cache_data(ttl=CACHE_TTL)
def load_saved(version=DATA_VERSION):
    return {
        "loaded_at": pd.Timestamp.now(tz="America/Los_Angeles"),
        "themes": data.enterprise_themes(run),
        "quarterly": data.enterprise_quarterly(run),
        "portcos": data.enterprise_portcos(run),
        "expert_themes": data.expert_themes(run),
        "expert_examples": data.expert_examples(run),
        "scan": data.external_scan(run),
        "fde": data.fde_quarterly(run),
    }


@st.cache_data(ttl=CACHE_TTL)
def load_health(version=DATA_VERSION):
    return data.account_health(run)


@st.cache_data(ttl=CACHE_TTL)
def load_topic_inputs(version=DATA_VERSION):
    return {
        "corr": ev.corroboration(run),
        "signals": em.signals(run),
        "cluster_weekly": em.weekly_all(run),
        "theme_weekly": tp.theme_weekly(run),
        "definitions": tp.theme_definitions(run),
    }


@st.cache_data(ttl=CACHE_TTL, max_entries=64)
def load_theme_live(theme, version=DATA_VERSION):
    return {
        "monthly": metrics.monthly_share(data.monthly_mentions(run, theme)),
        "accounts": data.theme_accounts(run, theme),
        "excerpts": data.theme_excerpts(run, theme, limit=25),
    }


def clear_caches():
    # Clears every @st.cache_data loader, including those in the view modules.
    st.cache_data.clear()


# ------------------------------------------------------------------ click-through to Research
# Callbacks run before the script, so setting the tab and picker here takes effect this rerun.

def open_topic(topic_id):
    if topic_id:
        st.session_state.topic = topic_id
        st.session_state.main_tab = RESEARCH_TAB


def _on_table_pick():
    rows = st.session_state.topics_table.selection.rows
    ids = st.session_state.get("_shown_ids", [])
    if rows and rows[0] < len(ids):
        open_topic(ids[rows[0]])


def _on_map_pick():
    picks = (st.session_state.topic_map.selection or {}).get(charts.TOPIC_PICK) or []
    if picks:
        open_topic(picks[0].get("TOPIC_ID"))


# ------------------------------------------------------------------ header (static first)

st.markdown("## :material/radar: Signal Intelligence")
st.caption(
    f"Tracked themes and newly discovered topics from CRM activity, portfolio introductions, expert "
    f"calls and an external scan · current window **Apr 1 – {data.AS_OF:%b %d, %Y}** vs prior 12 months · "
    f"synthetic data from `{data.DB}`"
)

with st.spinner("Loading signals…"):
    saved = load_saved()
    health = load_health()
    ti = load_topic_inputs()

lifted = metrics.theme_lift(saved["themes"])
theme_names = [t for t in lifted["THEME"] if t != metrics.BASELINE_THEME]
topics = tp.build(lifted, ti["corr"], ti["signals"], ti["theme_weekly"], ti["cluster_weekly"],
                  metrics.BASELINE_THEME, definitions=ti["definitions"])

ss = st.session_state
DEFAULT_TOPIC = tp.theme_id("Voice AI")
if ss.get("topic") not in set(topics["TOPIC_ID"]):
    ss.topic = DEFAULT_TOPIC if DEFAULT_TOPIC in set(topics["TOPIC_ID"]) else topics["TOPIC_ID"].iloc[0]

# ------------------------------------------------------------------ sidebar

with st.sidebar:
    st.markdown("### :material/tune: Account filters")
    segments = st.pills("Account segment", ["Portfolio", "Prospect"],
                        selection_mode="multi", default=["Portfolio", "Prospect"])
    only_actionable = st.toggle("Only unowned or 90+ days untouched", value=True)
    st.caption("Apply to action lists in Research.")
    st.divider()
    st.button(":material/refresh: Refresh data", on_click=clear_caches, width="stretch")
    st.caption(f"Data loaded {saved['loaded_at']:%b %d, %H:%M:%S} PT · app data version {DATA_VERSION}")
    st.caption(f"Theme momentum is lift vs **{metrics.BASELINE_THEME}**; discovered-topic momentum is "
               "velocity (last 8 weeks ÷ prior 8).")

topics_tab, research_tab = st.tabs([TOPICS_TAB, RESEARCH_TAB], key="main_tab", on_change="rerun")


# ================================================================== TAB 1: TOPICS

def render_topics():
    # Map first. It follows the table filters below, read from their state (defaults on first load).
    mapped = tp.visible(topics, ss.get("tp_kinds", tp.KINDS), ss.get("tp_status"), ss.get("tp_hidden", False))
    with st.container(border=True):
        st.markdown("**Topic map** · momentum vs reach, each panel on its own scale · "
                    "bubble = mentions · dashed line = 1× · click a topic to research it")
        st.altair_chart(charts.topic_map(mapped, ss.topic), on_select=_on_map_pick,
                        key="topic_map", width="content")

    k = metrics.headline_kpis(lifted, health)
    sm = tp.summary(topics)
    growth = ((k["current_mentions"] / CURRENT_WINDOW_MONTHS) / (k["prior_mentions"] / 12) - 1
              if k["prior_mentions"] else 0)
    with st.container(horizontal=True):
        st.metric("Topics picked up", sm["tracked"] + sm["discovered"],
                  f"{sm['tracked']} tracked · {sm['discovered']} discovered", delta_color="off", border=True)
        st.metric("New topics discovered", sm["new"], f"+ {sm['sub']} emerging sub-topics",
                  delta_color="off", border=True, help=em.STATUS_HELP["New topic"])
        st.metric("Themes outpacing baseline", f"{k['themes_outpacing']} / {k['themes_total']}", border=True)
        st.metric("Current-window mentions", f"{k['current_mentions']:,}",
                  f"{growth:+.0%} monthly rate vs prior", border=True)
        st.metric("Unowned accounts", f"{k['unowned']:,}",
                  f"{k['unowned'] / k['accounts']:.0%} of {k['accounts']:,}", delta_color="off", border=True)
        st.metric("No touch in 90+ days", f"{k['stale']:,}",
                  f"{k['stale'] / k['accounts']:.0%} of accounts", delta_color="off", border=True)

    new = tp.newest(topics)
    if len(new):
        st.markdown("**:material/fiber_new: What's new**")
        with st.container(horizontal=True):
            for r in new.itertuples(index=False):
                with st.container(border=True, width=300):
                    st.markdown(f"**{r.TOPIC}**  \n:violet-badge[{r.STATUS}]")
                    st.caption((r.DEFINITION or "")[:160])
                    st.caption(f"emerged {r.FIRST_SEEN:%b %d, %Y} · {r.COMPANIES} companies · "
                               f"{r.MOMENTUM:.2f}× velocity")
                    st.button("Research →", key=f"new_{r.TOPIC_ID}", on_click=open_topic,
                              args=(r.TOPIC_ID,), type="tertiary")

    with st.container(horizontal=True, vertical_alignment="bottom"):
        kinds = st.pills("Type", tp.KINDS, selection_mode="multi", default=tp.KINDS, key="tp_kinds")
        all_status = sorted(topics["STATUS"].unique())
        statuses = st.multiselect("Status", all_status, key="tp_status", placeholder="All statuses",
                                  width=360)
        show_hidden = st.toggle("Show noise and reviewed", key="tp_hidden",
                                help="Noise, dismissed, merged and promoted clusters")
    shown = tp.visible(topics, kinds, statuses, show_hidden)
    ss._shown_ids = list(shown["TOPIC_ID"])

    with st.container():
        with st.container(border=True):
            st.markdown(f"**All topics** · {len(shown)} shown · select a row to research it")
            st.dataframe(
                shown[["TOPIC", "KIND", "STATUS", "TREND", "MOMENTUM", "COMPANIES", "MENTIONS",
                       "SOURCES", "CONFIDENCE", "PARENT"]],
                hide_index=True, width="stretch", height=460, key="topics_table",
                on_select=_on_table_pick, selection_mode="single-row",
                column_config={
                    "TOPIC": st.column_config.TextColumn("Topic", width="medium"),
                    "KIND": "Type", "STATUS": "Status",
                    "TREND": st.column_config.LineChartColumn(f"Weekly mentions ({tp.TREND_WEEKS} wks)", y_min=0),
                    "MOMENTUM": st.column_config.NumberColumn(
                        "Momentum", format="%.2f×", help="Themes: lift vs baseline. Discovered: velocity."),
                    "COMPANIES": "Companies", "MENTIONS": st.column_config.NumberColumn(
                        "Mentions", help="Themes: current window. Discovered: all cluster records."),
                    "SOURCES": st.column_config.NumberColumn("Sources", format="%d"),
                    "CONFIDENCE": "Confidence", "PARENT": "Parent theme",
                },
            )

    with st.expander(":material/trending_up: All themes over time"):
        shares = metrics.quarterly_share(saved["quarterly"])
        a, b = st.columns([3, 2])
        with a:
            st.markdown(f"**Quarterly share of enterprise activity** (quarters under "
                        f"{metrics.MIN_QUARTER_ACTIVITIES} activities dropped)")
            st.altair_chart(charts.share_lines(shares, []), width="stretch")
        with b:
            st.markdown("**Year-over-year momentum**")
            st.dataframe(
                metrics.share_momentum(shares), hide_index=True, width="stretch", height=380,
                column_config={
                    "THEME": "Theme", "LATEST_QUARTER": "Quarter",
                    "LATEST_SHARE": st.column_config.NumberColumn("Share", format="percent"),
                    "EARLIER_SHARE": st.column_config.NumberColumn("4 qtrs ago", format="percent"),
                    "CHANGE_PTS": st.column_config.NumberColumn("Δ pts", format="%+.2f"),
                },
            )


# ================================================================== TAB 2: RESEARCH

def render_research():
    ids = list(topics["TOPIC_ID"])
    with st.container(horizontal=True, vertical_alignment="bottom"):
        st.selectbox("Topic", ids, key="topic", format_func=lambda i: tp.label(topics, i), width=460,
                     help="Every tracked theme and discovered topic")
        section = st.segmented_control("Section", list(SECTIONS), default="Overview", required=True,
                                       key="rs_section", format_func=lambda s: f"{SECTIONS[s]} {s}")
    topic_id = ss.topic
    row = topics.set_index("TOPIC_ID").loc[topic_id]

    # header card
    with st.container(border=True):
        with st.container(horizontal=True, vertical_alignment="center"):
            st.markdown(f"### {row['TOPIC']}")
            st.markdown(f":blue-badge[{row['KIND']}] :violet-badge[{row['STATUS']}]")
        if tp.is_theme(topic_id):
            if row["DEFINITION"]:
                st.write(row["DEFINITION"])
            st.caption(f"Tracked theme · CRM match phrase “{data.theme_phrase(row['TOPIC'])}”")
        else:
            s = ti["signals"].set_index("CLUSTER_ID").loc[topic_id]
            if row["DEFINITION"]:
                st.write(row["DEFINITION"])
            st.caption((f"Sub-topic of **{row['PARENT']}**" if row["PARENT"]
                        else f"Nearest tracked theme: **{s['NEAREST_THEME']}**")
                       + f" · emerged {row['FIRST_SEEN']:%b %d, %Y} · cluster {topic_id}")

    if tp.is_theme(topic_id):
        _research_theme(row["TOPIC"], section)
    elif section == "Companies" and _company_mode() == SOURCE_NEW:
        sourcing_view.render(run, cluster_id=topic_id, topic_name=row["TOPIC"])
    else:
        emerging_view.research(run, ti["signals"].set_index("CLUSTER_ID").loc[topic_id], topic_id,
                               section, on_change=clear_caches)


SOURCE_NEW = "New companies to source"
SOURCE_KNOWN = "Companies we talk to"


def _company_mode():
    return st.segmented_control(
        "Companies", [SOURCE_NEW, SOURCE_KNOWN], default=SOURCE_NEW, required=True, key="rs_company_mode",
        format_func=lambda m: (":material/travel_explore: " if m == SOURCE_NEW else ":material/handshake: ") + m,
        help="New: no CRM relationship, for sourcing. Talk to: CRM accounts, whose conversations feed the "
             "trend signals.")


def _research_theme(theme, section):
    with st.spinner(f"Loading live CRM activity for {theme}…"):
        live = load_theme_live(theme)
    sel = lifted.set_index("THEME").loc[theme]

    if section == "Overview":
        c = ti["corr"].set_index("THEME")
        with st.container(horizontal=True):
            st.metric("Lift vs baseline", f"{sel['LIFT']:.2f}×", sel["SIGNAL"],
                      delta_color="normal" if sel["LIFT"] >= 1 else "inverse", border=True,
                      chart_data=live["monthly"]["SHARE"].fillna(0).tail(12).round(4).tolist(),
                      chart_type="area")
            st.metric("Current-window mentions", f"{int(sel['CURRENT_MENTIONS']):,}",
                      f"{int(sel['PRIOR_MENTIONS']):,} in prior 12 months", delta_color="off", border=True)
            st.metric("Enterprises", f"{int(sel['CURRENT_ENTERPRISES']):,}", border=True)
            if pd.notna(sel["SHARE_FROM_PORTCO_INTROS"]):
                st.metric("Via portco intros", f"{sel['SHARE_FROM_PORTCO_INTROS']:.0%}", border=True)
            if theme in c.index:
                st.metric("Confidence", c.loc[theme, "CONFIDENCE"],
                          f"{int(c.loc[theme, 'SOURCE_FAMILIES'])} of 4 independent sources",
                          delta_color="off", border=True)
        left, right = st.columns(2)
        with left:
            with st.container(border=True):
                st.markdown("**Monthly share of live CRM events**")
                st.altair_chart(charts.monthly_area(live["monthly"]), width="stretch")
        with right:
            with st.container(border=True):
                st.markdown("**Quarterly share of enterprise activity** vs other themes")
                st.altair_chart(charts.share_lines(metrics.quarterly_share(saved["quarterly"]), [theme]),
                                width="stretch")
        if theme.lower().startswith("forward deployed"):
            with st.container(border=True):
                st.markdown("**Forward deployed engineering** · enterprise activities vs expert docs")
                st.altair_chart(charts.fde_chart(saved["fde"]), width="stretch")

    elif section == "Evidence":
        evidence_view.render(run, theme, lifted, saved, show_overview=False)
        with st.expander(f":material/format_quote: {len(live['excerpts'])} most recent CRM notes"):
            for r in live["excerpts"].itertuples(index=False):
                st.markdown(f":blue-badge[{r.EVENT_TYPE}] **{r.ACCOUNT_NAME}** · "
                            f"{pd.to_datetime(r.EVENT_DATE):%b %d, %Y} · {r.PERFORMED_BY or 'Unknown'}")
                st.text(r.EXCERPT)

    elif section == "Companies":
        if _company_mode() == SOURCE_NEW:
            sourcing_view.render(run, theme=theme)
        else:
            companies_view.render(run, theme, theme_names, fixed=True)

    elif section == "Actions":
        accounts = metrics.filter_accounts(live["accounts"], segments, only_actionable)
        with st.container(horizontal=True):
            st.metric("Accounts mentioning it", f"{len(live['accounts']):,}", border=True)
            st.metric("Shown with current filters", f"{len(accounts):,}", border=True)
            st.metric("Unowned", f"{int(accounts['UNOWNED'].sum()):,}", border=True)
            st.metric("90+ days untouched", f"{int(accounts['STALE'].sum()):,}", border=True)
        with st.container(border=True):
            st.markdown(f"**CRM accounts to action for {theme}** · filters in the sidebar")
            st.dataframe(
                accounts, hide_index=True, width="stretch",
                column_config={
                    "ACCOUNT_NAME": "Account", "WEBSITE": "Website", "SEGMENT": "Segment",
                    "OWNER_NAME": "Owner",
                    "UNOWNED": st.column_config.CheckboxColumn("Unowned"),
                    "DATE_OF_LAST_ACTIVITY": st.column_config.DateColumn("Last activity"),
                    "STALE": st.column_config.CheckboxColumn("90+ days"),
                    "MENTIONS": st.column_config.ProgressColumn(
                        "Mentions", format="%d", min_value=0,
                        max_value=int(max(1, live["accounts"]["MENTIONS"].max() if len(live["accounts"]) else 1))),
                    "LAST_MENTION": st.column_config.DateColumn("Last mention"),
                    "LAST_EVENT_BY": "Last event by", "LAST_LOSS_DROP_REASON": "Loss reason",
                    "LOSS_NOTES": "Loss notes",
                },
            )
            st.download_button(
                ":material/download: Download CSV", accounts.to_csv(index=False).encode(),
                file_name=f"signal_actions_{data.theme_phrase(theme).replace(' ', '_')}.csv",
                mime="text/csv",
            )

    elif section == "Context":
        scan = saved["scan"]
        in_scan = scan[scan["THEME"] == theme]
        portcos = metrics.portco_matrix(saved["portcos"])
        portcos = portcos[portcos["THEME"] == theme]
        left, right = st.columns([2, 3])
        with left:
            with st.container(border=True):
                st.markdown("**Portfolio companies driving the conversation**")
                if portcos.empty:
                    st.caption("No portfolio-company activity on this theme.")
                else:
                    st.dataframe(portcos[["PORTCO", "ACTIVITIES"]], hide_index=True, width="stretch",
                                 column_config={"PORTCO": "Portfolio company", "ACTIVITIES": "Activities"})
            with st.container(border=True):
                st.markdown("**Expert call coverage**")
                xt = saved["expert_themes"]
                st.dataframe(xt[xt["THEME"] == theme], hide_index=True, width="stretch",
                             column_config={"THEME": None, "SEARCH_PHRASE": "Phrase",
                                            "Q3_2025_DOCS": "Q3 '25", "Q3_2026_DOCS": "Q3 '26",
                                            "ACTIVE_PROJECT_OCT_2026": "Active project"})
        with right:
            with st.container(border=True):
                st.markdown("**Expert call examples**")
                xe = saved["expert_examples"]
                st.dataframe(xe[xe["THEME"] == theme], hide_index=True, width="stretch",
                             column_config={"THEME": None, "TITLE": "Title",
                                            "DATE": st.column_config.DateColumn("Date", format="MMM D, YYYY"),
                                            "URL": st.column_config.LinkColumn("Link", display_text="Open")})
            with st.container(border=True):
                st.markdown(f"**External scan companies** · {len(in_scan)}")
                if in_scan.empty:
                    st.caption("This theme was not part of the external scan.")
                else:
                    st.dataframe(
                        in_scan, hide_index=True, width="stretch",
                        column_config={
                            "THEME": None, "COMPANY": "Company", "DOMAIN": "Domain",
                            "STAGE": "Stage", "HEADCOUNT": "Headcount", "DESCRIPTION": "Description",
                            "SALESFORCE_STATUS": "Salesforce",
                            "SALESFORCE_OWNER_OR_MATCH": "Owner / match",
                            "SALESFORCE_LAST_ACTIVITY": st.column_config.DateColumn("Last activity"),
                        },
                    )


# Only the open tab runs, so the other tab's queries are skipped.
if topics_tab.open:
    with topics_tab:
        render_topics()
if research_tab.open:
    with research_tab:
        render_research()
