"""One topic list: tracked themes (DERIVED) plus topics discovered from embeddings (EMERGING).

Every row shares one shape so the Topics tab can rank, filter and chart them together:
TOPIC_ID, TOPIC, KIND, STATUS, MOMENTUM, MOMENTUM_LABEL, COMPANIES, MENTIONS, SOURCES,
CONFIDENCE, DEFINITION, FIRST_SEEN, TREND, PARENT.
"""

from __future__ import annotations

import pandas as pd

from .data import DB, Runner, _upper

THEME = "Tracked theme"
DISCOVERED = "Discovered"
KINDS = [THEME, DISCOVERED]
HIDDEN_STATUSES = ["Noise", "Dismissed", "Merged", "Promoted"]
TREND_WEEKS = 16


def theme_id(theme: str) -> str:
    return f"THEME:{theme}"


def is_theme(topic_id: str | None) -> bool:
    return bool(topic_id) and topic_id.startswith("THEME:")


def theme_name(topic_id: str) -> str:
    return topic_id.split(":", 1)[1]


def theme_weekly(run: Runner) -> pd.DataFrame:
    """Weekly CRM mentions per theme (same week start as the cluster sparklines)."""
    return _upper(run(
        f"SELECT THEME, DATE_TRUNC('week', EVENT_DATE) AS WEEK, COUNT(*) AS RECORDS "
        f"FROM {DB}.DERIVED.THEME_MENTIONS GROUP BY 1, 2 ORDER BY 1, 2", None))


def theme_definitions(run: Runner) -> pd.DataFrame:
    return _upper(run(f"SELECT THEME, DEFINITION FROM {DB}.ANALYTICS.DIM_THEME_DEFINITIONS", None))


def _trend(weekly: pd.DataFrame, col: str, key: str, end: pd.Timestamp, weeks: int) -> list:
    idx = pd.date_range(end=end, periods=weeks, freq="W-MON")
    s = weekly[weekly[col] == key].groupby("WEEK")["RECORDS"].sum()
    return [int(x) for x in s.reindex(idx, fill_value=0)]


def build(lifted: pd.DataFrame, corr: pd.DataFrame, sig: pd.DataFrame,
          theme_wk: pd.DataFrame, cluster_wk: pd.DataFrame, baseline: str,
          weeks: int = TREND_WEEKS, definitions: pd.DataFrame | None = None) -> pd.DataFrame:
    """Merge tracked themes and discovered clusters into one ranked table."""
    frames = [w.assign(WEEK=pd.to_datetime(w["WEEK"]).dt.normalize())
              for w in (theme_wk, cluster_wk) if len(w)]
    end = max((f["WEEK"].max() for f in frames), default=pd.Timestamp.today().normalize())
    end = end - pd.Timedelta(days=end.weekday())
    twk = frames[0] if len(theme_wk) else pd.DataFrame(columns=["THEME", "WEEK", "RECORDS"])
    cwk = (cluster_wk.assign(WEEK=pd.to_datetime(cluster_wk["WEEK"]).dt.normalize())
           if len(cluster_wk) else pd.DataFrame(columns=["CLUSTER_ID", "WEEK", "RECORDS"]))

    defs = (dict(zip(definitions["THEME"], definitions["DEFINITION"]))
            if definitions is not None and len(definitions) else {})
    conf = corr.set_index("THEME") if len(corr) else pd.DataFrame()
    themes = lifted[lifted["THEME"] != baseline]
    rows = [{
        "TOPIC_ID": theme_id(t.THEME), "TOPIC": t.THEME, "KIND": THEME, "STATUS": t.SIGNAL,
        "MOMENTUM": float(t.LIFT), "MOMENTUM_LABEL": "lift vs baseline",
        "COMPANIES": int(t.CURRENT_ENTERPRISES or 0), "MENTIONS": int(t.CURRENT_MENTIONS or 0),
        "SOURCES": int(conf.loc[t.THEME, "SOURCE_FAMILIES"]) if t.THEME in conf.index else None,
        "CONFIDENCE": conf.loc[t.THEME, "CONFIDENCE"] if t.THEME in conf.index else None,
        "DEFINITION": defs.get(t.THEME), "FIRST_SEEN": None, "PARENT": None,
        "TREND": _trend(twk, "THEME", t.THEME, end, weeks),
    } for t in themes.itertuples(index=False)]
    rows += [{
        "TOPIC_ID": c.CLUSTER_ID, "TOPIC": c.TOPIC_NAME if pd.notna(c.TOPIC_NAME) else c.CLUSTER_ID,
        "KIND": DISCOVERED, "STATUS": c.STATUS,
        "MOMENTUM": float(c.VELOCITY or 0), "MOMENTUM_LABEL": "velocity, last 8 wks vs prior",
        "COMPANIES": int(c.ACCOUNTS or 0), "MENTIONS": int(c.RECORDS or 0),
        "SOURCES": int(c.SOURCES or 0), "CONFIDENCE": None,
        "DEFINITION": c.DEFINITION if pd.notna(c.DEFINITION) else None,
        "FIRST_SEEN": pd.to_datetime(c.EMERGED_ON) if pd.notna(c.EMERGED_ON) else None,
        "PARENT": c.RELATED_THEME if pd.notna(c.RELATED_THEME) else None,
        "TREND": _trend(cwk, "CLUSTER_ID", c.CLUSTER_ID, end, weeks),
    } for c in sig.itertuples(index=False)]
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    # Discovered topics first (newest signal), then by momentum.
    out["_k"] = out["KIND"].map({DISCOVERED: 0, THEME: 1})
    out["_h"] = out["STATUS"].isin(HIDDEN_STATUSES).astype(int)
    return (out.sort_values(["_h", "_k", "MOMENTUM"], ascending=[True, True, False])
               .drop(columns=["_k", "_h"]).reset_index(drop=True))


def visible(topics: pd.DataFrame, kinds=None, statuses=None, show_hidden: bool = False) -> pd.DataFrame:
    t = topics
    if not show_hidden:
        t = t[~t["STATUS"].isin(HIDDEN_STATUSES)]
    if kinds:
        t = t[t["KIND"].isin(kinds)]
    if statuses:
        t = t[t["STATUS"].isin(statuses)]
    return t.reset_index(drop=True)


def newest(topics: pd.DataFrame, n: int = 4) -> pd.DataFrame:
    d = topics[(topics["KIND"] == DISCOVERED) & topics["STATUS"].isin(["New topic", "Emerging sub-topic"])]
    return d.sort_values("FIRST_SEEN", ascending=False).head(n).reset_index(drop=True)


def summary(topics: pd.DataFrame) -> dict:
    d = topics[topics["KIND"] == DISCOVERED]
    t = topics[topics["KIND"] == THEME]
    return {
        "tracked": len(t), "outpacing": int((t["MOMENTUM"] >= 1).sum()),
        "discovered": int((~d["STATUS"].isin(HIDDEN_STATUSES)).sum()),
        "new": int((d["STATUS"] == "New topic").sum()),
        "sub": int((d["STATUS"] == "Emerging sub-topic").sum()),
    }


def label(topics: pd.DataFrame, topic_id: str) -> str:
    r = topics[topics["TOPIC_ID"] == topic_id]
    if r.empty:
        return topic_id
    r = r.iloc[0]
    return f"{r['TOPIC']}  ·  {'theme' if r['KIND'] == THEME else r['STATUS'].lower()}"


__all__ = ["build", "visible", "newest", "summary", "label", "theme_weekly", "theme_definitions", "theme_id",
           "is_theme", "theme_name", "KINDS", "THEME", "DISCOVERED", "HIDDEN_STATUSES"]
