import os,sys
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import math
from setup_score import score_symbol, _risk, _pivots
from indicators_engine import compute_ema_series, compute_rsi_series, compute_session_vwap

def candles(n=270):
    out=[]; p=100.0
    for i in range(n):
        p += 0.05 + 0.4*math.sin(i/7)
        out.append({'open_time':i*3600000,'close_time':(i+1)*3600000-1,'open':p-0.2,'high':p+0.5,'low':p-0.5,'close':p,'volume':10_000_000})
    return out

def test_ema200_available_after_200():
    s=compute_ema_series(list(range(1,270)),200)
    assert s[198] is None and s[199] is not None

def test_rsi_series_aligned():
    s=compute_rsi_series(list(range(1,50)),14)
    assert len(s)==49 or len(s)==50
    assert s[-1]==100.0

def test_vwap_has_values():
    s=compute_session_vwap(candles(20)); assert all(x is not None for x in s)

def test_risk_validation():
    ok,reasons,r=_risk(100,95,5); assert ok and not reasons and r==5
    ok,reasons,_=_risk(100,90,1); assert not ok

def test_scanner_is_long_only():
    r=score_symbol('TESTUSDT',candles())
    assert r['direction'] in {'LONG','NONE'}
    assert not r['setup_type'].startswith('BEARISH')

def test_no_future_data_changes_previous_bar():
    cs=candles(); a=score_symbol('TESTUSDT',cs[:-5]); b=score_symbol('TESTUSDT',cs)
    # Different latest signal is expected, but the previous bar's indicator calculations
    # are deterministic from data available at that point.
    ea=compute_ema_series([c['close'] for c in cs[:-5]],200)[-1]
    eb=compute_ema_series([c['close'] for c in cs],200)[-6]
    assert ea == eb


def test_ema200_reclaim_requires_two_prior_closes():
    cs=[]
    for i in range(260):
        p=100.0
        if i==257:p=99.0
        if i==258:p=98.0
        if i==259:p=102.0
        cs.append({'open_time':i*3600000,'close_time':(i+1)*3600000-1,'open':p,'high':p+1,'low':p-1,'close':p,'volume':10000000})
    r=score_symbol('XUSDT',cs,10000000,'1h')
    assert r['setup_type']=='EMA200_RECLAIM' and r['qualified']

