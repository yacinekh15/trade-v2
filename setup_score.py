"""Long-only spot entry engine.

Signals implemented exactly as the current project rules:
1) EMA200_RECLAIM:
   - the two immediately preceding CLOSED candles both closed below EMA200
   - the signal candle CLOSED above EMA200
2) BULLISH_DIVERGENCE:
   - price is above EMA200
   - two confirmed pivot lows form a lower low in price and a higher low in RSI
   - the current closed candle is a 5-candle bullish confirmation:
     its close is above the closes of the four preceding closed candles.

No shorts, futures, leverage, MACD, EMA20/50, or sell-short logic is used.
"""
from indicators_engine import compute_ema_series, compute_rsi_series, compute_atr

TRADE_SETUPS = {"EMA200_RECLAIM", "BULLISH_DIVERGENCE"}
PIVOT_LEFT = 2
PIVOT_RIGHT = 2
RSI_PERIOD = 14
SWING_LOOKBACK = 80


def _round(v, d=8):
    return None if v is None else round(float(v), d)


def _pivot_lows(candles, rsi, left=2, right=2, start=0, end=None):
    end = len(candles) if end is None else end
    pivots = []
    for i in range(max(start, left), min(end - right, len(candles) - right)):
        low = candles[i]["low"]
        if all(low < candles[j]["low"] for j in range(i-left, i)) and \
           all(low <= candles[j]["low"] for j in range(i+1, i+right+1)):
            if rsi[i] is not None:
                pivots.append(i)
    return pivots


def _find_bullish_divergence(candles, rsi):
    """Return the latest valid pivot pair if regular bullish divergence exists.

    Both pivots are confirmed (two candles to the right). The second pivot must
    be recent enough to represent the current correction, and the signal candle
    comes after it.
    """
    end = len(candles) - 1  # leave the signal candle out of pivot formation
    pivots = _pivot_lows(candles, rsi, PIVOT_LEFT, PIVOT_RIGHT, max(0, end-SWING_LOOKBACK), end)
    if len(pivots) < 2:
        return None
    p2 = pivots[-1]
    # Require the second pivot to be within the recent correction window.
    if end - p2 > 20:
        return None
    for k in range(len(pivots)-2, -1, -1):
        p1 = pivots[k]
        price_lower_low = candles[p2]["low"] < candles[p1]["low"]
        rsi_higher_low = rsi[p2] > rsi[p1]
        if price_lower_low and rsi_higher_low:
            return {
                "first_pivot": p1,
                "second_pivot": p2,
                "price_1": candles[p1]["low"],
                "price_2": candles[p2]["low"],
                "rsi_1": rsi[p1],
                "rsi_2": rsi[p2],
            }
    return None


def _five_candle_confirmation(candles):
    """Conservative machine-readable interpretation of the video's 5-candle rule.

    The signal is the fifth candle: it must be bullish and close above the
    closes of the four candles immediately before it.
    """
    if len(candles) < 5:
        return False
    five = candles[-5:]
    return five[-1]["close"] > five[-1]["open"] and \
           five[-1]["close"] > max(c["close"] for c in five[:-1])


def _swing_low_for_sl(candles, divergence=None):
    lows = [c["low"] for c in candles[-12:]]
    if divergence:
        p = divergence["second_pivot"]
        lows = [c["low"] for c in candles[max(0, p-2):p+3]]
    return min(lows)


def _score(ema_reclaim, divergence, above_ema, confirmation, rr):
    score = 0
    if above_ema: score += 25
    if ema_reclaim: score += 35
    if divergence: score += 30
    if confirmation: score += 10
    if rr >= 2: score += 5
    return min(100, score)


