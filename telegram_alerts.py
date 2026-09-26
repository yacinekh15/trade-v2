"""Selective Telegram alerts for high-quality setups only."""
import time, requests
from config import (
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, ALERT_SETUP_TYPES, ALERT_MIN_SCORE,
    ALERT_MIN_VOLUME_RATIO, ALERT_MIN_ENTRY_QUALITY, ALERT_COOLDOWN_MINUTES, ALERT_EMA_EQUAL,
    ALERT_MAX_PER_SCAN,
)
from upstash_client import get_json, set_json
ALERT_STATE_KEY = "alerted_state_v4"


def send_message(text):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            data={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown", "disable_web_page_preview": True},
            timeout=10,
        )
        r.raise_for_status()
        return True
    except Exception as e:
        print(f"[telegram] send failed: {e}")
        return False


def _fmt(v):
    v = float(v)
    if v >= 1000: return f"{v:,.2f}"
    if v >= 1: return f"{v:,.4f}"
    return f"{v:.8f}".rstrip("0").rstrip(".")


def _levels(r):
    p = float(r["price"])
    atr = float(r["indicators"].get("atr") or 0)
    sup = float(r["indicators"].get("support") or p)
    res = float(r["indicators"].get("resistance") or p)
    if atr <= 0: return p, res, sup
    return p, max(res, p + 2 * atr), max(0, min(sup, p - 1.5 * atr))


def _is_bullish(r):
    i = r.get("indicators", {})
    return i.get("ema20", 0) > i.get("ema50", 0) and i.get("macd", 0) > i.get("macd_signal", 0)


def _mtf_qualified(symbol, tf, by_tf):
    """Require higher-timeframe bullish agreement for lower-timeframe alerts."""
    order = {"5m": ["15m", "1h", "4h"], "15m": ["1h", "4h"], "1h": ["4h"], "4h": []}
    higher = order.get(tf, [])
    if not higher:
        return True, []
    missing_or_bearish = []
    for h in higher:
        r = by_tf.get(h, {}).get(symbol)
        if not r or not _is_bullish(r):
            missing_or_bearish.append(h)
    return not missing_or_bearish, missing_or_bearish


def _eligible(r, tf, by_tf):
    setup = r.get("setup_type")
    score = int(r.get("score", 0))
    quality = int(r.get("entry_quality", 0))
    vol = float(r.get("indicators", {}).get("volume_ratio") or 0)
    analysis = r.get("analysis", {})
    if setup not in ALERT_SETUP_TYPES or score < ALERT_MIN_SCORE or quality < ALERT_MIN_ENTRY_QUALITY or vol < ALERT_MIN_VOLUME_RATIO:
        return False, "quality/setup/volume filter"
    if not r.get("qualified") or not analysis.get("rule_passed"):
        return False, "entry quality or R:R failed"
    if not _is_bullish(r):
        return False, "trend/momentum conflict"
    ok, missing = _mtf_qualified(r["symbol"], tf, by_tf)
    if not ok:
        return False, f"higher timeframe conflict: {','.join(missing)}"
    return True, "qualified"


def _message(r, tf, by_tf):
    symbol = r["symbol"]
    entry, target, stop = _levels(r)
    reasons = "\n".join(f"• {x}" for x in r.get("reasons", []))
    higher = {h: ("🟢" if _is_bullish(by_tf[h].get(symbol, {})) else "🔴") for h in ["5m", "15m", "1h", "4h"] if h in by_tf and symbol in by_tf[h]}
    mtf = "  ".join(f"{h} {v}" for h, v in higher.items())
    return (
        f"🚨 *HIGH-QUALITY {r['setup_type']}*\n"
        f"Symbol: `{symbol}`\nTimeframe: `{tf}`\nScore: *{r['score']}/100* | Entry quality: *{r.get('entry_quality', 0)}/100*\n\n"
        f"Entry/reference: `{_fmt(entry)}`\nTarget/reference: `{_fmt(target)}`\nInvalidation/reference: `{_fmt(stop)}`\n\n"
        f"*MTF*\n{mtf or '—'}\n\n*Why*\n{reasons}\n\n"
        f"RSI: `{r['indicators']['rsi']}` | Volume: `{r['indicators']['volume_ratio']}x`\n"
        f"EMA20: `{_fmt(r['indicators']['ema20'])}` | EMA50: `{_fmt(r['indicators']['ema50'])}`\n\n"
        f"\n*Analysis*\nBias: `{r.get('analysis', {}).get('bias', '—')}`\n"
        f"Entry zone: `{_fmt(r.get('analysis', {}).get('entry', {}).get('low', entry))}` – `{_fmt(r.get('analysis', {}).get('entry', {}).get('high', entry))}`\n"
        f"SL: `{_fmt(r.get('analysis', {}).get('sl', stop))}` | TP1 R:R: `{r.get('analysis', {}).get('rr_tp1', 0)}`\n"
        f"Confidence: `{r.get('analysis', {}).get('confidence', '—')}`\n"
        f"Invalidation: {r.get('analysis', {}).get('invalidation', '—')}\n"
        f"Counter-argument: {r.get('analysis', {}).get('counter_argument', '—')}\n\n"
        f"_Scanner alert only. Verify the chart and setup before making any trading decision._"
    )



