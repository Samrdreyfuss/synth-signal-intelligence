import pandas as pd

from signal_lib import topics as tp

BASE = "AI agents"


def _lifted():
    return pd.DataFrame({
        "THEME": [BASE, "Voice AI", "Document processing"],
        "SIGNAL": ["Baseline", "Outpacing baseline", "Lagging baseline"],
        "LIFT": [1.0, 1.5, 0.7],
        "CURRENT_ENTERPRISES": [50, 30, 20], "CURRENT_MENTIONS": [90, 40, 25],
    })


def _sig():
    return pd.DataFrame({
        "CLUSTER_ID": ["C001", "C002", "C005"], "TOPIC_NAME": ["MCP", None, "Plants"],
        "STATUS": ["New topic", "Emerging sub-topic", "Noise"], "VELOCITY": [3.0, 2.0, 1.0],
        "ACCOUNTS": [12, 8, 1], "RECORDS": [40, 20, 10], "SOURCES": [2, 1, 1],
        "DEFINITION": ["Model context protocol", None, None],
        "EMERGED_ON": ["2026-08-01", "2026-07-01", "2026-06-01"],
        "RELATED_THEME": [None, "Voice AI", None],
    })


def _weekly():
    t = pd.DataFrame({"THEME": ["Voice AI"] * 2, "WEEK": ["2026-10-05", "2026-10-12"], "RECORDS": [3, 5]})
    c = pd.DataFrame({"CLUSTER_ID": ["C001"], "WEEK": ["2026-10-12"], "RECORDS": [7]})
    return t, c


def _build():
    t, c = _weekly()
    corr = pd.DataFrame({"THEME": ["Voice AI"], "SOURCE_FAMILIES": [3], "CONFIDENCE": ["High"]})
    defs = pd.DataFrame({"THEME": ["Voice AI"], "DEFINITION": ["Speech agents"]})
    return tp.build(_lifted(), corr, _sig(), t, c, BASE, weeks=4, definitions=defs)


def test_build_merges_and_excludes_baseline():
    out = _build()
    assert set(out["TOPIC_ID"]) == {"THEME:Voice AI", "THEME:Document processing", "C001", "C002", "C005"}
    assert out.iloc[0]["TOPIC_ID"] == "C001"            # discovered, highest velocity first
    assert out.iloc[-1]["TOPIC_ID"] == "C005"           # hidden statuses sink to the bottom
    v = out.set_index("TOPIC_ID").loc["THEME:Voice AI"]
    assert v["CONFIDENCE"] == "High" and v["DEFINITION"] == "Speech agents"
    assert out.set_index("TOPIC_ID").loc["C002", "TOPIC"] == "C002"  # unnamed falls back to id


def test_trends_are_aligned_and_zero_filled():
    out = _build().set_index("TOPIC_ID")
    assert out.loc["THEME:Voice AI", "TREND"] == [0, 0, 3, 5]
    assert out.loc["C001", "TREND"] == [0, 0, 0, 7]
    assert out.loc["THEME:Document processing", "TREND"] == [0, 0, 0, 0]


def test_visible_summary_newest():
    out = _build()
    assert "C005" not in set(tp.visible(out)["TOPIC_ID"])
    assert "C005" in set(tp.visible(out, show_hidden=True)["TOPIC_ID"])
    assert set(tp.visible(out, kinds=[tp.THEME])["KIND"]) == {tp.THEME}
    assert tp.summary(out) == {"tracked": 2, "outpacing": 1, "discovered": 2, "new": 1, "sub": 1}
    assert list(tp.newest(out)["TOPIC_ID"]) == ["C001", "C002"]


def test_ids():
    assert tp.is_theme(tp.theme_id("Voice AI")) and not tp.is_theme("C001")
    assert tp.theme_name("THEME:Voice AI") == "Voice AI"
