"""
Transparent Setup Score engine for the Halal Crypto Scanner.

The repository referenced ``setup_score.score_symbol`` but did not contain
setup_score.py. This module supplies that missing interface using only the
indicator functions already present in indicators_engine.py.

The score is a technical screening score (0-100), not a probability of profit
and not a trading instruction.
"""

from indicators_engine import (
    compute_atr,
    compute_ema,
    compute_macd,
    compute_rsi,
    compute_support_resistance,
    compute_volume_ratio,
)


def _round(value, digits=4):
    if value is None:
        return None
    return round(float(value), digits)


def score_symbol(symbol, candles):
    """Return one dashboard-compatible score record for a symbol."""
    if not candles or len(candles) < 61:
        return None

    # Binance includes the currently forming candle. For an automated scanner,
    # use only completed candles so a signal does not appear/disappear while
    # the candle is still moving.
    candles = candles[:-1]
    closes = [float(c["close"]) for c in candles]
    volumes = [float(c["volume"]) for c in candles]
    current = closes[-1]

    rsi = compute_rsi(closes, 14)
    ema20 = compute_ema(closes, 20)
    ema50 = compute_ema(closes, 50)
    macd_line, signal_line, histogram = compute_macd(closes)
    atr = compute_atr(candles, 14)
    volume_ratio = compute_volume_ratio(volumes, 20)
    support, resistance = compute_support_resistance(candles, 20)

    required = [
        rsi, ema20, ema50, macd_line, signal_line, histogram,
        atr, volume_ratio, support, resistance,
    ]
    if any(value is None for value in required):
        return None

    score = 0
    reasons = []

    # Trend: 25 points.
    if current > ema20:
        score += 10
        reasons.append("Price above EMA20")
    if ema20 > ema50:
        score += 10
        reasons.append("EMA20 above EMA50")
    if current > ema50:
        score += 5
        reasons.append("Price above EMA50")

    # Momentum: 30 points.
    if 50 <= rsi <= 70:
        score += 15
        reasons.append(f"RSI constructive ({rsi:.1f})")
    elif 45 <= rsi < 50:
        score += 8
        reasons.append(f"RSI recovering ({rsi:.1f})")
    elif 70 < rsi <= 75:
        score += 7
        reasons.append(f"RSI strong but extended ({rsi:.1f})")

    if macd_line > signal_line:
        score += 10
        reasons.append("MACD above signal")
    if histogram > 0:
        score += 5
        reasons.append("MACD histogram positive")

    # Participation: 15 points.
    if volume_ratio >= 1.5:
        score += 15
        reasons.append(f"Volume elevated ({volume_ratio:.2f}x)")
    elif volume_ratio >= 1.2:
        score += 10
        reasons.append(f"Volume above average ({volume_ratio:.2f}x)")
    elif volume_ratio >= 1.0:
        score += 5
        reasons.append(f"Volume at/above average ({volume_ratio:.2f}x)")

    # Breakout proximity / confirmation: 20 points.
    if current > resistance:
        score += 20
        reasons.append("Price broke recent resistance")
    else:
        distance = (resistance - current) / resistance if resistance else 1.0
        if distance <= 0.01:
            score += 15
            reasons.append("Price within 1% of resistance")
        elif distance <= 0.03:
            score += 10
            reasons.append("Price within 3% of resistance")
        elif distance <= 0.05:
            score += 5
            reasons.append("Price within 5% of resistance")

    score = max(0, min(100, int(round(score))))

    if current > resistance and volume_ratio >= 1.2 and score >= 70:
        setup_type = "BREAKOUT"
    elif score >= 70 and macd_line > signal_line and current > ema20:
        setup_type = "MOMENTUM"
    elif score >= 55 and current > ema20 and ema20 > ema50:
        setup_type = "TREND"
    elif score >= 40:
        setup_type = "WATCH"
    else:
        setup_type = "NOSETUP"

    if not reasons:
        reasons.append("No strong bullish condition detected")

    return {
        "symbol": symbol,
        "price": _round(current, 8),
        "score": score,
        "setup_type": setup_type,
        "reasons": reasons,
        "indicators": {
            "rsi": _round(rsi, 2),
            "ema20": _round(ema20, 8),
            "ema50": _round(ema50, 8),
            "macd": _round(macd_line, 8),
            "macd_signal": _round(signal_line, 8),
            "macd_histogram": _round(histogram, 8),
            "atr": _round(atr, 8),
            "volume_ratio": _round(volume_ratio, 2),
            "support": _round(support, 8),
            "resistance": _round(resistance, 8),
        },
    }
