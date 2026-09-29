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



def _instant_result(symbol='TESTUSDT', setup='EMA200_RECLAIM', score=20, qualified=False, signal_time=123):
    return {
        'symbol': symbol, 'timeframe': '1h', 'setup_type': setup, 'score': score,
        'qualified': qualified, 'signal_time': signal_time, 'price': 100,
        'rejection_reasons': ['risk too high'] if not qualified else [],
        'indicators': {}, 'analysis': {'sl': 95},
    }


def test_instant_alert_bypasses_score(monkeypatch):
    import telegram_alerts as ta
    sent=[]
    monkeypatch.setattr(ta, 'TELEGRAM_BOT_TOKEN', 'token')
    monkeypatch.setattr(ta, 'TELEGRAM_CHAT_ID', 'chat')
    monkeypatch.setattr(ta, 'get_json', lambda key, default=None: {})
    monkeypatch.setattr(ta, 'set_json', lambda key, obj: None)
    monkeypatch.setattr(ta, 'send_message', lambda text: sent.append(text) or True)
    out=ta.check_instant_reclaim_alerts([_instant_result(score=10, qualified=False)], '1h', True)
    assert out['sent']==1 and out['candidates']==1 and 'UNFILTERED' in sent[0]


def test_instant_alert_ignores_other_setup(monkeypatch):
    import telegram_alerts as ta
    sent=[]
    monkeypatch.setattr(ta, 'TELEGRAM_BOT_TOKEN', 'token')
    monkeypatch.setattr(ta, 'TELEGRAM_CHAT_ID', 'chat')
    monkeypatch.setattr(ta, 'get_json', lambda key, default=None: {})
    monkeypatch.setattr(ta, 'set_json', lambda key, obj: None)
    monkeypatch.setattr(ta, 'send_message', lambda text: sent.append(text) or True)
    out=ta.check_instant_reclaim_alerts([_instant_result(setup='BULLISH_BREAKOUT', score=99, qualified=True)], '1h', True)
    assert out['sent']==0 and out['candidates']==0 and not sent


def test_instant_alert_deduplicates(monkeypatch):
    import telegram_alerts as ta
    sent=[]; state={}
    monkeypatch.setattr(ta, 'TELEGRAM_BOT_TOKEN', 'token')
    monkeypatch.setattr(ta, 'TELEGRAM_CHAT_ID', 'chat')
    monkeypatch.setattr(ta, 'get_json', lambda key, default=None: state.copy())
    monkeypatch.setattr(ta, 'set_json', lambda key, obj: state.update(obj))
    monkeypatch.setattr(ta, 'send_message', lambda text: sent.append(text) or True)
    r=_instant_result()
    assert ta.check_instant_reclaim_alerts([r], '1h', True)['sent']==1
    assert ta.check_instant_reclaim_alerts([r], '1h', True)['sent']==0
    assert len(sent)==1


def test_instant_alert_off_sends_nothing(monkeypatch):
    import telegram_alerts as ta
    sent=[]
    monkeypatch.setattr(ta, 'TELEGRAM_BOT_TOKEN', 'token')
    monkeypatch.setattr(ta, 'TELEGRAM_CHAT_ID', 'chat')
    monkeypatch.setattr(ta, 'send_message', lambda text: sent.append(text) or True)
    out=ta.check_instant_reclaim_alerts([_instant_result()], '1h', False)
    assert out['sent']==0 and not sent


def test_instant_dedup_namespace_is_separate(monkeypatch):
    import telegram_alerts as ta
    calls=[]
    monkeypatch.setattr(ta, 'TELEGRAM_BOT_TOKEN', 'token')
    monkeypatch.setattr(ta, 'TELEGRAM_CHAT_ID', 'chat')
    monkeypatch.setattr(ta, 'get_json', lambda key, default=None: calls.append(('get', key)) or {})
    monkeypatch.setattr(ta, 'set_json', lambda key, obj: calls.append(('set', key)))
    monkeypatch.setattr(ta, 'send_message', lambda text: True)
    ta.check_instant_reclaim_alerts([_instant_result()], '1h', True)
    assert ('get', ta.INSTANT_KEY) in calls and ta.INSTANT_KEY != ta.KEY

def _divergence_candles():
    prices=[120-i*0.15 for i in range(100)] + [106,105,104,105,107,109,108,106,105,103,104,106]
    out=[]
    for i,p in enumerate(prices):
        out.append({'open_time':i*3600000,'close_time':(i+1)*3600000-1,'open':p,'high':p+1,'low':p,'close':p,'volume':10000000})
    return out

def test_bullish_rsi_divergence_is_detected():
    cs=_divergence_candles()
    from indicators_engine import compute_rsi_series
    from setup_score import _divergence
    rsi=compute_rsi_series([c['close'] for c in cs],14)
    d=_divergence(cs,rsi)
    assert d is not None
    assert d['price_2'] < d['price_1']
    assert d['rsi_2'] > d['rsi_1'] + 1.0

