"""Deterministic entry-quality engine for the Halal Crypto Scanner.

The engine is intentionally selective.  A score is rule alignment, not a
probability of profit.  It is designed to find relatively low-risk spot-entry
locations inside bullish structure rather than simply rank strong coins.
"""
from indicators_engine import (
    compute_atr, compute_ema_series, compute_macd, compute_rsi,
    compute_support_resistance, compute_volume_ratio, ema_relationship,
    ema_crossed_up, ema_crossed_down,
)
from config import EMA_EQUAL_TOLERANCE_PCT


TRADE_SETUPS = {"PULLBACK", "SUPPORT_BOUNCE", "BREAKOUT_RETEST", "EMA200_MACD"}
WATCH_SETUPS = {"REVERSAL", "COMPRESSION", "EMA_CONVERGENCE", "OVEREXTENDED", "NOSETUP"}


def _round(value, digits=4):
    return None if value is None else round(float(value), digits)


def _pct(a, b):
    return abs(a - b) / abs(b) * 100 if b else 999.0


def _near(price, level, atr, atr_mult=1.25, pct=0.02):
    if level is None or price <= 0:
        return False
    return abs(price - level) <= max(atr * atr_mult, price * pct)


def _ema200_slope_pct(series, bars=8):
    valid = [x for x in series if x is not None]
    if len(valid) <= bars or valid[-1] == 0:
        return 0.0
    return (valid[-1] - valid[-1-bars]) / valid[-1-bars] * 100


def _recent_recovery(closes, candles, macd_hist, prev_hist, rsi, prev_rsi):
    bullish = candles[-1]["close"] >= candles[-1]["open"]
    return bullish and closes[-1] > closes[-2] and macd_hist >= prev_hist and rsi >= prev_rsi


def _find_breakout_retest(candles, current, atr):
    """Detect a recent close above prior resistance followed by a retest hold."""
    if len(candles) < 35:
        return False, None
    # Use a resistance level built before the last 3 candles, then look for a
    # breakout in the last five closed candles and a current retest/hold.
    base = candles[:-5]
    if len(base) < 20:
        return False, None
    level = max(c["high"] for c in base[-20:])
    breakout_index = None
    for i in range(len(candles)-5, len(candles)-1):
        prev = candles[i-1]["close"]
        close = candles[i]["close"]
        if close > level and prev <= level:
            breakout_index = i
    if breakout_index is None:
        return False, level
    current_c = candles[-1]
    retest = current_c["low"] <= level + max(0.35 * atr, level * 0.003)
    hold = current >= level
    return bool(retest and hold), level


def _build_levels(setup_type, current, atr, support, resistance, ema20, ema50,
                  breakout_level=None):
    """Build scenario levels from market structure first, then volatility."""
    atr = max(float(atr), current * 0.001)
    if setup_type == "SUPPORT_BOUNCE":
        zone = support
        entry_low = max(zone - 0.35 * atr, 0.0)
        entry_high = max(current, zone + 0.25 * atr)
        sl = max(zone - 1.0 * atr, 0.0)
    elif setup_type == "PULLBACK":
        zone = ema20 if _near(current, ema20, atr, 1.25, 0.018) else support
        entry_low = max(min(current, zone) - 0.15 * atr, 0.0)
        entry_high = max(current, zone + 0.20 * atr)
        sl = max(min(support - 0.45 * atr, zone - 0.65 * atr), 0.0)
    elif setup_type == "BREAKOUT_RETEST":
        zone = breakout_level or resistance
        entry_low = max(zone - 0.20 * atr, 0.0)
        entry_high = zone + 0.35 * atr
        sl = max(zone - 0.95 * atr, 0.0)
    else:  # EMA200_MACD
        zone = ema20 if _near(current, ema20, atr, 1.35, 0.02) else ema50
        entry_low = max(min(current, zone) - 0.15 * atr, 0.0)
        entry_high = max(current, zone + 0.25 * atr)
        sl = max(min(support - 0.35 * atr, zone - 0.8 * atr), 0.0)

    # Never put the stop above the bottom of the entry zone.
    sl = min(sl, entry_low - 0.05 * atr)
    if sl <= 0:
        sl = max(current - 1.5 * atr, current * 0.5)
    risk = max(entry_high - sl, 1e-12)

    # Resistance is a real market target only when it is above entry.  If it is
    # too close, the setup is rejected rather than manufacturing a target.
    candidates = [x for x in (resistance, current + 2 * atr, current + 3 * atr) if x and x > entry_high]
    tp1 = min(candidates) if candidates else entry_high + 2 * atr
    tp2 = max(entry_high + 3 * atr, tp1 + 0.75 * risk)
    tp3 = max(entry_high + 5 * atr, tp2 + 0.75 * risk)
    return entry_low, entry_high, sl, tp1, tp2, tp3