def _ema_convergence_message(r, tf):
    i = r.get("indicators", {})
    gap = float(i.get("ema_gap_pct") or 0)
    direction = "reached EMA50 from below" if not r.get("ema_cross_up") else "crossed EMA50 from below"
    return (
        f"⚠️ *EMA20/EMA50 CONVERGENCE*\n"
        f"Symbol: `{r['symbol']}`\nTimeframe: `{tf}`\n"
        f"EMA20: `{_fmt(i.get('ema20', 0))}`\n"
        f"EMA50: `{_fmt(i.get('ema50', 0))}`\n"
        f"Gap: `{gap:.3f}%`\n\n"
        f"EMA20 was below EMA50 and has {direction}.\n"
        f"This is a *watch alert*, not a buy/sell signal.\n"
        f"Wait for price structure, volume, momentum and higher-timeframe confirmation.\n\n"
        f"_Scanner watch alert only. Verify the chart before making any trading decision._"
    )

def check_ema_convergence_alert(results, timeframe, enabled=True):
    """Independent EMA20/EMA50 watch channel."""
    if not enabled:
        return {"sent": 0, "skipped": 0, "configured": bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID),
                "enabled": False, "candidates": 0,
                "reason": "EMA convergence alerts disabled by dashboard toggle."}
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return {"sent": 0, "skipped": 0, "configured": False, "enabled": True, "candidates": 0}
    if not ALERT_EMA_EQUAL:
        return {"sent": 0, "skipped": 0, "configured": True, "enabled": True, "candidates": 0}

    state = get_json(ALERT_STATE_KEY, default={}) or {}
    now = time.time()
    sent = skipped = candidates = 0
    changed = False

    for r in results:
        if not r.get("ema_convergence_from_below"):
            continue
        candidates += 1
        key = f"EMA_FROM_BELOW:{timeframe}:{r['symbol']}"
        prev = state.get(key)
        if isinstance(prev, dict) and now - float(prev.get("sent_at", 0)) < ALERT_COOLDOWN_MINUTES * 60:
            skipped += 1
            continue
        if sent >= ALERT_MAX_PER_SCAN:
            skipped += 1
            continue
        if send_message(_ema_convergence_message(r, timeframe)):
            state[key] = {"sent_at": now, "gap": r.get("indicators", {}).get("ema_gap_pct")}
            changed = True
            sent += 1

    if changed:
        set_json(ALERT_STATE_KEY, state)
    return {"sent": sent, "skipped": skipped, "configured": True, "enabled": True,
            "candidates": candidates, "reason": "EMA20 reached EMA50 from below watch alerts only."}


def check_and_alert(results, timeframe, enabled=True):
    """Independent normal setup alert channel."""
    if not enabled:
        return {"sent": 0, "skipped": 0, "configured": bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID),
                "enabled": False, "candidates": 0,
                "reason": "Normal setup alerts disabled by dashboard toggle."}
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return {"sent": 0, "skipped": 0, "configured": False, "enabled": True, "candidates": 0}

    state = get_json(ALERT_STATE_KEY, default={}) or {}
    now = time.time()
    sent = skipped = candidates = 0
    changed = False

    for r in sorted(results, key=lambda x: x.get("score", 0), reverse=True):
        qualified, _ = _eligible(r, timeframe, {timeframe: {r["symbol"]: r}})
        if not qualified:
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
        if send_message(_message(r, timeframe, {timeframe: {r["symbol"]: r}})):
            state[key] = {"sent_at": now, "score": r["score"]}
            changed = True
            sent += 1

    if changed:
        set_json(ALERT_STATE_KEY, state)
    return {"sent": sent, "skipped": skipped, "configured": True, "enabled": True,
            "candidates": candidates, "max_per_scan": ALERT_MAX_PER_SCAN}


def check_and_alert_mtf(scan_payloads, enabled=True):
    if not enabled:
        return {"sent": 0, "skipped": 0, "configured": bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID), "enabled": False, "candidates": 0, "reason": "Telegram sending disabled by dashboard toggle."}
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return {"sent": 0, "skipped": 0, "configured": False, "candidates": 0}
    by_tf = {}
    for tf, payload in scan_payloads.items():
        by_tf[tf] = {r["symbol"]: r for r in payload.get("results", [])}
    state = get_json(ALERT_STATE_KEY, default={}) or {}
    now = time.time(); sent = skipped = candidates = 0; changed = False
    # Higher-value timeframes first; one alert per symbol/setup/timeframe per cooldown.
    for tf in ["1h", "15m", "4h", "5m"]:
        for r in sorted(by_tf.get(tf, {}).values(), key=lambda x: x.get("score", 0), reverse=True):
            qualified, _ = _eligible(r, tf, by_tf)
            if not qualified:
                continue
            candidates += 1
            key = f"{tf}:{r['symbol']}:{r['setup_type']}"
            prev = state.get(key)
            if isinstance(prev, dict) and now - float(prev.get("sent_at", 0)) < ALERT_COOLDOWN_MINUTES * 60:
                skipped += 1
                continue
            if sent >= ALERT_MAX_PER_SCAN:
                skipped += 1
                continue
            if send_message(_message(r, tf, by_tf)):
                state[key] = {"sent_at": now, "score": r["score"]}
                changed = True; sent += 1
    if changed:
        set_json(ALERT_STATE_KEY, state)
    return {"sent": sent, "skipped": skipped, "configured": True, "enabled": True, "candidates": candidates, "max_per_scan": ALERT_MAX_PER_SCAN}
