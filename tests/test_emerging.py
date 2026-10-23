"""Tests for signal_lib.emerging helpers and action binding."""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "signal_dashboard"))

from signal_lib import emerging as em  # noqa: E402


class Capture:
    def __init__(self):
        self.calls = []

    def __call__(self, sql, params):
        self.calls.append((sql, params))
        return pd.DataFrame({"R": ["ok"]})


def test_promote_binds_all_values():
    cap = Capture()
    em.promote(cap, "C001", "MCP'; DROP TABLE x;--", " model context protocol ", "def")
    sql, params = cap.calls[0]
    assert "DROP" not in sql and sql.count("?") == 4
    assert params == ["C001", "MCP'; DROP TABLE x;--", "model context protocol", "def"]


def test_review_rejects_unknown_action():
    with pytest.raises(ValueError):
        em.review(Capture(), "C001", "Delete")


def test_members_limit_clamped():
    cap = Capture()
    em.members(cap, "C001", limit=10_000)
    assert "LIMIT 200" in cap.calls[0][0]


def test_suggested_phrase():
    assert em.suggested_phrase("EU Data Residency", "data residency, GDPR") == "data residency"
    assert em.suggested_phrase("EU Data Residency", None) == "eu data residency"


def test_status_counts_has_every_status():
    out = em.status_counts(pd.DataFrame({"STATUS": ["New topic", "New topic", "Noise"]}))
    assert out["New topic"] == 2 and out["Noise"] == 1 and out["Watch"] == 0
    assert set(out) == set(em.STATUSES)


def test_sparkline_zero_fills_missing_weeks():
    wk = pd.DataFrame({"CLUSTER_ID": ["C1", "C1", "C2"],
                       "WEEK": pd.to_datetime(["2026-09-28", "2026-10-12", "2026-10-12"]),
                       "RECORDS": [3, 5, 9]})
    assert em.sparkline(wk, "C1", weeks=4) == [0, 3, 0, 5]
    assert em.sparkline(wk, "C3", weeks=2) == [0, 0]
