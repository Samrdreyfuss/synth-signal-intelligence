"""Query functions over SYNTH_SIGNAL_DB.

Every function takes ``run(sql, params)`` and returns a pandas DataFrame with
upper-case column names. User-chosen values are always passed as qmark (``?``)
bind parameters, never formatted into the SQL text.
"""

from __future__ import annotations

from datetime import date
from typing import Callable, Optional, Sequence

import pandas as pd

Runner = Callable[[str, Optional[Sequence]], pd.DataFrame]

DB = "SYNTH_SIGNAL_DB"
ANALYTICS = f"{DB}.ANALYTICS"
SAVED = f"{DB}.SIGNAL_SAVED_FILES"
# Theme, quarterly and FDE signals computed from FACT_CRM_EVENTS (sql/06_derived_signals.sql).
DERIVED = f"{DB}.DERIVED"

# Data in the synthetic copy runs to this date; 90-day staleness is measured from it.
AS_OF = date(2026, 10, 17)
EVENTS_FROM = date(2024, 7, 1)
BASELINE_THEME = "AI agents (baseline)"

# Account names the dashboard excludes (stealth, fund entities, placeholders, duplicates).
_ACCOUNT_EXCLUSIONS = f"""
    NOT REGEXP_LIKE(LOWER(c.ACCOUNT_NAME), '.*(stealth|insight partners|new co|newco).*')
    AND c.ACCOUNT_NAME NOT LIKE '%(%'
    AND c.ACCOUNT_NAME NOT LIKE '% / %'
"""


def theme_phrase(theme: str) -> str:
    """Lower-case phrase used to match a theme in CRM event descriptions."""
    return theme.replace(" (baseline)", "").strip().lower()


