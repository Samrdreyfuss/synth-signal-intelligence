"""Tests for signal_lib.companies pure helpers and query binding."""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "signal_dashboard"))

from signal_lib import companies as co  # noqa: E402


@pytest.mark.parametrize("rank,mentions,expected", [
    (1, 3, "Confirmed"), (4, 0, "Latent fit"), (5, 2, "Talking, off-profile"), (12, 0, "Unrelated"),
])
def test_relationship_rule(rank, mentions, expected):
    assert co.relationship(rank, mentions) == expected


def test_theme_companies_binds_values_and_filters_unknown_labels():
    calls = []

    def run(sql, params):
        calls.append((sql, params))
        return pd.DataFrame()

    co.theme_companies(run, "Voice AI'; DROP TABLE x;--", ["Confirmed", "bogus"])
    sql, params = calls[0]
    assert "DROP" not in sql and sql.count("?") == len(params)
    assert params[1] == "Voice AI'; DROP TABLE x;--" and params[2:] == ["Confirmed"]


def test_on_profile_share():
    themes = pd.DataFrame({"FIT_RANK": [1, 2, 7], "CRM_MENTIONS": [6, 2, 2]})
    assert co.on_profile_share(themes) == pytest.approx(0.8)
    assert co.on_profile_share(themes.assign(CRM_MENTIONS=0)) is None


def test_outreach_list_puts_unowned_stale_first():
    df = pd.DataFrame({
        "ACCOUNT_NAME": ["A", "B", "C"], "RELATIONSHIP": ["Latent fit", "Latent fit", "Confirmed"],
        "SIMILARITY": [0.5, 0.3, 0.9], "UNOWNED": [False, True, False], "STALE": [False, True, False],
    })
    out = co.outreach_list(df)
    assert out["ACCOUNT_NAME"].tolist() == ["B", "A"]


def test_relationship_counts_includes_all_labels():
    counts = co.relationship_counts(pd.DataFrame({"RELATIONSHIP": ["Confirmed", "Confirmed"]}))
    assert counts == {"Confirmed": 2, "Latent fit": 0, "Talking, off-profile": 0, "Unrelated": 0}
