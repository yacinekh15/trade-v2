import math
from indicators_engine import ema_relationship, ema_crossed_up
from setup_score import score_symbol
from backtest import backtest_candles

def candles(n=180):
    out=[]; price=100.0
    for i in range(n):
        price += 0.2 + 0.8*math.sin(i/7)
        out.append({"open_time":i*3600000,"open":price-0.2,"high":price+1,"low":price-1,"close":price,"volume":1000+(500 if i%17==0 else 0)})
    return out

def test_ema_equal_band():
    state,gap=ema_relationship(100,100.03,0.05)
    assert state=="EQUAL" and gap<0.05

def test_score_shape():
    r=score_symbol("TESTUSDT",candles())
    assert r and 0<=r["score"]<=100 and "ema_equal" in r

def test_backtest_shape():
    r=backtest_candles("TESTUSDT",candles(),"1h",40,12)
    assert "summary" in r and r["summary"]["signals"]==len(r["trades"])
