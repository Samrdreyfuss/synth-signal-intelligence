import os
from datetime import timedelta

import pandas as pd
import streamlit as st

from signal_lib import charts, data, metrics

st.set_page_config(
    page_title="Signal Intelligence",
    page_icon=":material/radar:",
    layout="wide",
)

CACHE_TTL = timedelta(minutes=15)

conn = st.connection("snowflake", ttl=os.getenv("SNOWFLAKE_CONNECTION_TTL"))


def run(sql, params=None):
    return conn.query(sql, params=params, ttl=CACHE_TTL)


# ------------------------------------------------------------------ cached loaders

@st.cache_data(ttl=CACHE_TTL)
def load_saved():
    return {
        "themes": data.enterprise_themes(run),
        "quarterly": data.enterprise_quarterly(run),
        "portcos": data.enterprise_portcos(run),
        "expert_themes": data.expert_themes(run),
        "expert_examples": data.expert_examples(run),
        "scan": data.external_scan(run),
        "fde": data.fde_quarterly(run),
    }


@st.cache_data(ttl=CACHE_TTL)
def load_health():
    return data.account_health(run)


@st.cache_data(ttl=CACHE_TTL, max_entries=64)
def load_theme_live(theme):
    return {
        "monthly": metrics.monthly_share(data.monthly_mentions(run, theme)),
        "accounts": data.theme_accounts(run, theme),
        "excerpts": data.theme_excerpts(run, theme, limit=25),
    }


def clear_caches():
    load_saved.clear()
    load_health.clear()
    load_theme_live.clear()


# ------------------------------------------------------------------ header (static first)

st.markdown("## :material/radar: Signal Intelligence")
st.caption(
    f"Enterprise theme signals from CRM activity, portfolio introductions, expert calls and an "
    f"external scan · current window **Apr 1 – {data.AS_OF:%b %d, %Y}** vs prior 12 months · "
    f"synthetic data from `{data.DB}`"
)

with st.spinner("Loading signals…"):
    saved = load_saved()
    health = load_health()

lifted = metrics.theme_lift(saved["themes"])
theme_names = [t for t in lifted["THEME"] if t != metrics.BASELINE_THEME]

# ------------------------------------------------------------------ sidebar filters

with st.sidebar:
    st.markdown("### :material/tune: Filters")
    theme = st.selectbox("Focus theme", theme_names, index=0,
                         help="Drives the trend highlight, live excerpts and action list.")
    segments = st.pills("Account segment", ["Portfolio", "Prospect"],
                        selection_mode="multi", default=["Portfolio", "Prospect"])
    only_actionable = st.toggle("Only unowned or 90+ days untouched", value=True)
    st.divider()
    st.button(":material/refresh: Refresh data", on_click=clear_caches, width="stretch")
    st.caption(f"Signals measured against **{metrics.BASELINE_THEME}**. "
               "Lift = theme rate ratio ÷ baseline rate ratio from the same scan.")

with st.spinner(f"Loading live CRM activity for {theme}…"):
    live = load_theme_live(theme)

# ------------------------------------------------------------------ KPI strip

k = metrics.headline_kpis(lifted, health)
sel = lifted.set_index("THEME").loc[theme]
monthly = live["monthly"]
spark = monthly["SHARE"].fillna(0).tail(12).round(4).tolist()
growth = (k["current_mentions"] / 6.55) / (k["prior_mentions"] / 12) - 1 if k["prior_mentions"] else 0

with st.container(horizontal=True):
    st.metric("Themes outpacing baseline", f"{k['themes_outpacing']} / {k['themes_total']}",
              border=True)
    st.metric("Current-window mentions", f"{k['current_mentions']:,}",
              f"{growth:+.0%} monthly rate vs prior", border=True)
    st.metric(f"{theme} · lift", f"{sel['LIFT']:.2f}×", sel["SIGNAL"],
              delta_color="normal" if sel["LIFT"] >= 1 else "inverse",
              border=True, chart_data=spark, chart_type="area")
    st.metric("Unowned accounts", f"{k['unowned']:,}",
              f"{k['unowned'] / k['accounts']:.0%} of {k['accounts']:,}",
              delta_color="off", border=True)
    st.metric("No touch in 90+ days", f"{k['stale']:,}",
              f"{k['stale'] / k['accounts']:.0%} of accounts", delta_color="off", border=True)

# ------------------------------------------------------------------ tabs

radar_tab, trends_tab, network_tab, action_tab, excerpt_tab = st.tabs([
    ":material/radar: Theme radar",
    ":material/trending_up: Trends",
    ":material/hub: Network",
    ":material/task_alt: Action list",
    ":material/format_quote: Live excerpts",
])

with radar_tab:
    left, right = st.columns([3, 2])
    with left:
        with st.container(border=True):
            st.markdown("**Theme radar** · bubble size = current mentions")
            st.altair_chart(charts.theme_radar(lifted, theme), width="stretch")
    with right:
        with st.container(border=True):
            st.markdown("**Lift vs baseline**")
            st.altair_chart(charts.lift_bars(lifted), width="stretch")
    with st.container(border=True):
        st.markdown("**All themes**")
        st.dataframe(
            lifted[["THEME", "SIGNAL", "LIFT", "MONTHLY_RATE_RATIO", "PRIOR_MENTIONS",
                    "CURRENT_MENTIONS", "CURRENT_ENTERPRISES", "SHARE_FROM_PORTCO_INTROS",
                    "SCAN", "EXAMPLE_ENTERPRISES"]],
            hide_index=True, width="stretch",
            column_config={
                "THEME": "Theme", "SIGNAL": "Signal", "SCAN": "Scan",
                "LIFT": st.column_config.ProgressColumn("Lift", format="%.2f×", min_value=0,
                                                        max_value=float(lifted["LIFT"].max())),
                "MONTHLY_RATE_RATIO": st.column_config.NumberColumn("Rate ratio", format="%.2f"),
                "PRIOR_MENTIONS": "Prior", "CURRENT_MENTIONS": "Current",
                "CURRENT_ENTERPRISES": "Enterprises",
                "SHARE_FROM_PORTCO_INTROS": st.column_config.NumberColumn("Via portco intros",
                                                                          format="percent"),
                "EXAMPLE_ENTERPRISES": "Examples",
            },
        )

