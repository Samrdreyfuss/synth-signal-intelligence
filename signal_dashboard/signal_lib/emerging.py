"""Emerging topics: clusters discovered from record embeddings (SYNTH_SIGNAL_DB.EMERGING)."""

from __future__ import annotations

import pandas as pd

from .data import Runner, _upper

EMERGING = "SYNTH_SIGNAL_DB.EMERGING"

STATUSES = ["New topic", "Emerging sub-topic", "Watch", "Noise", "Promoted", "Merged", "Dismissed"]
STATUS_HELP = {
    "New topic": "A distinct topic no tracked theme covers, recent, growing and spread across companies",
    "Emerging sub-topic": "A specific new application inside a tracked theme",
    "Watch": "Below the new-topic thresholds (older, slowing or thinly spread)",
    "Noise": "Concentrated in one or very few companies",
    "Promoted": "Added to the tracked theme list",
    "Merged": "Folded into an existing theme by a reviewer",
    "Dismissed": "Marked as not relevant by a reviewer",
}
REVIEW_ACTIONS = ["Merged", "Dismissed", "Reopen"]


# ------------------------------------------------------------------ queries

def signals(run: Runner) -> pd.DataFrame:
    return _upper(run(f"SELECT * FROM {EMERGING}.CLUSTER_SIGNALS ORDER BY EMERGENCE_SCORE DESC", None))


def weekly(run: Runner, cluster_id: str) -> pd.DataFrame:
    sql = f"""
        SELECT DATE_TRUNC('week', RECORD_DATE) AS WEEK, SOURCE, COUNT(*) AS RECORDS
        FROM {EMERGING}.CLUSTER_MEMBERS WHERE CLUSTER_ID = ?
        GROUP BY 1, 2 ORDER BY 1
    """
    return _upper(run(sql, [cluster_id]))


def weekly_all(run: Runner) -> pd.DataFrame:
    """Weekly member counts for every cluster (for sparklines)."""
    return _upper(run(
        f"SELECT CLUSTER_ID, DATE_TRUNC('week', RECORD_DATE) AS WEEK, COUNT(*) AS RECORDS "
        f"FROM {EMERGING}.CLUSTER_MEMBERS GROUP BY 1, 2 ORDER BY 1, 2", None))


def members(run: Runner, cluster_id: str, limit: int = 30) -> pd.DataFrame:
    """Records closest to the cluster centre first."""
    sql = f"""
        SELECT m.RECORD_ID, m.SOURCE, m.ENTITY_NAME, m.INDUSTRY, m.RECORD_DATE, m.TEXT,
               ROUND(VECTOR_COSINE_SIMILARITY(m.EMBEDDING, c.CENTROID), 3) AS SIMILARITY
        FROM {EMERGING}.CLUSTER_MEMBERS m
        JOIN {EMERGING}.CLUSTERS c USING (CLUSTER_ID)
        WHERE m.CLUSTER_ID = ?
        ORDER BY SIMILARITY DESC, m.RECORD_ID
        LIMIT {max(1, min(int(limit), 200))}
    """
    return _upper(run(sql, [cluster_id]))


def companies(run: Runner, cluster_id: str) -> pd.DataFrame:
    sql = f"""
        SELECT m.ENTITY_NAME, m.INDUSTRY, COUNT(*) AS RECORDS, MAX(m.RECORD_DATE) AS LAST_SEEN,
               ARRAY_TO_STRING(ARRAY_AGG(DISTINCT m.SOURCE), ', ') AS SOURCES,
               NULLIF(c.OWNER_NAME, '') AS OWNER_NAME
        FROM {EMERGING}.CLUSTER_MEMBERS m
        LEFT JOIN SYNTH_SIGNAL_DB.ANALYTICS.DIM_SALESFORCE__COMPANIES c ON c.ACCOUNT_ID = m.ACCOUNT_ID
        WHERE m.CLUSTER_ID = ?
        GROUP BY 1, 2, c.OWNER_NAME
        ORDER BY RECORDS DESC, LAST_SEEN DESC
    """
    return _upper(run(sql, [cluster_id]))


def history(run: Runner) -> pd.DataFrame:
    return _upper(run(f"SELECT * FROM {EMERGING}.CLUSTER_SIGNAL_HISTORY ORDER BY SNAPSHOT_AT", None))


# ------------------------------------------------------------------ actions (bound parameters)

def promote(run: Runner, cluster_id: str, theme_name: str, phrase: str, definition: str) -> str:
    out = run(f"CALL {EMERGING}.PROMOTE_CLUSTER(?, ?, ?, ?)",
              [cluster_id, theme_name.strip(), phrase.strip(), definition.strip()])
    return str(out.iloc[0, 0]) if len(out) else ""


def review(run: Runner, cluster_id: str, action: str, theme: str | None = None,
           note: str | None = None) -> str:
    if action not in REVIEW_ACTIONS:
        raise ValueError(f"action must be one of {REVIEW_ACTIONS}")
    out = run(f"CALL {EMERGING}.REVIEW_CLUSTER(?, ?, ?, ?)", [cluster_id, action, theme, note])
    return str(out.iloc[0, 0]) if len(out) else ""


# ------------------------------------------------------------------ pure helpers

def suggested_phrase(topic_name: str | None, key_terms: str | None) -> str:
    """First key term (else the topic name), lower-cased, as the CRM phrase for a promoted theme."""
    first = (key_terms or "").split(",")[0].strip()
    return (first or (topic_name or "")).lower()


def status_counts(sig: pd.DataFrame) -> dict:
    counts = sig["STATUS"].value_counts().to_dict() if len(sig) else {}
    return {s: int(counts.get(s, 0)) for s in STATUSES}


def sparkline(weekly_all: pd.DataFrame, cluster_id: str, weeks: int = 16) -> list:
    """Zero-filled weekly counts for the last `weeks` weeks (weeks start Monday, as DATE_TRUNC does)."""
    if weekly_all.empty:
        return [0] * weeks
    w = weekly_all.assign(WEEK=pd.to_datetime(weekly_all["WEEK"]).dt.normalize())
    idx = pd.date_range(end=w["WEEK"].max(), periods=weeks, freq="W-MON")
    s = w[w["CLUSTER_ID"] == cluster_id].groupby("WEEK")["RECORDS"].sum()
    return [int(x) for x in s.reindex(idx, fill_value=0)]
