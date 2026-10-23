"""Company profiles and company x theme relevance (Cortex embedding fit vs CRM mentions)."""

from __future__ import annotations

from typing import Optional, Sequence

import pandas as pd

from .data import AS_OF, Runner, _upper

ANALYTICS = "SYNTH_SIGNAL_DB.ANALYTICS"
EVIDENCE = "SYNTH_SIGNAL_DB.EVIDENCE"

RELATIONSHIPS = ["Confirmed", "Latent fit", "Talking, off-profile", "Unrelated"]
RELATIONSHIP_HELP = {
    "Confirmed": "Theme fits the company's profile and it is talking about it",
    "Latent fit": "Theme fits the profile but no CRM mentions yet: outreach opportunity",
    "Talking, off-profile": "Mentioned in CRM but not a strong fit for what the company does",
    "Unrelated": "Neither a profile fit nor mentioned",
}
TOP_FIT_RANK = 4  # a theme is a profile fit when it is in the company's top 4 by similarity


def relationship(fit_rank: int, crm_mentions: int, top: int = TOP_FIT_RANK) -> str:
    """Same rule as EVIDENCE.COMPANY_THEME_RELEVANCE.RELATIONSHIP."""
    fits = fit_rank <= top
    talks = crm_mentions > 0
    if fits and talks:
        return "Confirmed"
    if fits:
        return "Latent fit"
    if talks:
        return "Talking, off-profile"
    return "Unrelated"


# ------------------------------------------------------------------ queries

def theme_companies(run: Runner, theme: str,
                    relationships: Optional[Sequence[str]] = None) -> pd.DataFrame:
    """Every company's fit and activity for one theme, with CRM ownership flags."""
    rels = [r for r in (relationships or []) if r in RELATIONSHIPS]
    rel_clause = f"AND r.RELATIONSHIP IN ({', '.join('?' for _ in rels)})" if rels else ""
    sql = f"""
        SELECT r.ACCOUNT_NAME, r.INDUSTRY, r.RELATIONSHIP, r.SIMILARITY, r.PROFILE_FIT, r.FIT_RANK,
               r.STATED_PRIORITY, r.CRM_MENTIONS, r.CURRENT_MENTIONS, r.LAST_MENTION,
               r.OTHER_SOURCE_HITS,
               NULLIF(c.OWNER_NAME, '') AS OWNER_NAME,
               (c.OWNER_NAME IS NULL OR c.OWNER_NAME = '' OR c.OWNER_NAME ILIKE 'unassigned%') AS UNOWNED,
               (c.DATE_OF_LAST_ACTIVITY IS NULL
                OR c.DATE_OF_LAST_ACTIVITY < DATEADD(day, -90, ?::DATE)) AS STALE
        FROM {EVIDENCE}.COMPANY_THEME_RELEVANCE r
        JOIN {ANALYTICS}.DIM_SALESFORCE__COMPANIES c USING (ACCOUNT_ID)
        WHERE r.THEME = ? {rel_clause}
        ORDER BY r.SIMILARITY DESC, r.CRM_MENTIONS DESC
    """
    return _upper(run(sql, [AS_OF.isoformat(), theme, *rels]))


def relationship_summary(run: Runner) -> pd.DataFrame:
    """Count of companies per theme and relationship."""
    return _upper(run(
        f"SELECT THEME, RELATIONSHIP, COUNT(*) AS COMPANIES "
        f"FROM {EVIDENCE}.COMPANY_THEME_RELEVANCE GROUP BY 1, 2", None))


def company_card(run: Runner, account_name: str) -> dict:
    """Profile plus fit vs mentions for every theme, for one company."""
    profile = _upper(run(
        f"""
        SELECT p.ACCOUNT_NAME, p.INDUSTRY, p.SUB_INDUSTRY, p.EMPLOYEE_BAND, p.HQ_REGION,
               p.FOUNDED_YEAR, ARRAY_TO_STRING(p.STATED_PRIORITIES, ', ') AS STATED_PRIORITIES,
               p.DESCRIPTION,
               NULLIF(c.OWNER_NAME, '') AS OWNER_NAME, c.DATE_OF_LAST_ACTIVITY,
               IFF(c.ACCOUNT_TYPE ILIKE 'portfolio%', 'Portfolio', 'Prospect') AS SEGMENT
        FROM {ANALYTICS}.DIM_COMPANY_PROFILES p
        JOIN {ANALYTICS}.DIM_SALESFORCE__COMPANIES c USING (ACCOUNT_ID)
        WHERE p.ACCOUNT_NAME = ?
        LIMIT 1
        """, [account_name]))
    themes = _upper(run(
        f"""
        SELECT THEME, RELATIONSHIP, SIMILARITY, PROFILE_FIT, FIT_RANK, STATED_PRIORITY,
               CRM_MENTIONS, CURRENT_MENTIONS, LAST_MENTION, OTHER_SOURCE_HITS
        FROM {EVIDENCE}.COMPANY_THEME_RELEVANCE
        WHERE ACCOUNT_NAME = ?
        ORDER BY FIT_RANK
        """, [account_name]))
    return {"profile": profile, "themes": themes}


# ------------------------------------------------------------------ pure helpers

def relationship_counts(companies: pd.DataFrame) -> dict:
    counts = companies["RELATIONSHIP"].value_counts().to_dict() if len(companies) else {}
    return {r: int(counts.get(r, 0)) for r in RELATIONSHIPS}


def on_profile_share(card_themes: pd.DataFrame, top: int = TOP_FIT_RANK) -> Optional[float]:
    """Share of a company's CRM theme mentions that fall on its top-`top` profile themes."""
    total = card_themes["CRM_MENTIONS"].sum()
    if not total:
        return None
    return float(card_themes.loc[card_themes["FIT_RANK"] <= top, "CRM_MENTIONS"].sum() / total)


def outreach_list(companies: pd.DataFrame) -> pd.DataFrame:
    """Latent-fit companies, best fit first, unowned / untouched accounts surfaced first."""
    latent = companies[companies["RELATIONSHIP"] == "Latent fit"].copy()
    latent["_PRIORITY"] = latent["UNOWNED"].astype(int) + latent["STALE"].astype(int)
    return (latent.sort_values(["_PRIORITY", "SIMILARITY"], ascending=False)
            .drop(columns="_PRIORITY").reset_index(drop=True))
