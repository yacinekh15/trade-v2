"""Descriptive KDRX-style context. Does not create, suppress, or rank signals."""

def build_kdrx_context(price, ema20, ema50, ema200, rsi, volume_ratio, support=None, resistance=None):
    def pct(a, b):
        return None if a is None or not b else (a - b) / b * 100.0
    gap50_200 = pct(ema50, ema200)
    price_vs_ema200 = pct(price, ema200)
    price_vs_ema20 = pct(price, ema20)
    support_distance = None if not support or not price else (price - support) / price * 100.0
    trend = bool(ema50 is not None and ema200 is not None and price is not None and ema50 > ema200 and price > ema50 and price > ema200)
    pullback = bool(price is not None and ema20 is not None and price <= ema20)
    moderate_rsi = bool(rsi is not None and 45 <= rsi <= 55)
    near_ema200 = bool(price_vs_ema200 is not None and 0 <= price_vs_ema200 <= 3)
    if volume_ratio is None:
        volume_state = "UNAVAILABLE"
    elif volume_ratio < 0.5:
        volume_state = "LOW (<0.5x)"
    elif volume_ratio < 1:
        volume_state = "BELOW AVERAGE (0.5–1x)"
    elif volume_ratio < 1.5:
        volume_state = "AVERAGE (1–1.5x)"
    else:
        volume_state = "HIGH (>=1.5x)"
    return {
        "trend_ema50_over_ema200_price_above_both": trend,
        "price_at_or_below_ema20": pullback,
        "rsi_45_55": moderate_rsi,
        "price_0_3pct_above_ema200": near_ema200,
        "ema50_vs_ema200_pct": None if gap50_200 is None else round(gap50_200, 4),
        "price_vs_ema20_pct": None if price_vs_ema20 is None else round(price_vs_ema20, 4),
        "price_vs_ema200_pct": None if price_vs_ema200 is None else round(price_vs_ema200, 4),
        "support_distance_pct": None if support_distance is None else round(support_distance, 4),
        "resistance_distance_pct": None if not resistance or not price else round((resistance-price)/price*100, 4),
        "relative_volume_state": volume_state,
        "relative_volume_ratio": None if volume_ratio is None else round(volume_ratio, 3),
        "matching_core_conditions": bool(trend and pullback and moderate_rsi and near_ema200),
        "interpretation_note": "Descriptive context only; not a buy/sell recommendation and not used by the signal engine.",
    }
