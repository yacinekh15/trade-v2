"""
Indicator math for the Setup Score engine. No external TA library —
plain calculations over OHLCV data so every number is auditable.

Each candle is a dict: {open_time, open, high, low, close, volume}
"""


def compute_rsi(closes, period=14):
    if len(closes) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(closes)):
        change = closes[i] - closes[i - 1]
        gains.append(max(change, 0))
        losses.append(max(-change, 0))
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def compute_ema_series(values, period):
    """Returns the full EMA series (same length as values, first `period-1` are None)."""
    if len(values) < period:
        return [None] * len(values)
    multiplier = 2 / (period + 1)
    series = [None] * (period - 1)
    sma = sum(values[:period]) / period
    series.append(sma)
    prev = sma
    for v in values[period:]:
        prev = (v - prev) * multiplier + prev
        series.append(prev)
    return series


def compute_ema(values, period):
    series = compute_ema_series(values, period)
    return series[-1] if series else None


def compute_macd(closes, fast=12, slow=26, signal=9):
    """Returns (macd_line, signal_line, histogram) for the latest candle, or Nones."""
    if len(closes) < slow + signal:
        return None, None, None
    ema_fast = compute_ema_series(closes, fast)
    ema_slow = compute_ema_series(closes, slow)
    macd_series = [
        (f - s) if (f is not None and s is not None) else None
        for f, s in zip(ema_fast, ema_slow)
    ]
    valid_macd = [m for m in macd_series if m is not None]
    signal_series = compute_ema_series(valid_macd, signal)
    macd_line = valid_macd[-1]
    signal_line = signal_series[-1]
    if signal_line is None:
        return macd_line, None, None
    return macd_line, signal_line, macd_line - signal_line


def compute_atr(candles, period=14):
    """Average True Range — a volatility measure, not a directional signal."""
    if len(candles) < period + 1:
        return None
    trs = []
    for i in range(1, len(candles)):
        high, low = candles[i]["high"], candles[i]["low"]
        prev_close = candles[i - 1]["close"]
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        trs.append(tr)
    atr = sum(trs[:period]) / period
    for tr in trs[period:]:
        atr = (atr * (period - 1) + tr) / period
    return atr


def compute_volume_ratio(volumes, lookback=20):
    if len(volumes) < lookback + 1:
        return None
    current = volumes[-1]
    baseline = volumes[-(lookback + 1):-1]
    avg = sum(baseline) / len(baseline)
    if avg == 0:
        return None
    return current / avg


def compute_support_resistance(candles, lookback=20):
    """Recent resistance = highest high, support = lowest low, EXCLUDING the current candle."""
    if len(candles) < lookback + 1:
        return None, None
    window = candles[-(lookback + 1):-1]
    resistance = max(c["high"] for c in window)
    support = min(c["low"] for c in window)
    return support, resistance


def ema_relationship(ema20, ema50, tolerance_pct=0.05):
    """Classify EMA20 vs EMA50; near-equal uses a configurable percentage band."""
    if ema20 is None or ema50 in (None, 0):
        return "UNKNOWN", None
    gap_pct = abs(ema20 - ema50) / abs(ema50) * 100
    if gap_pct <= tolerance_pct:
        return "EQUAL", gap_pct
    return ("BULLISH" if ema20 > ema50 else "BEARISH"), gap_pct


def ema_crossed_up(series20, series50):
    """True when EMA20 crossed from <= EMA50 to > EMA50 on the latest candle."""
    if len(series20) < 2 or len(series50) < 2:
        return False
    a0, b0 = series20[-2], series50[-2]
    a1, b1 = series20[-1], series50[-1]
    return None not in (a0, b0, a1, b1) and a0 <= b0 and a1 > b1


def ema_crossed_down(series20, series50):
    if len(series20) < 2 or len(series50) < 2:
        return False
    a0, b0 = series20[-2], series50[-2]
    a1, b1 = series20[-1], series50[-1]
    return None not in (a0, b0, a1, b1) and a0 >= b0 and a1 < b1
