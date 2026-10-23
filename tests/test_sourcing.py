import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "signal_dashboard"))

from signal_lib import sourcing as so  # noqa: E402


def _targets():
    return pd.DataFrame({
        "COMPANY_ID": ["M1", "M2", "M3", "M4"],
        "BASIS": ["Fit + signal", "Fit only", "Signal only", "Fit + signal"],
        "STAGE": ["Seed", "Series A", "Seed", "Growth"],
        "SOURCING_SCORE": [0.9, 0.5, 0.4, None],
        "LAST_SIGNAL": ["2026-10-01", None, "2026-03-01", "2026-08-01"],
    })


def test_filter_targets():
    t = _targets()
    assert list(so.filter_targets(t, ["Fit + signal"])["COMPANY_ID"]) == ["M1", "M4"]
    assert list(so.filter_targets(t, stages=["Seed"])["COMPANY_ID"]) == ["M1", "M3"]
    assert list(so.filter_targets(t, min_score=0.45)["COMPANY_ID"]) == ["M1", "M2"]


def test_basis_and_recency():
    t = _targets()
    assert so.basis_counts(t) == {"Fit + signal": 2, "Signal only": 1, "Fit only": 1}
    assert so.recent_signal_count(t, "2026-10-17", 90) == 2
    assert so.basis_counts(t.iloc[0:0]) == {b: 0 for b in so.BASES}


def test_queries_bind_parameters():
    seen = []
    so.theme_targets(lambda sql, p: seen.append((sql, p)) or pd.DataFrame(), "Voice AI'; DROP")
    so.topic_targets(lambda sql, p: seen.append((sql, p)) or pd.DataFrame(), "C001", limit=10_000)
    assert seen[0][1] == ["Voice AI'; DROP"] and "DROP" not in seen[0][0]
    assert seen[1][1] == ["C001"] and "LIMIT 200" in seen[1][0]