def _build_analysis(current, score, setup_type, rsi, ema20, ema50, ema200,
                    macd_line, macd_signal, volume_ratio, atr, support,
                    resistance, levels, entry_quality, rejection_reasons):
    entry_low, entry_high, sl, tp1, tp2, tp3 = levels
    risk = max(entry_high - sl, 1e-12)
    rr1 = (tp1 - entry_high) / risk
    rr2 = (tp2 - entry_high) / risk
    rr3 = (tp3 - entry_high) / risk
    qualified = setup_type in TRADE_SETUPS and entry_quality >= 75 and rr1 >= 1.5 and not rejection_reasons
    bias = "LONG" if qualified else "NO TRADE"
    if qualified and score >= 88:
        confidence = "High"
    elif qualified and score >= 80:
        confidence = "Medium"
    else:
        confidence = "Low"

    historical = {
        "PULLBACK": "[Qualitative] Pullbacks within an established trend can resume after support and momentum recover; they can also fail if the correction becomes a trend change.",
        "SUPPORT_BOUNCE": "[Qualitative] Support reactions can produce continuation when buyers defend the level, but repeated tests can weaken support.",
        "BREAKOUT_RETEST": "[Qualitative] A breakout followed by a successful retest can act as continuation structure; failed retests can return price to the prior range.",
        "EMA200_MACD": "[Qualitative] Long-term trend filters combined with MACD confirmation can align entries with established trends; flat EMA200 conditions are less informative.",
        "REVERSAL": "[Qualitative] Early reversals can develop after momentum recovery, but require structural confirmation.",
        "COMPRESSION": "[Qualitative] Compression can precede expansion in either direction; direction and confirmation matter.",
        "EMA_CONVERGENCE": "[Qualitative] EMA convergence is a transition state, not by itself a directional entry signal.",
        "OVEREXTENDED": "[Qualitative] Extended moves can continue, but fresh entries become more vulnerable to mean reversion and poor location.",
    }.get(setup_type, "[Qualitative] No validated entry pattern is present.")

    if rejection_reasons:
        counter = " / ".join(rejection_reasons[:2])
    elif resistance <= entry_high * 1.015:
        counter = "Nearby resistance leaves limited room for the first target."
    elif volume_ratio < 1.2:
        counter = "Participation is not strongly above average."
    else:
        counter = "The setup can fail if support/invalidation breaks or momentum fades."

    return {
        "bias": bias,
        "setup": setup_type,
        "qualified": qualified,
        "entry_quality": entry_quality,
        "entry": {"low": _round(entry_low, 8), "high": _round(entry_high, 8)},
        "sl": _round(sl, 8),
        "tp": [
            {"level": _round(tp1, 8), "rr": _round(rr1, 2), "reason": "Nearest usable structural/volatility objective"},
            {"level": _round(tp2, 8), "rr": _round(rr2, 2), "reason": "Next expansion objective"},
            {"level": _round(tp3, 8), "rr": _round(rr3, 2), "reason": "Extended objective; requires continued momentum"},
        ],
        "historical": historical,
        "invalidation": f"Scenario invalid if price closes below the invalidation area near {_round(sl, 8)}.",
        "counter_argument": counter,
        "confidence": confidence,
        "rr_tp1": _round(rr1, 2),
        "rule_passed": bool(qualified),
        "rejection_reasons": rejection_reasons,
    }