def score_symbol(symbol, candles):
    # Binance returns the newest candle, which may still be forming.
    if not candles or len(candles) < 210:
        return None
    closed = candles[:-1]
    if len(closed) < 205:
        return None

    closes = [float(c["close"]) for c in closed]
    ema200 = compute_ema_series(closes, 200)
    rsi = compute_rsi_series(closes, RSI_PERIOD)
    if ema200[-1] is None or rsi[-1] is None:
        return None

    price = closes[-1]
    ema = ema200[-1]
    prev_ema = ema200[-2]
    # Exact reclaim rule: the two candles before the signal candle closed below EMA200.
    below_1 = closes[-2] < ema200[-2]
    below_2 = closes[-3] < ema200[-3]
    ema_reclaim = below_1 and below_2 and price > ema and closes[-2] <= prev_ema

    divergence = _find_bullish_divergence(closed, rsi)
    above_ema = price > ema
    confirmation = _five_candle_confirmation(closed)

    setup = None
    reasons = []
    if ema_reclaim:
        setup = "EMA200_RECLAIM"
        reasons = [
            "Previous 2 closed candles were below EMA200",
            "Current closed candle reclaimed EMA200",
            "Signal is long-only / spot",
        ]
    elif divergence and above_ema and confirmation:
        setup = "BULLISH_DIVERGENCE"
        reasons = [
            "Price is above EMA200",
            "Regular bullish RSI divergence detected",
            "5-candle bullish confirmation closed",
        ]

    # Levels use actual recent structure, not arbitrary fixed percentages.
    swing_low = _swing_low_for_sl(closed, divergence)
    # A tiny structural buffer reduces same-candle noise without manufacturing a target.
    risk_buffer = max((price - swing_low) * 0.03, price * 0.0005)
    sl = swing_low - risk_buffer
    if sl <= 0 or sl >= price:
        sl = price * 0.98
    risk = price - sl
    tp_2r = price + 2 * risk
    tp_3r = price + 3 * risk

    # Divergence signal is only eligible when all its stated conditions pass.
    qualified = setup in TRADE_SETUPS
    rr = 2.0

    if setup == "EMA200_RECLAIM":
        reasons.append(f"Stop below recent swing low: {sl:.8g}")
    elif setup == "BULLISH_DIVERGENCE":
        reasons.append(f"Price low {divergence['price_2']:.8g} < {divergence['price_1']:.8g}")
        reasons.append(f"RSI low {divergence['rsi_2']:.2f} > {divergence['rsi_1']:.2f}")
        reasons.append(f"Stop below divergence swing low: {sl:.8g}")

    score = _score(ema_reclaim, bool(divergence), above_ema, confirmation, rr)
    if not qualified:
        score = max(score, 0)

    return {
        "symbol": symbol,
        "price": _round(price),
        "score": score,
        "entry_quality": score,
        "qualified": qualified,
        "setup_type": setup or "NO_SIGNAL",
        "direction": "LONG" if qualified else "NONE",
        "timeframe": None,
        "reasons": reasons or ["No qualifying long setup"],
        "rejection_reasons": [] if qualified else [
            "Waiting for EMA200 reclaim or bullish divergence confirmation"
        ],
        "analysis": {
            "bias": "LONG" if qualified else "WAIT",
            "setup": setup or "NO_SIGNAL",
            "entry": {"low": _round(price), "high": _round(price)},
            "sl": _round(sl),
            "tp": [
                {"level": _round(tp_2r), "rr": 2.0, "reason": "2R reference target"},
                {"level": _round(tp_3r), "rr": 3.0, "reason": "3R reference target"},
            ],
            "rr_tp1": 2.0,
            "rule_passed": qualified,
            "confidence": "Rule-confirmed" if qualified else "Waiting",
            "invalidation": f"Long thesis invalid below {sl:.8g}.",
            "counter_argument": "A confirmed setup can still fail; the scanner does not predict profit.",
            "historical": "[Not a backtest result] Strategy rules are derived from the supplied video summaries.",
        },
        "indicators": {
            "ema200": _round(ema),
            "ema200_prev": _round(prev_ema),
            "rsi": _round(rsi[-1], 2),
            "rsi_prev": _round(rsi[-2], 2),
            "price_above_ema200": above_ema,
            "ema200_reclaim": ema_reclaim,
            "two_closes_below_ema200": below_1 and below_2,
            "bullish_divergence": bool(divergence),
            "five_candle_confirmation": confirmation,
            "swing_low": _round(swing_low),
            "risk": _round(risk),
            "tp_2r": _round(tp_2r),
            "tp_3r": _round(tp_3r),
            "divergence": divergence,
        },
    }
