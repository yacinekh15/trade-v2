"""Deterministic technical setup scoring for the Halal Crypto Scanner.

The scanner is deliberately conservative: the score is a rule-alignment score,
not a probability of profit.
"""
from indicators_engine import (
    compute_atr, compute_ema_series, compute_macd, compute_rsi,
    compute_support_resistance, compute_volume_ratio, ema_relationship,
    ema_crossed_up, ema_crossed_down,
)
from config import EMA_EQUAL_TOLERANCE_PCT


def _round(value, digits=4):
    return None if value is None else round(float(value), digits)


def score_symbol(symbol, candles):
    if not candles or len(candles) < 61:
        return None
    # Ignore the currently-forming Binance candle.
    candles = candles[:-1]
    if len(candles) < 60:
        return None
    closes = [float(c["close"]) for c in candles]
    volumes = [float(c["volume"]) for c in candles]
    current = closes[-1]

    rsi = compute_rsi(closes, 14)
    ema20_series = compute_ema_series(closes, 20)
    ema50_series = compute_ema_series(closes, 50)
    ema20, ema50 = ema20_series[-1], ema50_series[-1]
    prev_ema20, prev_ema50 = ema20_series[-2], ema50_series[-2]
    macd_line, signal_line, histogram = compute_macd(closes)
    atr = compute_atr(candles, 14)
    volume_ratio = compute_volume_ratio(volumes, 20)
    support, resistance = compute_support_resistance(candles, 20)
    required = [rsi, ema20, ema50, macd_line, signal_line, histogram, atr, volume_ratio, support, resistance]
    if any(v is None for v in required):
        return None

    ema_state, ema_gap_pct = ema_relationship(ema20, ema50, EMA_EQUAL_TOLERANCE_PCT)
    ema_equal = ema_state == "EQUAL"
    ema_cross_up = ema_crossed_up(ema20_series, ema50_series)
    ema_cross_down = ema_crossed_down(ema20_series, ema50_series)
    prev_ema_bearish = prev_ema20 < prev_ema50
    ema_convergence_from_below = prev_ema_bearish and ema_equal
    prev_close = closes[-2]
    bullish_candle = candles[-1]["close"] >= candles[-1]["open"]
    near_support = current > support and (current - support) / current <= 0.015 if current else False
    near_ema20 = abs(current - ema20) / current <= 0.015 if current else False

    score = 0
    reasons = []
    if current > ema20:
        score += 10; reasons.append("Price above EMA20")
    if ema20 > ema50:
        score += 10; reasons.append("EMA20 above EMA50")
    if current > ema50:
        score += 5; reasons.append("Price above EMA50")

    if 50 <= rsi <= 70:
        score += 15; reasons.append(f"RSI constructive ({rsi:.1f})")
    elif 45 <= rsi < 50:
        score += 8; reasons.append(f"RSI recovering ({rsi:.1f})")
    elif 70 < rsi <= 75:
        score += 7; reasons.append(f"RSI strong but extended ({rsi:.1f})")

    if macd_line > signal_line:
        score += 10; reasons.append("MACD above signal")
    if histogram > 0:
        score += 5; reasons.append("MACD histogram positive")

    if volume_ratio >= 1.5:
        score += 15; reasons.append(f"Volume elevated ({volume_ratio:.2f}x)")
    elif volume_ratio >= 1.2:
        score += 10; reasons.append(f"Volume above average ({volume_ratio:.2f}x)")
    elif volume_ratio >= 1.0:
        score += 5; reasons.append(f"Volume at/above average ({volume_ratio:.2f}x)")

    breakout = current > resistance and prev_close <= resistance
    if breakout:
        score += 20; reasons.append("Closed above recent resistance")
    else:
        distance = (resistance - current) / resistance if resistance else 1
        if distance <= .01:
            score += 15; reasons.append("Price within 1% of resistance")
        elif distance <= .03:
            score += 10; reasons.append("Price within 3% of resistance")
        elif distance <= .05:
            score += 5; reasons.append("Price within 5% of resistance")

    if ema_equal:
        reasons.append(f"EMA20 ≈ EMA50 (gap {ema_gap_pct:.3f}%)")
    if ema_cross_up:
        reasons.append("EMA20 crossed above EMA50")
    if ema_cross_down:
        reasons.append("EMA20 crossed below EMA50")
    if ema_convergence_from_below:
        reasons.append(f"EMA20 reached EMA50 from below (gap {ema_gap_pct:.3f}%)")

    if near_support:
        reasons.append("Price is near recent support")
    if near_ema20:
        reasons.append("Price is near EMA20")

    # Setup classification. These are labels for market structure, not trade instructions.
    if breakout and volume_ratio >= 1.2 and ema20 > ema50 and macd_line > signal_line:
        setup_type = "BREAKOUT"
    elif ema_cross_up and rsi >= 50 and volume_ratio >= 1.2:
        setup_type = "REVERSAL"
    elif score >= 70 and macd_line > signal_line and current > ema20 and volume_ratio >= 1.2:
        setup_type = "MOMENTUM"
    elif ema20 > ema50 and near_support and bullish_candle and rsi >= 45:
        setup_type = "SUPPORT_BOUNCE"
    elif ema20 > ema50 and near_ema20 and current >= ema50 and rsi >= 45:
        setup_type = "PULLBACK"
    elif score >= 55 and current > ema20 and ema20 > ema50:
        setup_type = "TREND"
    elif score >= 40:
        setup_type = "WATCH"
    else:
        setup_type = "NOSETUP"

    score = max(0, min(100, int(round(score))))
    return {
        "symbol": symbol, "price": _round(current, 8), "score": score, "setup_type": setup_type,
        "ema_equal": ema_equal, "ema_cross_up": ema_cross_up, "ema_cross_down": ema_cross_down,
        "ema_convergence_from_below": ema_convergence_from_below,
        "reasons": reasons or ["No strong bullish condition detected"],
        "indicators": {
            "rsi": _round(rsi, 2), "ema20": _round(ema20, 8), "ema50": _round(ema50, 8),
            "ema_gap_pct": _round(ema_gap_pct, 4), "macd": _round(macd_line, 8),
            "macd_signal": _round(signal_line, 8), "macd_histogram": _round(histogram, 8),
            "atr": _round(atr, 8), "volume_ratio": _round(volume_ratio, 2),
            "support": _round(support, 8), "resistance": _round(resistance, 8),
        },
    }
