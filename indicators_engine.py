"""Auditable indicator calculations for closed Binance Spot candles."""


def compute_rsi_series(closes, period=14):
    out = [None] * len(closes)
    if len(closes) <= period:
        return out
    gains = [0.0] * (len(closes) - 1)
    losses = [0.0] * (len(closes) - 1)
    for i in range(1, len(closes)):
        d = closes[i] - closes[i - 1]
        gains[i - 1] = max(d, 0.0)
        losses[i - 1] = max(-d, 0.0)
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    out[period] = 100.0 if avg_loss == 0 else 100 - 100 / (1 + avg_gain / avg_loss)
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        out[i + 1] = 100.0 if avg_loss == 0 else 100 - 100 / (1 + avg_gain / avg_loss)
    return out


def compute_rsi(closes, period=14):
    s = compute_rsi_series(closes, period)
    return s[-1] if s else None


def compute_ema_series(values, period):
    if len(values) < period:
        return [None] * len(values)
    out = [None] * (period - 1)
    prev = sum(values[:period]) / period
    out.append(prev)
    alpha = 2 / (period + 1)
    for value in values[period:]:
        prev = (value - prev) * alpha + prev
        out.append(prev)
    return out


def compute_ema(values, period):
    s = compute_ema_series(values, period)
    return s[-1] if s else None


def compute_macd_series(closes, fast=12, slow=26, signal=9):
    ef = compute_ema_series(closes, fast)
    es = compute_ema_series(closes, slow)
    macd = [None if f is None or s is None else f - s for f, s in zip(ef, es)]
    valid = [x for x in macd if x is not None]
    sig_valid = compute_ema_series(valid, signal)
    signal_full = [None] * len(macd)
    j = 0
    for i, x in enumerate(macd):
        if x is not None:
            signal_full[i] = sig_valid[j]
            j += 1
    hist = [None if a is None or b is None else a - b for a, b in zip(macd, signal_full)]
    return macd, signal_full, hist


def compute_macd(closes, fast=12, slow=26, signal=9):
    m, s, h = compute_macd_series(closes, fast, slow, signal)
    return m[-1], s[-1], h[-1]


def compute_atr_series(candles, period=14):
    out = [None] * len(candles)
    if len(candles) <= period:
        return out
    trs = [None]
    for i in range(1, len(candles)):
        c, p = candles[i], candles[i - 1]
        trs.append(max(c["high"] - c["low"], abs(c["high"] - p["close"]), abs(c["low"] - p["close"])))
    atr = sum(trs[1:period + 1]) / period
    out[period] = atr
    for i in range(period + 1, len(candles)):
        atr = (atr * (period - 1) + trs[i]) / period
        out[i] = atr
    return out


def compute_atr(candles, period=14):
    s = compute_atr_series(candles, period)
    return s[-1] if s else None


def compute_volume_ratio(volumes, lookback=20):
    if len(volumes) < lookback + 1:
        return None
    avg = sum(volumes[-lookback - 1:-1]) / lookback
    return None if avg == 0 else volumes[-1] / avg


def compute_support_resistance(candles, lookback=20):
    if len(candles) < lookback + 1:
        return None, None
    w = candles[-lookback - 1:-1]
    return min(c["low"] for c in w), max(c["high"] for c in w)


def ema_relationship(ema20, ema50, tolerance_pct=0.05):
    if ema20 is None or ema50 in (None, 0):
        return "UNKNOWN", None
    gap = abs(ema20 - ema50) / abs(ema50) * 100
    if gap <= tolerance_pct:
        return "EQUAL", gap
    return ("BULLISH" if ema20 > ema50 else "BEARISH"), gap


def ema_crossed_up(series20, series50):
    if len(series20) < 2 or len(series50) < 2:
        return False
    a0, b0, a1, b1 = series20[-2], series50[-2], series20[-1], series50[-1]
    return None not in (a0, b0, a1, b1) and a0 <= b0 and a1 > b1
