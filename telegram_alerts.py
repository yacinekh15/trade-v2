"""Telegram alerts with persistent deduplication in Upstash Redis."""

import requests

from config import (
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    ALERT_SETUP_TYPES,
    ALERT_MIN_SCORE,
    ALERT_COOLDOWN_MINUTES,
)
from upstash_client import get_json, set_json

ALERT_STATE_KEY = "alerted_state_v2"


def send_message(text):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }
    try:
        resp = requests.post(url, data=payload, timeout=10)
        resp.raise_for_status()
        return True
    except Exception as e:
        print(f"[telegram] send failed: {e}")
        return False


def _alert_key(timeframe, symbol):
    return f"{timeframe}:{symbol}"


def _trade_levels(result):
    """Derive informational ATR-based levels for the Telegram message."""
    price = float(result["price"])
    atr = float(result["indicators"].get("atr") or 0)
    resistance = float(result["indicators"].get("resistance") or price)
    support = float(result["indicators"].get("support") or price)

    if atr <= 0:
        return price, resistance, support

    # Informational levels only; execution is intentionally not automated.
    entry = price
    stop = min(support, price - 1.5 * atr)
    target = max(resistance, price + 2.0 * atr)
    if target <= entry:
        target = entry + 2.0 * atr
    if stop >= entry:
        stop = max(0.0, entry - 1.5 * atr)
    return entry, target, stop


def _fmt_price(value):
    if value >= 1000:
        return f"{value:,.2f}"
    if value >= 1:
        return f"{value:,.4f}"
    return f"{value:.8f}".rstrip("0").rstrip(".")


def check_and_alert(results, timeframe):
    """Alert only on a newly qualifying setup or after its cooldown."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return {"sent": 0, "skipped": 0, "configured": False}

    now = __import__("time").time()
    state = get_json(ALERT_STATE_KEY, default={}) or {}
    changed = False
    sent = 0
    skipped = 0

    for result in results:
        symbol = result["symbol"]
        key = _alert_key(timeframe, symbol)
        qualifies = (
            result["setup_type"] in ALERT_SETUP_TYPES
            and result["score"] >= ALERT_MIN_SCORE
        )

        previous = state.get(key)
        if not qualifies:
            if previous is not None:
                del state[key]
                changed = True
            continue

        setup = result["setup_type"]
        recently_sent = (
            isinstance(previous, dict)
            and previous.get("setup_type") == setup
            and now - float(previous.get("sent_at", 0))
            < ALERT_COOLDOWN_MINUTES * 60
        )
        if recently_sent:
            skipped += 1
            continue

        entry, target, stop = _trade_levels(result)
        reasons = "\n".join(f"• {reason}" for reason in result["reasons"])
        text = (
            f"🚨 *{setup} — {symbol}*\n"
            f"Timeframe: `{timeframe}`\n"
            f"Score: *{result['score']}/100*\n\n"
            f"Entry/reference: `{_fmt_price(entry)}`\n"
            f"Target/reference: `{_fmt_price(target)}`\n"
            f"Invalidation/reference: `{_fmt_price(stop)}`\n\n"
            f"*Reasons*\n{reasons}\n\n"
            f"RSI: `{result['indicators']['rsi']}` | "
            f"Volume: `{result['indicators']['volume_ratio']}x`\n"
            f"_Technical screening only — not an instruction to trade._"
        )

        if send_message(text):
            state[key] = {"setup_type": setup, "sent_at": now, "score": result["score"]}
            changed = True
            sent += 1

    if changed:
        set_json(ALERT_STATE_KEY, state)

    return {"sent": sent, "skipped": skipped, "configured": True}
