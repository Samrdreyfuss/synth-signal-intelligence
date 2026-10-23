"""Sourcing: companies we have not spoken with (no CRM account), ranked per topic.

Tracked themes use EVIDENCE.SOURCING_TARGETS (Cortex fit + signals in other sources + recency).
Discovered topics have no theme definition, so companies are ranked by how close their
description embedding is to the cluster centre.
"""

from __future__ import annotations

import pandas as pd

from .data import DB, Runner, _upper

ANALYTICS = f"{DB}.ANALYTICS"
BASES = ["Fit + signal", "Signal only", "Fit only"]
BASIS_HELP = {
    "Fit + signal": "Profile fits the theme and the company has been seen on it in another source",
    "Signal only": "Seen on the theme in another source, though its profile ranks other themes higher",
    "Fit only": "Profile fits the theme; not yet seen in any source",
}
STAGES = ["Pre-seed", "Seed", "Series A", "Series B", "Series C", "Growth"]


def theme_targets(run: Runner, theme: str) -> pd.DataFrame:
    sql = f"""
        SELECT COMPANY_ID, COMPANY_NAME, DOMAIN, INDUSTRY, SUB_INDUSTRY, STAGE, HEADCOUNT, HQ_REGION,
               FOUNDED_YEAR, SOURCING_SCORE, BASIS, SIMILARITY, FIT_RANK, STATED_PRIORITY,
               THEME_SIGNALS, ALL_SIGNALS, LAST_SIGNAL, SIGNAL_SOURCES, PORTCOS, DESCRIPTION
        FROM {DB}.EVIDENCE.SOURCING_TARGETS
        WHERE THEME = ?
        ORDER BY SOURCING_SCORE DESC, SIMILARITY DESC
    """
    return _upper(run(sql, [theme]))


def topic_targets(run: Runner, cluster_id: str, limit: int = 40) -> pd.DataFrame:
    """Market companies closest to a discovered topic's centroid."""
    sql = f"""
        SELECT c.COMPANY_ID, c.COMPANY_NAME, c.DOMAIN, c.INDUSTRY, c.SUB_INDUSTRY, c.STAGE, c.HEADCOUNT,
               c.HQ_REGION, c.FOUNDED_YEAR,
               ROUND(VECTOR_COSINE_SIMILARITY(e.EMBEDDING, k.CENTROID), 4) AS SIMILARITY,
               COALESCE(s.ALL_SIGNALS, 0) AS ALL_SIGNALS, s.LAST_SIGNAL, c.DESCRIPTION
        FROM {ANALYTICS}.MARKET_EMBEDDINGS e
        JOIN {ANALYTICS}.DIM_MARKET_COMPANIES c USING (COMPANY_ID)
        JOIN {DB}.EMERGING.CLUSTERS k ON k.CLUSTER_ID = ?
        LEFT JOIN (SELECT COMPANY_ID, COUNT(*) AS ALL_SIGNALS, MAX(SIGNAL_DATE) AS LAST_SIGNAL
                   FROM {ANALYTICS}.MARKET_SIGNALS GROUP BY 1) s USING (COMPANY_ID)
        ORDER BY SIMILARITY DESC
        LIMIT {max(1, min(int(limit), 200))}
    """
    return _upper(run(sql, [cluster_id]))


def company_signals(run: Runner, company_id: str) -> pd.DataFrame:
    sql = f"""
        SELECT SIGNAL_DATE, SOURCE, THEME, PORTCO, SNIPPET
        FROM {ANALYTICS}.MARKET_SIGNALS WHERE COMPANY_ID = ?
        ORDER BY SIGNAL_DATE DESC
    """
    return _upper(run(sql, [company_id]))


def company_fit(run: Runner, company_id: str) -> pd.DataFrame:
    sql = f"""
        SELECT THEME, ROUND(SIMILARITY, 4) AS SIMILARITY, FIT_RANK
        FROM {ANALYTICS}.MARKET_THEME_FIT WHERE COMPANY_ID = ?
        ORDER BY FIT_RANK
    """
    return _upper(run(sql, [company_id]))


# ------------------------------------------------------------------ pure helpers

def filter_targets(targets: pd.DataFrame, bases=None, stages=None, min_score: float = 0.0) -> pd.DataFrame:
    t = targets
    if bases:
        t = t[t["BASIS"].isin(bases)]
    if stages:
        t = t[t["STAGE"].isin(stages)]
    t = t[pd.to_numeric(t["SOURCING_SCORE"], errors="coerce").fillna(0) >= min_score]
    return t.reset_index(drop=True)


def basis_counts(targets: pd.DataFrame) -> dict:
    counts = targets["BASIS"].value_counts().to_dict() if len(targets) else {}
    return {b: int(counts.get(b, 0)) for b in BASES}


def recent_signal_count(targets: pd.DataFrame, as_of, days: int = 90) -> int:
    if targets.empty:
        return 0
    last = pd.to_datetime(targets["LAST_SIGNAL"], errors="coerce")
    return int((last >= pd.Timestamp(as_of) - pd.Timedelta(days=days)).sum())
