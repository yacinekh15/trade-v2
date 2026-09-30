"""Telegram sender with duplicate protection. Website results are never filtered by Telegram."""
import time, requests
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, ALERT_COOLDOWN_MINUTES, ALERT_MAX_PER_SCAN
try:
    from upstash_client import get_json, set_json
except Exception:
    get_json=lambda *a,**k: {}
    set_json=lambda *a,**k: None

STATE_KEY="trade_hhj_alert_state_v1"


def send_message(text):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:return False
    try:
        r=requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",data={"chat_id":TELEGRAM_CHAT_ID,"text":text,"disable_web_page_preview":True},timeout=10)
        r.raise_for_status(); return True
    except Exception as e:
        print(f"[telegram] {e}"); return False


def alert_signals(results,timeframe,enabled=True):
    if not enabled:return {"sent":0,"skipped":0,"configured":bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID),"enabled":False}
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:return {"sent":0,"skipped":0,"configured":False,"enabled":True}
    state=get_json(STATE_KEY,default={}) or {}; now=time.time(); sent=skipped=0; changed=False
    for r in results:
        if not r.get("signal"):continue
        key=f"{timeframe}:{r['symbol']}:{r['setup_type']}:{r.get('signal_time',r['symbol'])}"
        old=state.get(key)
        if old and now-float(old)<ALERT_COOLDOWN_MINUTES*60:skipped+=1;continue
        if sent>=ALERT_MAX_PER_SCAN:skipped+=1;continue
        text=(f"TRADE-HHJ scanner alert\n{r['symbol']} | {timeframe}\nSetup: {r['setup_type']}\n"
              f"Context score: {r.get('score',0)}/100\nReference: {r.get('entry_reference') or r.get('price')}\n"
              f"Why: {'; '.join(r.get('reasons',[])[:5])}\n\nScanner only — manually verify the chart.")
        if send_message(text):state[key]=now;changed=True;sent+=1
    if changed:set_json(STATE_KEY,state)
    return {"sent":sent,"skipped":skipped,"configured":True,"enabled":True}
