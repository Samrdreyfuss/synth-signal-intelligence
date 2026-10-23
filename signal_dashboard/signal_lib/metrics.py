"""Pure-pandas metric logic. No database or Streamlit access, so it is unit-testable."""

from __future__ import annotations

import pandas as pd

BASELINE_THEME = "AI agents (baseline)"
MIN_QUARTER_ACTIVITIES = 200


def theme_lift(themes: pd.DataFrame) -> pd.DataFrame:
    """Add LIFT (theme ratio / its scan's baseline ratio), SCAN and SIGNAL labels.

    Raises ValueError if the baseline row is missing, matching the dashboard's
    overlap calculation which depends on it.
    """
    if BASELINE_THEME not in set(themes["THEME"]):
        raise ValueError(f"'{BASELINE_THEME}' row is required in enterprise_themes")
    out = themes.copy()
    out["IS_BASELINE"] = out["THEME"] == BASELINE_THEME
    out["LIFT"] = out["MONTHLY_RATE_RATIO"] / out["BASELINE_RATIO"]
    out["SCAN"] = out["SHARE_FROM_PORTCO_INTROS"].isna().map(
        {True: "Discovered", False: "Tracked"}
    )
    out["SIGNAL"] = pd.cut(
        out["LIFT"],
        bins=[-float("inf"), 0.8, 1.0, 1.25, float("inf")],
        labels=["Cooling", "Lagging baseline", "Matching baseline", "Outpacing baseline"],
        right=False,
    ).astype(str)
    out.loc[out["IS_BASELINE"], "SIGNAL"] = "Baseline"
    return out.sort_values("LIFT", ascending=False).reset_index(drop=True)


def quarterly_share(quarterly: pd.DataFrame, min_total: int = MIN_QUARTER_ACTIVITIES) -> pd.DataFrame:
    """Drop thin quarters (< min_total activities) and add SHARE = mentions / total."""
    out = quarterly[quarterly["TOTAL_ACTIVITIES"] >= min_total].copy()
    out["SHARE"] = out["MENTIONS"] / out["TOTAL_ACTIVITIES"]
    return out.sort_values(["THEME", "QUARTER"]).reset_index(drop=True)


def share_momentum(shares: pd.DataFrame, periods: int = 4) -> pd.DataFrame:
    """Per theme: latest SHARE, SHARE `periods` quarters earlier, and the change in points."""
    rows = []
    for theme, g in shares.sort_values("QUARTER").groupby("THEME"):
        if len(g) <= periods:
            continue
        latest, earlier = g.iloc[-1], g.iloc[-1 - periods]
        rows.append(
            {
                "THEME": theme,
                "LATEST_QUARTER": latest["QUARTER"],
                "LATEST_SHARE": latest["SHARE"],
                "EARLIER_SHARE": earlier["SHARE"],
                "CHANGE_PTS": (latest["SHARE"] - earlier["SHARE"]) * 100,
            }
        )
    return pd.DataFrame(rows).sort_values("CHANGE_PTS", ascending=False).reset_index(drop=True)


def headline_kpis(lifted: pd.DataFrame, health: pd.DataFrame) -> dict:
    """Numbers for the KPI strip."""
    themes = lifted[~lifted["IS_BASELINE"]]
    prior = int(themes["PRIOR_MENTIONS"].sum())
    current = int(themes["CURRENT_MENTIONS"].sum())
    accounts = int(health["ACCOUNTS"].sum())
    return {
        "themes_outpacing": int((themes["LIFT"] >= 1.0).sum()),
        "themes_total": int(len(themes)),
        "current_mentions": current,
        "prior_mentions": prior,
        "unowned": int(health["UNOWNED"].sum()),
        "stale": int(health["STALE"].sum()),
        "accounts": accounts,
    }


def monthly_share(monthly: pd.DataFrame) -> pd.DataFrame:
    out = monthly.copy()
    out["SHARE"] = out["MENTIONS"] / out["TOTAL"].where(out["TOTAL"] > 0)
    return out


def portco_matrix(portcos: pd.DataFrame) -> pd.DataFrame:
    """Long-form THEME x PORTCO activity grid for a heatmap."""
    return (
        portcos.groupby(["THEME", "PORTCO"], as_index=False)["ACTIVITIES"].sum()
        .sort_values("ACTIVITIES", ascending=False)
        .reset_index(drop=True)
    )


def scan_status_counts(scan: pd.DataFrame) -> pd.DataFrame:
    return (
        scan.groupby(["THEME", "SALESFORCE_STATUS"], as_index=False)
        .size()
        .rename(columns={"size": "COMPANIES"})
    )


def filter_accounts(accounts: pd.DataFrame, segments=None, only_actionable: bool = False) -> pd.DataFrame:
    """Filter theme accounts by segment and to unowned-or-stale when requested."""
    out = accounts
    if segments:
        out = out[out["SEGMENT"].isin(segments)]
    if only_actionable:
        out = out[out["UNOWNED"].astype(bool) | out["STALE"].astype(bool)]
    return out.reset_index(drop=True)
