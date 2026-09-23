"""Telegram alerts with persistent deduplication."""
import time, requests
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, ALERT_SETUP_TYPES, ALERT_MIN_SCORE, ALERT_COOLDOWN_MINUTES, ALERT_EMA_EQUAL
from upstash_client import get_json, set_json
ALERT_STATE_KEY="alerted_state_v3"

def send_message(text):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID: return False
    try:
        r=requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",data={"chat_id":TELEGRAM_CHAT_ID,"text":text,"parse_mode":"Markdown","disable_web_page_preview":True},timeout=10)
        r.raise_for_status(); return True
    except Exception as e: print(f"[telegram] send failed: {e}"); return False

def _fmt(v):
    v=float(v)
    if v>=1000:return f"{v:,.2f}"
    if v>=1:return f"{v:,.4f}"
    return f"{v:.8f}".rstrip('0').rstrip('.')

def _levels(r):
    p=float(r["price"]); atr=float(r["indicators"].get("atr") or 0); sup=float(r["indicators"].get("support") or p); res=float(r["indicators"].get("resistance") or p)
    if atr<=0:return p,res,sup
    return p,max(res,p+2*atr),max(0,min(sup,p-1.5*atr))

def check_and_alert(results,timeframe):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:return {"sent":0,"skipped":0,"configured":False}
    now=time.time(); state=get_json(ALERT_STATE_KEY,default={}) or {}; sent=skipped=0; changed=False
    for r in results:
        symbol=r["symbol"]; setup=r["setup_type"]; key=f"{timeframe}:{symbol}:{setup}"
        normal=setup in ALERT_SETUP_TYPES and r["score"]>=ALERT_MIN_SCORE
        ema_event=ALERT_EMA_EQUAL and r.get("ema_equal",False)
        if not normal and not ema_event:
            continue
        kind="EMA_EQUAL" if ema_event and not normal else setup
        k=f"{timeframe}:{symbol}:{kind}"; prev=state.get(k)
        if isinstance(prev,dict) and now-float(prev.get("sent_at",0))<ALERT_COOLDOWN_MINUTES*60:
            skipped+=1; continue
        entry,target,stop=_levels(r); reasons="\n".join(f"• {x}" for x in r.get("reasons",[]))
        title="EMA20 ≈ EMA50" if kind=="EMA_EQUAL" else f"{kind} — {symbol}"
        text=(f"🔔 *{title}*\nSymbol: `{symbol}`\nTimeframe: `{timeframe}`\nScore: *{r['score']}/100*\n\n"
              f"Entry/reference: `{_fmt(entry)}`\nTarget/reference: `{_fmt(target)}`\nInvalidation/reference: `{_fmt(stop)}`\n\n"
              f"*Why*\n{reasons}\n\nRSI: `{r['indicators']['rsi']}` | EMA20: `{_fmt(r['indicators']['ema20'])}` | EMA50: `{_fmt(r['indicators']['ema50'])}`\n"
              f"_Technical screening only — not an instruction to trade._")
        if send_message(text):
            state[k]={"sent_at":now,"score":r["score"]}; changed=True; sent+=1
    if changed:set_json(ALERT_STATE_KEY,state)
    return {"sent":sent,"skipped":skipped,"configured":True}
