"""Selective Telegram alerts; website toggle is server-persisted and affects sending only."""
import time,requests
from config import TELEGRAM_BOT_TOKEN,TELEGRAM_CHAT_ID,ALERT_COOLDOWN_MINUTES,ALERT_MAX_PER_SCAN,ALERT_MIN_SCORE
from upstash_client import get_json,set_json
KEY='telegram_alert_state'

def send_message(text):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:return False
    r=requests.post(f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage',json={'chat_id':TELEGRAM_CHAT_ID,'text':text},timeout=10); r.raise_for_status(); return True

def _f(v):
    if v is None:return '—'
    return f'{float(v):,.8f}'.rstrip('0').rstrip('.')

def _msg(r):
    i=r['indicators']; a=r['analysis']; checks=['✓ closed candle', '✓ liquidity filter','✓ risk validation']
    if i.get('volume_ratio',0)>=1.2:checks.append('✓ volume confirmation')
    return (f'🟢 LONG SPOT ALERT\nSymbol: {r["symbol"]}\nTimeframe: {r["timeframe"]}\nSetup: {r["setup_type"]}\nScore: {r["score"]}/100\n\n'
            f'Entry reference: {_f(r["price"])}\nInvalidation: {_f(a.get("sl"))}\nTP1: {_f((a.get("tp") or [{}])[0].get("level"))}\nTP2: {_f((a.get("tp") or [{},{}])[1].get("level"))}\n'
            f'MTF: {r.get("mtf_states",{})}\nConfirmations: {", ".join(checks)}\n\nScanner reference levels only; manually verify the chart.')

def check_and_alert(results,timeframe,enabled=True):
    if not enabled:return {'sent':0,'skipped':0,'candidates':0,'enabled':False,'configured':bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)}
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:return {'sent':0,'skipped':0,'candidates':0,'enabled':True,'configured':False}
    state=get_json(KEY,{}) or {}; now=time.time(); sent=skipped=candidates=0; changed=False
    for r in results:
        if not r.get('telegram_eligible') or r.get('score',0)<ALERT_MIN_SCORE:continue
        candidates+=1; key=f'{r["symbol"]}:{timeframe}:{r["setup_type"]}:{r.get("signal_time")}'; old=state.get(key)
        if old: skipped+=1; continue
        if sent>=ALERT_MAX_PER_SCAN: skipped+=1; continue
        try:
            if send_message(_msg(r)): state[key]={'sent_at':now}; sent+=1; changed=True
        except Exception: skipped+=1
    # keep recent state bounded
    if len(state)>2000: state=dict(list(state.items())[-1000:])
    if changed:set_json(KEY,state)
    return {'sent':sent,'skipped':skipped,'candidates':candidates,'enabled':True,'configured':True}

def check_and_alert_mtf(results,enabled=True):
    return check_and_alert(results,'ALL',enabled)