with trends_tab:
    shares = metrics.quarterly_share(saved["quarterly"])
    momentum = metrics.share_momentum(shares)
    left, right = st.columns([3, 2])
    with left:
        with st.container(border=True):
            st.markdown(f"**Quarterly share of enterprise activity** · {theme} highlighted "
                        f"(quarters under {metrics.MIN_QUARTER_ACTIVITIES} activities dropped)")
            st.altair_chart(charts.share_lines(shares, [theme]), width="stretch")
    with right:
        with st.container(border=True):
            st.markdown("**Year-over-year momentum**")
            st.dataframe(
                momentum, hide_index=True, width="stretch", height=380,
                column_config={
                    "THEME": "Theme", "LATEST_QUARTER": "Quarter",
                    "LATEST_SHARE": st.column_config.NumberColumn("Share", format="percent"),
                    "EARLIER_SHARE": st.column_config.NumberColumn("4 qtrs ago", format="percent"),
                    "CHANGE_PTS": st.column_config.NumberColumn("Δ pts", format="%+.2f"),
                },
            )
    left, right = st.columns(2)
    with left:
        with st.container(border=True):
            st.markdown(f"**{theme} · monthly share of live CRM events**")
            st.altair_chart(charts.monthly_area(monthly), width="stretch")
    with right:
        with st.container(border=True):
            st.markdown("**Forward deployed engineering** · enterprise activities vs expert docs")
            st.altair_chart(charts.fde_chart(saved["fde"]), width="stretch")

with network_tab:
    with st.container(border=True):
        st.markdown("**Portfolio companies driving theme conversations**")
        st.altair_chart(charts.portco_heatmap(metrics.portco_matrix(saved["portcos"])),
                        width="stretch")
    left, right = st.columns([2, 3])
    with left:
        with st.container(border=True):
            st.markdown("**Expert call coverage** · Q3 2025 → Q3 2026")
            st.dataframe(
                saved["expert_themes"], hide_index=True, width="stretch",
                column_config={
                    "THEME": "Theme", "SEARCH_PHRASE": "Phrase",
                    "Q3_2025_DOCS": "Q3 '25", "Q3_2026_DOCS": "Q3 '26",
                    "ACTIVE_PROJECT_OCT_2026": "Active project",
                },
            )
    with right:
        with st.container(border=True):
            st.markdown("**Expert call examples**")
            st.dataframe(
                saved["expert_examples"], hide_index=True, width="stretch",
                column_config={
                    "THEME": "Theme", "TITLE": "Title",
                    "DATE": st.column_config.DateColumn("Date", format="MMM D, YYYY"),
                    "URL": st.column_config.LinkColumn("Link", display_text="Open"),
                },
            )

with action_tab:
    accounts = metrics.filter_accounts(live["accounts"], segments, only_actionable)
    with st.container(horizontal=True):
        st.metric(f"Accounts mentioning {theme}", f"{len(live['accounts']):,}", border=True)
        st.metric("Shown with current filters", f"{len(accounts):,}", border=True)
        st.metric("Unowned", f"{int(accounts['UNOWNED'].sum()):,}", border=True)
        st.metric("90+ days untouched", f"{int(accounts['STALE'].sum()):,}", border=True)
    with st.container(border=True):
        st.markdown(f"**CRM accounts to action for {theme}**")
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
    scan = saved["scan"]
    left, right = st.columns([2, 3])
    with left:
        with st.container(border=True):
            st.markdown("**External scan · Salesforce coverage**")
            st.altair_chart(charts.scan_status_bars(metrics.scan_status_counts(scan)),
                            width="stretch")
    with right:
        with st.container(border=True):
            in_scan = scan[scan["THEME"] == theme]
            st.markdown(f"**External companies for {theme}**" if len(in_scan)
                        else "**External scan companies** · focus theme not scanned, showing all")
            st.dataframe(
                in_scan if len(in_scan) else scan, hide_index=True, width="stretch",
                column_config={
                    "THEME": "Theme", "COMPANY": "Company", "DOMAIN": "Domain",
                    "STAGE": "Stage", "HEADCOUNT": "Headcount", "DESCRIPTION": "Description",
                    "SALESFORCE_STATUS": "Salesforce",
                    "SALESFORCE_OWNER_OR_MATCH": "Owner / match",
                    "SALESFORCE_LAST_ACTIVITY": st.column_config.DateColumn("Last activity"),
                },
            )

with excerpt_tab:
    ex = live["excerpts"]
    st.caption(f"{len(ex)} most recent CRM notes mentioning **{data.theme_phrase(theme)}**")
    for row in ex.itertuples(index=False):
        with st.container(border=True):
            st.markdown(
                f":blue-badge[{row.EVENT_TYPE}] **{row.ACCOUNT_NAME}** · "
                f"{pd.to_datetime(row.EVENT_DATE):%b %d, %Y} · {row.PERFORMED_BY or 'Unknown'}"
            )
            st.text(row.EXCERPT)
