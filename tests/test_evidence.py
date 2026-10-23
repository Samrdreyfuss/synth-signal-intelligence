"""Tests for signal_lib.evidence pure helpers and SQL parameter binding."""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "signal_dashboard"))

from signal_lib import evidence as ev  # noqa: E402


class Capture:
    def __init__(self):
        self.calls = []

    def __call__(self, sql, params):
        self.calls.append((sql, params))
        return pd.DataFrame({"N": [0]})


def test_where_binds_every_value_and_drops_unknown_sources():
    cap = Capture()
    ev.evidence(cap, theme="Voice AI", sources=["CRM note", "x'; DROP TABLE t;--"],
                entity="Harbor Health", search="50%_off")
    sql, params = cap.calls[0]
    assert "DROP" not in sql and "Voice AI" not in sql and "Harbor" not in sql
    assert sql.count("?") == len(params)
    assert params[:3] == ["Voice AI", "CRM note", "Harbor Health"]
    assert params[3] == "%50!%!_off%"


def test_evidence_limit_is_clamped():
    cap = Capture()
    ev.evidence(cap, limit=10_000_000)
    assert "LIMIT 2000" in cap.calls[0][0]


def test_attribution_shares_sum_to_one():
    attr = pd.DataFrame({"THEME": ["A", "A", "B"], "SOURCE": ["CRM note", "Expert call", "CRM note"],
                         "EVIDENCE_ITEMS": [3, 1, 5]})
    out = ev.attribution_shares(attr)
    assert out.groupby("THEME")["SHARE_OF_THEME"].sum().tolist() == pytest.approx([1.0, 1.0])
    assert out.loc[(out.THEME == "A") & (out.SOURCE == "CRM note"), "SHARE_OF_THEME"].item() == 0.75


def test_source_matrix_counts_independent_families():
    long = pd.DataFrame({
        "ENTITY_NAME": ["Acme", "Acme", "Acme", "Beta"],
        "ENTITY_TYPE": ["Enterprise"] * 4,
        "ACCOUNT_ID": ["1", "1", "1", "2"],
        "SOURCE": ["CRM note", "Portco intro", "Portco network", "CRM note"],
        "ITEMS": [4, 2, 1, 7],
        "LAST_SEEN": pd.to_datetime(["2026-09-01", "2026-10-01", None, "2026-08-01"]),
    })
    m = ev.source_matrix(long).set_index("ENTITY_NAME")
    # CRM note + Portco intro are one family (CRM); Portco network is a second.
    assert m.loc["Acme", "SOURCE_FAMILIES"] == 2
    assert m.loc["Beta", "SOURCE_FAMILIES"] == 1
    assert m.loc["Acme", "TOTAL"] == 7
    assert list(m.index)[0] == "Acme"


def test_source_matrix_handles_date_objects_with_nulls():
    import datetime as dt
    long = pd.DataFrame({"ENTITY_NAME": ["A", "A"], "ENTITY_TYPE": ["Enterprise"] * 2,
                         "SOURCE": ["CRM note", "Portco network"], "ITEMS": [1, 1],
                         "LAST_SEEN": [dt.date(2026, 9, 1), None]})
    m = ev.source_matrix(long)
    assert m.loc[0, "LAST_SEEN"] == pd.Timestamp("2026-09-01")


def test_source_matrix_empty():
    out = ev.source_matrix(pd.DataFrame(columns=["ENTITY_NAME", "ENTITY_TYPE", "SOURCE", "ITEMS",
                                                 "LAST_SEEN"]))
    assert out.empty and "SOURCE_FAMILIES" in out.columns


def test_intro_share_check():
    attr = pd.DataFrame({"THEME": ["A", "A"], "SOURCE": ["CRM note", "Portco intro"],
                         "EVIDENCE_ITEMS": [75, 25]})
    themes = pd.DataFrame({"THEME": ["A"], "SHARE_FROM_PORTCO_INTROS": [0.30]})
    out = ev.intro_share_check(attr, themes)
    assert out.loc[0, "CRM_INTRO_SHARE"] == pytest.approx(0.25)
    assert out.loc[0, "GAP_PTS"] == pytest.approx(-5.0)
