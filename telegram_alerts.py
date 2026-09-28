"""Telegram alerts for the two approved long-only spot setups."""
import time
import requests
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, ALERT_COOLDOWN_MINUTES, ALERT_MAX_PER_SCAN
from upstash_client import get_json, set_json

ALERT_STATE_KEY = "telegram_alert_state"


def send_message(text):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    r = requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"}, timeout=10)
    r.raise_for_status()
    return True


def _fmt(v):
    if v is None:
        return "—"
    return f"{float(v):,.8f}".rstrip("0").rstrip(".")


def _message(r, tf):
    i = r["indicators"]
    a = r["analysis"]
    div = i.get("divergence") or {}
    extra = ""
    if r["setup_type"] == "BULLISH_DIVERGENCE":
        extra = (
            f"\nPrice lows: `{_fmt(div.get('price_1'))}` → `{_fmt(div.get('price_2'))}`"
            f"\nRSI lows: `{_fmt(div.get('rsi_1'))}` → `{_fmt(div.get('rsi_2'))}`"
        )
    return (
        f"🟢 *LONG SPOT ALERT*\n"
        f"Symbol: `{r['symbol']}`\nTimeframe: `{tf}`\n"
        f"Setup: *{r['setup_type']}*\n\n"
        f"Entry: `{_fmt(r['price'])}`\n"
        f"EMA200: `{_fmt(i.get('ema200'))}`\n"
        f"SL: `{_fmt(a.get('sl'))}`\n"
        f"TP 2R: `{_fmt(i.get('tp_2r'))}`\n"
        f"TP 3R: `{_fmt(i.get('tp_3r'))}`"
        f"{extra}\n\n"
        f"Rules: {'; '.join(r.get('reasons', [])[:4])}\n\n"
        f"_Spot/long-only scanner alert. Verify the chart before trading._"
    )


def check_and_alert(results, timeframe, enabled=True):
    if not enabled:
        return {"sent": 0, "skipped": 0, "candidates": 0, "configured": bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID), "enabled": False}
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return {"sent": 0, "skipped": 0, "candidates": 0, "configured": False, "enabled": True}
    state = get_json(ALERT_STATE_KEY, default={}) or {}
    now = time.time()
    sent = skipped = candidates = 0
    changed = False
    for r in sorted(results, key=lambda x: x.get("score", 0), reverse=True):
        if not r.get("qualified") or r.get("setup_type") not in {"EMA200_RECLAIM", "BULLISH_DIVERGENCE"}:
            continue
        candidates += 1
        key = f"{timeframe}:{r['symbol']}:{r['setup_type']}"
        prev = state.get(key)
        if isinstance(prev, dict) and now - float(prev.get("sent_at", 0)) < ALERT_COOLDOWN_MINUTES * 60:
            skipped += 1
            continue
        if sent >= ALERT_MAX_PER_SCAN:
            skipped += 1
            continue
        if send_message(_message(r, timeframe)):
            state[key] = {"sent_at": now, "score": r.get("score", 0)}
            changed = True
            sent += 1
    if changed:
        set_json(ALERT_STATE_KEY, state)
    return {"sent": sent, "skipped": skipped, "candidates": candidates, "configured": True, "enabled": True, "max_per_scan": ALERT_MAX_PER_SCAN}


def check_and_alert_mtf(scan_payloads, enabled=True):
    if not enabled:
        return {"sent": 0, "skipped": 0, "candidates": 0, "configured": bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID), "enabled": False}
    sent = skipped = candidates = 0
    # Use the existing per-timeframe cooldown state; scan high timeframes first.
    for tf in ["4h", "1h", "15m", "5m"]:
        payload = scan_payloads.get(tf)
        if not payload:
            continue
        remaining = max(0, ALERT_MAX_PER_SCAN - sent)
        if remaining == 0:
            break
        result = check_and_alert(payload.get("results", []), tf, enabled=True)
        sent += result.get("sent", 0)
        skipped += result.get("skipped", 0)
        candidates += result.get("candidates", 0)
    return {"sent": sent, "skipped": skipped, "candidates": candidates, "configured": bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID), "enabled": True}
