"""Selective Telegram alerts plus a separate instant EMA200 reclaim alert path."""
import time
import requests
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, ALERT_MAX_PER_SCAN, ALERT_MIN_SCORE
from upstash_client import get_json, set_json

KEY = 'telegram_alert_state'
INSTANT_KEY = 'telegram_instant_reclaim_state'
INSTANT_ENABLED_KEY = 'telegram_instant_reclaim_enabled'
INSTANT_MAX_PER_SCAN = 20


def send_message(text):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False
    r = requests.post(
        f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage',
        json={'chat_id': TELEGRAM_CHAT_ID, 'text': text},
        timeout=10,
    )
    r.raise_for_status()
    return True


def _f(v):
    if v is None:
        return '—'
    return f'{float(v):,.8f}'.rstrip('0').rstrip('.')


def _msg(r):
    i = r['indicators']
    a = r['analysis']
    checks = ['✓ closed candle', '✓ liquidity filter', '✓ risk validation']
    if i.get('volume_ratio', 0) >= 1.2:
        checks.append('✓ volume confirmation')
    return (
        f'🟢 LONG SPOT ALERT\nSymbol: {r["symbol"]}\nTimeframe: {r["timeframe"]}\n'
        f'Setup: {r["setup_type"]}\nScore: {r["score"]}/100\n\n'
        f'Entry reference: {_f(r["price"])}\nInvalidation: {_f(a.get("sl"))}\n'
        f'TP1: {_f((a.get("tp") or [{}])[0].get("level"))}\n'
        f'TP2: {_f((a.get("tp") or [{},{}])[1].get("level"))}\n'
        f'MTF: {r.get("mtf_states",{})}\nConfirmations: {", ".join(checks)}\n\n'
        f'Scanner reference levels only; manually verify the chart.'
    )


def check_and_alert(results, timeframe, enabled=True):
    if not enabled:
        return {'sent': 0, 'skipped': 0, 'candidates': 0, 'enabled': False,
                'configured': bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)}
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return {'sent': 0, 'skipped': 0, 'candidates': 0, 'enabled': True, 'configured': False}
    state = get_json(KEY, {}) or {}
    sent = skipped = candidates = 0
    changed = False
    for r in results:
        if not r.get('telegram_eligible') or r.get('score', 0) < ALERT_MIN_SCORE:
            continue
        candidates += 1
        key = f'{r["symbol"]}:{timeframe}:{r["setup_type"]}:{r.get("signal_time")}'
        if state.get(key):
            skipped += 1
            continue
        if sent >= ALERT_MAX_PER_SCAN:
            skipped += 1
            continue
        try:
            if send_message(_msg(r)):
                state[key] = {'sent_at': time.time()}
                sent += 1
                changed = True
        except Exception:
            skipped += 1
    if len(state) > 2000:
        state = dict(list(state.items())[-1000:])
    if changed:
        set_json(KEY, state)
    return {'sent': sent, 'skipped': skipped, 'candidates': candidates, 'enabled': True, 'configured': True}


def check_and_alert_mtf(results, enabled=True):
    return check_and_alert(results, 'ALL', enabled)


def _instant_msg(r):
    qualified = bool(r.get('qualified'))
    reasons = r.get('rejection_reasons') or []
    reason_text = ', '.join(str(x) for x in reasons) if reasons else 'none'
    return (
        '⚡ INSTANT EMA200 CROSS ALERT\n'
        'UNFILTERED / MANUAL VERIFICATION REQUIRED\n\n'
        f'Symbol: {r.get("symbol", "—")}\n'
        f'Timeframe: {r.get("timeframe", "—")}\n'
        'Setup: EMA200_RECLAIM\n'
        f'Entry reference: {_f(r.get("price"))}\n'
        f'Score: {r.get("score", 0)}/100\n'
        f'Normal engine qualified: {"YES" if qualified else "NO"}\n'
        f'Rejection reasons: {reason_text}\n\n'
        'This alert intentionally bypasses the normal score, volume, and MTF quality gate.\n'
        'It does NOT mean this is a good trade. Verify the TradingView chart manually before acting.'
    )


def check_instant_reclaim_alerts(results, timeframe, enabled):
    """Send every EMA200 reclaim result, independently of the normal quality gate."""
    configured = bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)
    if not enabled or not configured:
        return {'sent': 0, 'skipped': 0, 'candidates': 0, 'enabled': bool(enabled),
                'configured': configured}

    state = get_json(INSTANT_KEY, {}) or {}
    sent = skipped = candidates = 0
    changed = False
    for r in results:
        if r.get('setup_type') != 'EMA200_RECLAIM':
            continue
        candidates += 1
        key = f'{r.get("symbol")}:{timeframe}:{r.get("signal_time")}'
        if state.get(key):
            skipped += 1
            continue
        if sent >= INSTANT_MAX_PER_SCAN:
            skipped += 1
            continue
        try:
            if send_message(_instant_msg(r)):
                state[key] = {'sent_at': time.time()}
                sent += 1
                changed = True
        except Exception:
            skipped += 1

    if len(state) > 5000:
        state = dict(list(state.items())[-2500:])
    if changed:
        set_json(INSTANT_KEY, state)
    return {'sent': sent, 'skipped': skipped, 'candidates': candidates,
            'enabled': True, 'configured': True}
