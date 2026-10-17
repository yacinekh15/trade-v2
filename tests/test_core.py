import math
from strategy_engine import ema200_cross, rsi_divergence, vwap_rsi_15m_ema200, bb_pullback, kijun_ssl, kdrx_v1


def candles_from_closes(closes):
    out=[]
    for i,c in enumerate(closes):
        out.append({"open_time":i*60000,"close_time":i*60000+59999,"open":c,"high":c*1.01,"low":c*0.99,"close":c,"volume":1000})
    return out


def test_ema200_cross_has_no_signal_without_cross():
    closes=[100+0.01*i for i in range(260)]
    r=ema200_cross("TESTUSDT","1h",candles_from_closes(closes))
    assert r is not None and not r["signal"]


def test_ema200_cross_detects_last_closed_cross():
    closes=[100.0]*250 + [99.0, 101.0]
    r=ema200_cross("TESTUSDT","1h",candles_from_closes(closes))
    assert r is not None
    assert r["signal"] is True


def test_other_four_strategy_engines_return_structured_results():
    closes=[100 + 0.02*i + 2*math.sin(i/5) for i in range(300)]
    c=candles_from_closes(closes)
    assert rsi_divergence("TESTUSDT","1h",c) is not None
    assert bb_pullback("TESTUSDT","1h",c) is not None
    assert kijun_ssl("TESTUSDT","1h",c) is not None
    trend=candles_from_closes(closes)
    assert vwap_rsi_15m_ema200("TESTUSDT","5m",c,trend) is not None


def test_kdrx_context_is_descriptive_and_does_not_replace_signal_engine():
    closes = [100 + 0.02*i + 2*math.sin(i/5) for i in range(300)]
    r = ema200_cross("TESTUSDT", "1h", candles_from_closes(closes))
    assert r is not None
    assert "kdrx_context" in r
    kc = r["kdrx_context"]
    assert "matching_core_conditions" in kc
    assert "relative_volume_state" in kc
    assert "interpretation_note" in kc
    # The context is metadata only; the original signal/status contract remains present.
    assert isinstance(r["signal"], bool)
    assert r["status"] in {"SIGNAL", "WATCH"}


def test_kdrx_v1_returns_five_conditions_and_equal_weight_score():
    closes = [100 + 0.02*i + 2*math.sin(i/5) for i in range(300)]
    r = kdrx_v1("TESTUSDT", "1h", candles_from_closes(closes))
    assert r is not None
    assert r["setup_type"] == "KDRX_V1"
    assert len(r["conditions"]) == 5
    assert r["match_count"] == sum(c["state"] == "PASS" for c in r["conditions"])
    assert 0 <= r["score"] <= 100
    assert r["complete_evaluation"] is True
