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



def _build_analysis(current, score, setup_type, rsi, ema20, ema50, macd_line,
                    macd_signal, volume_ratio, atr, support, resistance):
    """Build a deterministic analyst-style explanation from scanner data.
    This is not an AI prediction and does not claim statistical win rates.
    """
    bullish_structure = ema20 > ema50 and current > ema50
    momentum_ok = macd_line > macd_signal and rsi >= 45
    near_support = support > 0 and abs(current - support) / current <= 0.02
    resistance_gap = (resistance - current) / current if current else 1

    # Informational long setup levels. They are scenario levels, not orders.
    if bullish_structure:
        entry_low = max(0.0, min(current, support if near_support else current - 0.5 * atr))
        entry_high = current + 0.15 * atr
        invalidation = min(support - 0.3 * atr, entry_low - 0.3 * atr)
        if invalidation <= 0:
            invalidation = max(0.0, current - 1.5 * atr)
        risk = max(entry_high - invalidation, 1e-12)
        tp1 = resistance if resistance > entry_high else entry_high + 1.5 * risk
        tp2 = max(tp1 + 0.75 * risk, entry_high + 3 * atr)
        tp3 = max(tp2 + 0.75 * risk, entry_high + 5 * atr)
        rr1 = (tp1 - entry_high) / risk
        rr2 = (tp2 - entry_high) / risk
        rr3 = (tp3 - entry_high) / risk
    else:
        entry_low = entry_high = current
        invalidation = max(0.0, current - 1.5 * atr)
        risk = max(current - invalidation, 1e-12)
        tp1 = tp2 = tp3 = current
        rr1 = rr2 = rr3 = 0.0

    if score >= 85 and bullish_structure and momentum_ok and volume_ratio >= 1.2:
        confidence = "High"
    elif score >= 70 and bullish_structure and momentum_ok:
        confidence = "Medium"
    else:
        confidence = "Low"

    if setup_type in {"PULLBACK", "SUPPORT_BOUNCE"}:
        historical = "[Qualitative] Pullbacks/support bounces inside an established bullish structure can resume when momentum and participation recover."
    elif setup_type == "BREAKOUT":
        historical = "[Qualitative] Breakouts can continue when the level is reclaimed with participation; failed breakouts can quickly return to the prior range."
    elif setup_type == "REVERSAL":
        historical = "[Qualitative] Early reversals can develop after momentum recovery, but they remain vulnerable until market structure confirms the change."
    else:
        historical = "[Qualitative] Trend/momentum setups can continue while structure remains intact; weakening momentum or a support break can invalidate the scenario."

    if resistance_gap <= 0.015:
        counter = "Nearby resistance may limit upside and weaken the risk/reward."
    elif not bullish_structure:
        counter = "The EMA structure is not fully bullish, so continuation remains unconfirmed."
    elif volume_ratio < 1.2:
        counter = "Volume is not strongly above average, reducing participation confirmation."
    else:
        counter = "A failed momentum recovery or loss of the nearby support area would weaken the setup."

    rr_rule = rr1 >= 1.5
    bias = "LONG" if bullish_structure and momentum_ok and rr_rule and setup_type not in {"WATCH", "NOSETUP"} else "NO TRADE"
    return {
        "bias": bias,
        "setup": setup_type,
        "entry": {"low": round(entry_low, 8), "high": round(entry_high, 8)},
        "sl": round(invalidation, 8),
        "tp": [
            {"level": round(tp1, 8), "rr": round(rr1, 2), "reason": "Nearest meaningful resistance / first measured objective"},
            {"level": round(tp2, 8), "rr": round(rr2, 2), "reason": "Next expansion objective using volatility/structure"},
            {"level": round(tp3, 8), "rr": round(rr3, 2), "reason": "Extended objective; requires continued momentum"},
        ],
        "historical": historical,
        "invalidation": f"Scenario invalid if price closes below the support/invalidation area near {_round(invalidation, 8)}.",
        "counter_argument": counter,
        "confidence": confidence,
        "rr_tp1": round(rr1, 2),
        "rule_passed": rr_rule,
    }


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
    analysis = _build_analysis(current, score, setup_type, rsi, ema20, ema50, macd_line, signal_line, volume_ratio, atr, support, resistance)
    return {
        "symbol": symbol, "price": _round(current, 8), "score": score, "setup_type": setup_type,
        "ema_equal": ema_equal, "ema_cross_up": ema_cross_up, "ema_cross_down": ema_cross_down,
        "ema_convergence_from_below": ema_convergence_from_below,
        "reasons": reasons or ["No strong bullish condition detected"],
        "analysis": analysis,
        "indicators": {
            "rsi": _round(rsi, 2), "ema20": _round(ema20, 8), "ema50": _round(ema50, 8),
            "ema_gap_pct": _round(ema_gap_pct, 4), "macd": _round(macd_line, 8),
            "macd_signal": _round(signal_line, 8), "macd_histogram": _round(histogram, 8),
            "atr": _round(atr, 8), "volume_ratio": _round(volume_ratio, 2),
            "support": _round(support, 8), "resistance": _round(resistance, 8),
        },
    }
