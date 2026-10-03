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


def compute_rma_series(values, period):
    """TradingView ta.rma-style Wilder moving average (SMA seed, alpha=1/period)."""
    out = [None] * len(values)
    if len(values) < period:
        return out
    prev = sum(values[:period]) / period
    out[period - 1] = prev
    alpha = 1.0 / period
    for i in range(period, len(values)):
        prev = alpha * values[i] + (1.0 - alpha) * prev
        out[i] = prev
    return out


def compute_trend_speed_analyzer(candles, max_length=50, accel_multiplier=5.0):
    """Reproduce the core bullish/bearish state of Zeiierman's Trend Speed Analyzer.

    The public script uses close as counts_diff, an adaptive EMA, WMA(close, 2)
    for the dynamic-trend color, and an RMA(10) based cumulative trend speed.
    """
    closes = [float(c["close"]) for c in candles]
    opens = [float(c["open"]) for c in candles]
    n = len(closes)
    if n == 0:
        return None

    # Pine ta.highest(abs(close), 200), with the available-history behavior.
    dyn = [None] * n
    deltas = [None] * n
    for i in range(n):
        start = max(0, i - 199)
        max_abs = max(abs(x) for x in closes[start:i + 1])
        max_abs = max_abs if max_abs != 0 else 1.0
        norm = (closes[i] + max_abs) / (2.0 * max_abs)
        dyn_length = 5.0 + norm * (max_length - 5.0)
        if i == 0:
            delta = 0.0
        else:
            delta = abs(closes[i] - closes[i - 1])
        deltas[i] = delta
        dstart = max(0, i - 199)
        max_delta = max(deltas[dstart:i + 1]) or 1.0
        accel_factor = delta / max_delta
        alpha_base = 2.0 / (dyn_length + 1.0)
        alpha = min(1.0, alpha_base * (1.0 + accel_factor * accel_multiplier))
        dyn[i] = closes[i] if i == 0 else alpha * closes[i] + (1.0 - alpha) * dyn[i - 1]

    rma_close = compute_rma_series(closes, 10)
    rma_open = compute_rma_series(opens, 10)
    speed = [None] * n
    pos = 0
    running = 0.0
    # The Pine script resets speed on a trend-direction crossover and then
    # accumulates c-o each bar.
    wma2 = [None] * n
    for i in range(n):
        wma2[i] = closes[i] if i == 0 else (2.0 * closes[i] + closes[i - 1]) / 3.0
        if rma_close[i] is None or rma_open[i] is None:
            speed[i] = None
            continue
        if i > 0:
            bullish_cross = closes[i] > dyn[i] and closes[i - 1] <= dyn[i - 1]
            bearish_cross = closes[i] < dyn[i] and closes[i - 1] >= dyn[i - 1]
            if bullish_cross:
                pos = 1
                running = rma_close[i] - rma_open[i]
            elif bearish_cross:
                pos = -1
                running = rma_close[i] - rma_open[i]
            else:
                running += rma_close[i] - rma_open[i]
        else:
            running = rma_close[i] - rma_open[i]
        speed[i] = running

    i = n - 1
    trend_green = wma2[i] > dyn[i]
    speed_green = speed[i] is not None and speed[i] > 0
    return {
        "dynamic_ema": dyn[i],
        "wma2": wma2[i],
        "trend_green": trend_green,
        "trend_speed": speed[i],
        "speed_green": speed_green,
        "green": trend_green and speed_green,
    }


def compute_adaptive_expansion(candles, ma_type="EMA", ma_length=20, atr_length=14, mult1=1.0):
    """Reproduce the bullish state of BigBeluga Adaptive Trend Expansion Bands."""
    closes = [float(c["close"]) for c in candles]
    highs = [float(c["high"]) for c in candles]
    lows = [float(c["low"]) for c in candles]
    n = len(closes)
    if n == 0:
        return None

    if ma_type == "SMA":
        base = [None] * n
        for i in range(ma_length - 1, n):
            base[i] = sum(closes[i - ma_length + 1:i + 1]) / ma_length
    elif ma_type == "WMA":
        base = [None] * n
        denom = ma_length * (ma_length + 1) / 2
        for i in range(ma_length - 1, n):
            vals = closes[i - ma_length + 1:i + 1]
            base[i] = sum(v * (j + 1) for j, v in enumerate(vals)) / denom
    elif ma_type == "HMA":
        # HMA is not the default, but keep the setting faithful enough for UI experimentation.
        def wma(vals):
            m = len(vals); d = m * (m + 1) / 2
            return sum(v * (j + 1) for j, v in enumerate(vals)) / d
        half = max(1, ma_length // 2); root = max(1, int(ma_length ** 0.5))
        raw = [None] * n
        for j in range(n):
            if j >= ma_length - 1:
                raw[j] = 2 * wma(closes[j-half+1:j+1]) - wma(closes[j-ma_length+1:j+1])
        base = [None] * n
        for j in range(root - 1, n):
            vals = [x for x in raw[j-root+1:j+1] if x is not None]
            if len(vals) == root:
                base[j] = wma(vals)
    else:
        base = compute_ema_series(closes, ma_length)

    atr = compute_atr_series(candles, atr_length)
    u3 = [None] * n; l3 = [None] * n
    for i in range(n):
        if base[i] is not None and atr[i] is not None:
            mult3 = mult1 + 1.0
            u3[i] = base[i] + atr[i] * mult3
            l3[i] = base[i] - atr[i] * mult3

    trend = 0
    flipped_bull = False
    flipped_bear = False
    for i in range(n):
        if i == 0 or u3[i] is None or l3[i] is None or u3[i-1] is None or l3[i-1] is None:
            continue
        if closes[i] > u3[i] and closes[i-1] <= u3[i-1]:
            trend = 1
        if closes[i] < l3[i] and closes[i-1] >= l3[i-1]:
            trend = -1
    if n >= 2 and u3[-1] is not None and u3[-2] is not None and l3[-1] is not None and l3[-2] is not None:
        flipped_bull = closes[-1] > u3[-1] and closes[-2] <= u3[-2]
        flipped_bear = closes[-1] < l3[-1] and closes[-2] >= l3[-2]
    return {
        "base_ma": base[-1],
        "atr": atr[-1],
        "upper_zone3": u3[-1],
        "lower_zone3": l3[-1],
        "trend": trend,
        "green": trend == 1,
        "flipped_bullish": flipped_bull,
        "flipped_bearish": flipped_bear,
    }