def score_symbol(symbol, candles):
    # EMA200 plus structure needs a meaningful warm-up. The caller normally
    # supplies 220 candles; the forming candle is removed below.
    if not candles or len(candles) < 205:
        return None
    candles = candles[:-1]  # never score an open candle
    if len(candles) < 204:
        return None

    closes = [float(c["close"]) for c in candles]
    volumes = [float(c["volume"]) for c in candles]
    current = closes[-1]
    prev_close = closes[-2]

    rsi_series = []
    for i in range(15, len(closes) + 1):
        rsi_series.append(compute_rsi(closes[:i], 14))
    rsi = rsi_series[-1]
    prev_rsi = rsi_series[-2]
    ema20_series = compute_ema_series(closes, 20)
    ema50_series = compute_ema_series(closes, 50)
    ema200_series = compute_ema_series(closes, 200)
    ema20, ema50, ema200 = ema20_series[-1], ema50_series[-1], ema200_series[-1]
    prev_ema20, prev_ema50 = ema20_series[-2], ema50_series[-2]
    macd_line, signal_line, histogram = compute_macd(closes)
    prev_macd_line, prev_signal_line, prev_hist = compute_macd(closes[:-1])
    atr = compute_atr(candles, 14)
    volume_ratio = compute_volume_ratio(volumes, 20)
    support, resistance = compute_support_resistance(candles, 30)
    required = [rsi, prev_rsi, ema20, ema50, ema200, macd_line, signal_line,
                histogram, prev_macd_line, prev_signal_line, prev_hist, atr,
                volume_ratio, support, resistance]
    if any(v is None for v in required):
        return None

    ema_state, ema_gap_pct = ema_relationship(ema20, ema50, EMA_EQUAL_TOLERANCE_PCT)
    ema_equal = ema_state == "EQUAL"
    ema_cross_up = ema_crossed_up(ema20_series, ema50_series)
    ema_cross_down = ema_crossed_down(ema20_series, ema50_series)
    ema200_slope = _ema200_slope_pct(ema200_series, 8)
    ema200_rising = ema200_slope > 0.03
    price_above_200 = current > ema200
    price_above_50 = current > ema50
    bullish_structure = current > ema50 and ema20 > ema50 and price_above_200
    macd_cross_up = prev_macd_line <= prev_signal_line and macd_line > signal_line
    hist_improving = histogram >= prev_hist
    rsi_recovering = rsi >= prev_rsi
    recovery = _recent_recovery(closes, candles, histogram, prev_hist, rsi, prev_rsi)
    bullish_candle = candles[-1]["close"] >= candles[-1]["open"]
    near_support = _near(current, support, atr, 1.15, 0.012)
    near_ema20 = _near(current, ema20, atr, 1.15, 0.015)
    near_ema50 = _near(current, ema50, atr, 1.25, 0.02)
    breakout_retest, breakout_level = _find_breakout_retest(candles, current, atr)

    # Pullback: price must have come down from a recent impulse high while the
    # larger structure remains bullish and the current candle shows recovery.
    prior_high = max(c["high"] for c in candles[-31:-3])
    prior_low = min(c["low"] for c in candles[-31:-3])
    impulse_range = max(prior_high - prior_low, atr)
    retracement = (prior_high - current) / impulse_range
    valid_pullback_depth = 0.20 <= retracement <= 0.65
    pullback = bullish_structure and valid_pullback_depth and (near_ema20 or near_ema50 or near_support) and recovery

    support_bounce = bullish_structure and near_support and bullish_candle and recovery and rsi >= 45

    ema200_macd = (price_above_200 and ema200_rising and ema20 > ema50 and
                   (macd_cross_up or (macd_line > signal_line and hist_improving)) and
                   rsi >= 45 and volume_ratio >= 1.05 and (near_ema20 or near_ema50 or near_support))

    reversal = (ema_cross_up or (prev_ema20 <= prev_ema50 and ema20 > ema50)) and rsi_recovering and hist_improving
    compression = (atr / current < 0.025 and
                   (max(c["high"] for c in candles[-10:]) - min(c["low"] for c in candles[-10:])) / current < 0.06)
    overextended = ((current - ema20) / max(ema20, 1e-12) > 0.025 or
                    (current - ema20) > 1.8 * atr or rsi > 75)

    # Entry quality components. Location deliberately penalizes chasing
    # resistance and rewards a defined pullback/support/retest location.
    trend = 0
    if price_above_200: trend += 8
    if ema200_rising: trend += 5
    if ema20 > ema50: trend += 6
    if current > ema20: trend += 3
    if ema20_series[-1] > ema20_series[-6]: trend += 3
    trend = min(trend, 25)

    location = 0
    if near_support: location += 10
    if near_ema20: location += 7
    if near_ema50: location += 5
    if breakout_retest: location += 10
    resistance_room = (resistance - current) / current if current else -1
    if resistance_room > 0.05: location += 5
    elif resistance_room < 0.02 and not breakout_retest: location -= 10
    if overextended: location -= 10
    location = max(0, min(location, 25))

    momentum = 0
    if macd_line > signal_line: momentum += 7
    if histogram > 0: momentum += 4
    if hist_improving: momentum += 3
    if macd_cross_up: momentum += 4
    if 45 <= rsi <= 68: momentum += 2
    if rsi > 72: momentum -= 4
    momentum = max(0, min(momentum, 20))

    volume = 10 if volume_ratio >= 1.5 else 7 if volume_ratio >= 1.2 else 4 if volume_ratio >= 1.05 else 0
    structure = 5 if recovery else 2 if bullish_candle else 0

    # First classify the market state, then calculate risk/reward from it.
    if breakout_retest and volume_ratio >= 1.15 and bullish_structure:
        setup_type = "BREAKOUT_RETEST"
    elif overextended:
        setup_type = "OVEREXTENDED"
    elif support_bounce:
        setup_type = "SUPPORT_BOUNCE"
    elif pullback:
        setup_type = "PULLBACK"
    elif ema200_macd:
        setup_type = "EMA200_MACD"
    elif ema_cross_up and reversal:
        setup_type = "REVERSAL"
    elif ema_equal and prev_ema20 < prev_ema50:
        setup_type = "EMA_CONVERGENCE"
    elif compression:
        setup_type = "COMPRESSION"
    else:
        setup_type = "NOSETUP"

    levels = _build_levels(setup_type, current, atr, support, resistance, ema20, ema50, breakout_level)
    entry_low, entry_high, sl, tp1, tp2, tp3 = levels
    risk = max(entry_high - sl, 1e-12)
    rr1 = (tp1 - entry_high) / risk

    rejection_reasons = []
    if not bullish_structure and setup_type in TRADE_SETUPS:
        rejection_reasons.append("Higher trend structure is not fully bullish")
    if resistance_room < 0.015 and setup_type != "BREAKOUT_RETEST":
        rejection_reasons.append("Resistance is too close for a clean entry")
    if overextended and setup_type != "BREAKOUT_RETEST":
        rejection_reasons.append("Price is extended from its value/EMA area")
    if rr1 < 1.5:
        rejection_reasons.append("TP1 R:R is below 1.5")
    if volume_ratio < 1.05 and setup_type in {"PULLBACK", "SUPPORT_BOUNCE", "BREAKOUT_RETEST", "EMA200_MACD"}:
        rejection_reasons.append("Participation is too weak")

    risk_reward_points = 15 if rr1 >= 3 else 12 if rr1 >= 2 else 9 if rr1 >= 1.5 else 0
    score = max(0, min(100, int(round(trend + location + momentum + volume + structure + risk_reward_points))))
    entry_quality = max(0, min(100, int(round((trend / 25) * 28 + (location / 25) * 30 + (momentum / 20) * 20 + (volume / 10) * 10 + (structure / 5) * 5 + (risk_reward_points / 15) * 7))))

    reasons = []
    if price_above_200: reasons.append("Price above EMA200")
    if ema200_rising: reasons.append(f"EMA200 rising ({ema200_slope:.3f}%)")
    if ema20 > ema50: reasons.append("EMA20 above EMA50")
    if near_support: reasons.append("Price is near structural support")
    if near_ema20: reasons.append("Price is near EMA20 value area")
    if near_ema50: reasons.append("Price is near EMA50 value area")
    if breakout_retest: reasons.append("Recent breakout is being retested and held")
    if recovery: reasons.append("Price/momentum are recovering on the closed candle")
    if macd_cross_up: reasons.append("MACD bullish crossover")
    elif macd_line > signal_line and hist_improving: reasons.append("MACD momentum improving")
    if volume_ratio >= 1.2: reasons.append(f"Volume confirmation ({volume_ratio:.2f}x)")
    if resistance_room > 0.05: reasons.append("Adequate room to resistance")
    if overextended: reasons.append("Price is extended")
    if rr1 >= 1.5: reasons.append(f"TP1 R:R {rr1:.2f}")

    analysis = _build_analysis(
        current, score, setup_type, rsi, ema20, ema50, ema200,
        macd_line, signal_line, volume_ratio, atr, support, resistance,
        levels, entry_quality, rejection_reasons,
    )

    return {
        "symbol": symbol, "price": _round(current, 8), "score": score,
        "entry_quality": entry_quality, "qualified": bool(analysis["qualified"]),
        "setup_type": setup_type, "ema_equal": ema_equal,
        "ema_cross_up": ema_cross_up, "ema_cross_down": ema_cross_down,
        "ema_convergence_from_below": prev_ema20 < prev_ema50 and ema_equal,
        "ema200_bullish": price_above_200 and ema200_rising,
        "reasons": reasons or ["No qualified entry pattern detected"],
        "rejection_reasons": rejection_reasons,
        "analysis": analysis,
        "indicators": {
            "rsi": _round(rsi, 2), "rsi_prev": _round(prev_rsi, 2),
            "ema20": _round(ema20, 8), "ema50": _round(ema50, 8),
            "ema200": _round(ema200, 8), "ema200_slope_pct": _round(ema200_slope, 4),
            "ema_gap_pct": _round(ema_gap_pct, 4), "macd": _round(macd_line, 8),
            "macd_signal": _round(signal_line, 8), "macd_histogram": _round(histogram, 8),
            "atr": _round(atr, 8), "atr_pct": _round(atr/current*100, 3),
            "volume_ratio": _round(volume_ratio, 2), "support": _round(support, 8),
            "resistance": _round(resistance, 8), "ema200_rising": ema200_rising,
            "macd_cross_up": macd_cross_up, "recovery": recovery,
            "resistance_room_pct": _round(resistance_room*100, 3),
            "retracement_pct": _round(retracement*100, 2),
        },
    }