def _upper(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = [str(c).upper() for c in df.columns]
    return df


# ------------------------------------------------------------------ saved files

def enterprise_themes(run: Runner) -> pd.DataFrame:
    return _upper(run(f"SELECT * FROM {DERIVED}.ENTERPRISE_THEMES", None))


def enterprise_quarterly(run: Runner) -> pd.DataFrame:
    return _upper(run(f"SELECT * FROM {DERIVED}.ENTERPRISE_QUARTERLY ORDER BY THEME, QUARTER", None))


def enterprise_portcos(run: Runner) -> pd.DataFrame:
    return _upper(run(f"SELECT * FROM {SAVED}.ENTERPRISE_PORTCOS", None))


def expert_themes(run: Runner) -> pd.DataFrame:
    return _upper(run(f"SELECT * FROM {SAVED}.EXPERT_THEMES", None))


def expert_examples(run: Runner) -> pd.DataFrame:
    return _upper(run(f"SELECT * FROM {SAVED}.EXPERT_EXAMPLES ORDER BY DATE DESC", None))


def external_scan(run: Runner) -> pd.DataFrame:
    return _upper(run(f"SELECT * FROM {SAVED}.EXTERNAL_SCAN", None))


def fde_quarterly(run: Runner) -> pd.DataFrame:
    return _upper(run(f"SELECT * FROM {DERIVED}.FDE_OTHER_QUARTERLY ORDER BY QUARTER", None))


# ------------------------------------------------------------------ live CRM queries

def account_health(run: Runner) -> pd.DataFrame:
    """Portfolio/prospect, owned/unowned and stale counts across eligible accounts."""
    sql = f"""
        SELECT
          IFF(c.ACCOUNT_TYPE ILIKE 'portfolio%', 'Portfolio', 'Prospect') AS SEGMENT,
          COUNT(*) AS ACCOUNTS,
          COUNT_IF(c.OWNER_NAME IS NULL OR c.OWNER_NAME = '' OR c.OWNER_NAME ILIKE 'unassigned%') AS UNOWNED,
          COUNT_IF(c.DATE_OF_LAST_ACTIVITY IS NULL
                   OR c.DATE_OF_LAST_ACTIVITY < DATEADD(day, -90, ?::DATE)) AS STALE
        FROM {ANALYTICS}.DIM_SALESFORCE__COMPANIES c
        WHERE {_ACCOUNT_EXCLUSIONS}
        GROUP BY 1
    """
    return _upper(run(sql, [AS_OF.isoformat()]))


def monthly_mentions(run: Runner, theme: str) -> pd.DataFrame:
    """Monthly count of CRM events mentioning the theme, with all-event totals."""
    sql = f"""
        SELECT DATE_TRUNC('month', TO_DATE(PERFORMED_DATE)) AS MONTH,
               COUNT_IF(CONTAINS(LOWER(DESCRIPTION), ?)) AS MENTIONS,
               COUNT(*) AS TOTAL
        FROM {ANALYTICS}.FACT_CRM_EVENTS
        WHERE TO_DATE(PERFORMED_DATE) >= ?::DATE
        GROUP BY 1
        ORDER BY 1
    """
    return _upper(run(sql, [theme_phrase(theme), EVENTS_FROM.isoformat()]))


def theme_accounts(run: Runner, theme: str) -> pd.DataFrame:
    """Accounts whose CRM events mention the theme, with ownership and staleness flags."""
    sql = f"""
        WITH ev AS (
          SELECT ACCOUNT_ID, PERFORMED_BY_ID, PERFORMED_DATE
          FROM {ANALYTICS}.FACT_CRM_EVENTS
          WHERE TO_DATE(PERFORMED_DATE) >= ?::DATE
            AND CONTAINS(LOWER(DESCRIPTION), ?)
        ), agg AS (
          SELECT ACCOUNT_ID, COUNT(*) AS MENTIONS, MAX(PERFORMED_DATE) AS LAST_MENTION,
                 MAX_BY(PERFORMED_BY_ID, PERFORMED_DATE) AS LAST_BY
          FROM ev GROUP BY 1
        )
        SELECT c.ACCOUNT_NAME,
               c.WEBSITE_CLEANED AS WEBSITE,
               IFF(c.ACCOUNT_TYPE ILIKE 'portfolio%', 'Portfolio', 'Prospect') AS SEGMENT,
               NULLIF(c.OWNER_NAME, '') AS OWNER_NAME,
               (c.OWNER_NAME IS NULL OR c.OWNER_NAME = '' OR c.OWNER_NAME ILIKE 'unassigned%') AS UNOWNED,
               c.DATE_OF_LAST_ACTIVITY,
               (c.DATE_OF_LAST_ACTIVITY IS NULL
                OR c.DATE_OF_LAST_ACTIVITY < DATEADD(day, -90, ?::DATE)) AS STALE,
               a.MENTIONS,
               TO_DATE(a.LAST_MENTION) AS LAST_MENTION,
               u.USER_NAME AS LAST_EVENT_BY,
               c.LAST_LOSS_DROP_REASON,
               LEFT(c.LAST_LOSS_DROP_NOTES, 160) AS LOSS_NOTES
        FROM agg a
        JOIN {ANALYTICS}.DIM_SALESFORCE__COMPANIES c USING (ACCOUNT_ID)
        LEFT JOIN {ANALYTICS}.DIM_USERS u ON u.USER_ID = a.LAST_BY
        WHERE {_ACCOUNT_EXCLUSIONS}
        ORDER BY a.MENTIONS DESC, a.LAST_MENTION DESC
    """
    return _upper(run(sql, [EVENTS_FROM.isoformat(), theme_phrase(theme), AS_OF.isoformat()]))


def theme_excerpts(run: Runner, theme: str, limit: int = 25) -> pd.DataFrame:
    """Most recent CRM notes mentioning the theme, HTML and 'Description:' marker removed."""
    sql = f"""
        SELECT e.EVENT_ID,
               TO_DATE(e.PERFORMED_DATE) AS EVENT_DATE,
               UPPER(REPLACE(e.EVENT_TYPE, '_', ' ')) AS EVENT_TYPE,
               c.ACCOUNT_NAME,
               u.USER_NAME AS PERFORMED_BY,
               TRIM(REGEXP_REPLACE(REGEXP_REPLACE(e.DESCRIPTION, '<[^>]+>', ''),
                                   '^\\\\s*Description:\\\\s*', '')) AS EXCERPT
        FROM {ANALYTICS}.FACT_CRM_EVENTS e
        JOIN {ANALYTICS}.DIM_SALESFORCE__COMPANIES c USING (ACCOUNT_ID)
        LEFT JOIN {ANALYTICS}.DIM_USERS u ON u.USER_ID = e.PERFORMED_BY_ID
        WHERE CONTAINS(LOWER(e.DESCRIPTION), ?)
        ORDER BY e.PERFORMED_DATE DESC, e.EVENT_ID
        LIMIT {max(1, min(int(limit), 200))}
    """
    return _upper(run(sql, [theme_phrase(theme)]))
