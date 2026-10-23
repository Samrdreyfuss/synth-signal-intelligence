"""Unit tests for signal_lib.metrics. Run from the repo root: python -m pytest tests"""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "signal_dashboard"))

from signal_lib import metrics  # noqa: E402
from signal_lib.data import theme_phrase  # noqa: E402


def _themes():
    return pd.DataFrame(
        {
            "THEME": ["AI agents (baseline)", "Voice AI", "Vector databases", "Agent identity"],
            "PRIOR_MENTIONS": [420, 40, 130, 20],
            "CURRENT_MENTIONS": [610, 110, 110, 75],
            "MONTHLY_RATE_RATIO": [2.66, 5.04, 1.55, 6.87],
            "CURRENT_ENTERPRISES": [180, 38, 52, 26],
            "SHARE_FROM_PORTCO_INTROS": [0.22, 0.33, 0.09, None],
            "EXAMPLE_ENTERPRISES": ["a", "b", "c", "d"],
            "BASELINE_RATIO": [2.66, 2.66, 2.66, 2.95],
        }
    )


def test_theme_lift_uses_own_scan_baseline():
    out = metrics.theme_lift(_themes()).set_index("THEME")
    assert out.loc["AI agents (baseline)", "LIFT"] == pytest.approx(1.0)
    assert out.loc["Agent identity", "LIFT"] == pytest.approx(6.87 / 2.95)
    assert out.loc["Agent identity", "SCAN"] == "Discovered"
    assert out.loc["Voice AI", "SCAN"] == "Tracked"


def test_theme_lift_signal_labels():
    out = metrics.theme_lift(_themes()).set_index("THEME")
    assert out.loc["AI agents (baseline)", "SIGNAL"] == "Baseline"
    assert out.loc["Voice AI", "SIGNAL"] == "Outpacing baseline"
    assert out.loc["Vector databases", "SIGNAL"] == "Cooling"


def test_theme_lift_requires_baseline():
    df = _themes()
    with pytest.raises(ValueError):
        metrics.theme_lift(df[df["THEME"] != "AI agents (baseline)"])


def test_quarterly_share_drops_thin_quarters():
    q = pd.DataFrame(
        {
            "THEME": ["X"] * 3,
            "QUARTER": ["2026-Q2", "2026-Q3", "2026-Q4"],
            "MENTIONS": [20, 30, 5],
            "TOTAL_ACTIVITIES": [1000, 1500, 160],
        }
    )
    out = metrics.quarterly_share(q)
    assert list(out["QUARTER"]) == ["2026-Q2", "2026-Q3"]
    assert out["SHARE"].tolist() == pytest.approx([0.02, 0.02])


def test_share_momentum_change_in_points():
    shares = pd.DataFrame(
        {
            "THEME": ["X"] * 5,
            "QUARTER": [f"2025-Q{i}" for i in range(1, 5)] + ["2026-Q1"],
            "SHARE": [0.01, 0.01, 0.01, 0.01, 0.03],
        }
    )
    out = metrics.share_momentum(shares, periods=4)
    assert out.loc[0, "CHANGE_PTS"] == pytest.approx(2.0)


def test_headline_kpis_excludes_baseline():
    lifted = metrics.theme_lift(_themes())
    health = pd.DataFrame({"SEGMENT": ["Portfolio", "Prospect"], "ACCOUNTS": [10, 90],
                           "UNOWNED": [1, 20], "STALE": [3, 40]})
    k = metrics.headline_kpis(lifted, health)
    assert k["themes_total"] == 3
    assert k["current_mentions"] == 110 + 110 + 75
    assert k["unowned"] == 21 and k["stale"] == 43 and k["accounts"] == 100


def test_filter_accounts_actionable():
    acc = pd.DataFrame({"SEGMENT": ["Portfolio", "Prospect", "Prospect"],
                        "UNOWNED": [False, True, False], "STALE": [False, False, True]})
    assert len(metrics.filter_accounts(acc, only_actionable=True)) == 2
    assert len(metrics.filter_accounts(acc, segments=["Portfolio"])) == 1


def test_theme_phrase():
    assert theme_phrase("AI agents (baseline)") == "ai agents"
    assert theme_phrase("Voice AI") == "voice ai"
