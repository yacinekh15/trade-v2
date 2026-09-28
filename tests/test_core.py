import math
from setup_score import score_symbol, _five_candle_confirmation
from indicators_engine import compute_ema_series, compute_rsi_series


def base_candles(n=260):
    out=[]
    price=100.0
    for i in range(n):
        price += 0.15 + 0.5*math.sin(i/8)
        out.append({"open_time":i*3600000,"open":price-0.1,"high":price+0.5,"low":price-0.5,"close":price,"volume":1000})
    return out


def test_five_candle_confirmation():
    cs=[{"open":i,"close":i+0.1,"high":i+0.2,"low":i-0.2} for i in range(5)]
    assert _five_candle_confirmation(cs) is True


def test_scanner_shape_is_long_only():
    r=score_symbol("TESTUSDT",base_candles())
    assert r
    assert r["direction"] in {"LONG","NONE"}
    assert "SHORT" not in r["setup_type"]


def test_no_ema20_50_logic_required():
    r=score_symbol("TESTUSDT",base_candles())
    assert "ema200" in r["indicators"]
    assert "macd" not in r["indicators"]


def test_rsi_series_aligned():
    closes=list(range(1,40))
    s=compute_rsi_series(closes,14)
    assert len(s)==len(closes)
    assert s[-1] == 100.0
