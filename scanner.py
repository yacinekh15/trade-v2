"""Scan orchestration and multi-timeframe qualification."""
from binance_data import get_klines_batch
from setup_score import score_symbol, TRADE_SETUPS


def run_scan(symbols, timeframe, candle_lookback):
    candle_data, failed = get_klines_batch(symbols, interval=timeframe, limit=candle_lookback)
    results = []
    for symbol, candles in candle_data.items():
        scored = score_symbol(symbol, candles)
        if scored:
            scored["timeframe"] = timeframe
            results.append(scored)
    results.sort(key=lambda r: (r.get("qualified", False), r.get("entry_quality", 0), r.get("score", 0)), reverse=True)
    return results, failed


def _bullish_context(r):
    if not r:
        return False
    i = r.get("indicators", {})
    return bool(
        i.get("ema20", 0) > i.get("ema50", 0)
        and i.get("ema50", 0) > i.get("ema200", 0)
        and i.get("ema200_rising", False)
    )


def combine_mtf(scan_payloads):
    """Combine timeframes into an entry-focused MTF view.

    4H = regime, 1H = main structure, 15M = confirmation, 5M = timing.
    Missing higher-timeframe data never gets silently treated as bullish.
    """
    by_symbol = {}
    for tf, payload in scan_payloads.items():
        for r in payload.get("results", []):
            by_symbol.setdefault(r["symbol"], {})[tf] = r

    out = []
    for symbol, by_tf in by_symbol.items():
        h4 = by_tf.get("4h")
        h1 = by_tf.get("1h")
        m15 = by_tf.get("15m")
        m5 = by_tf.get("5m")
        main = h1 or h4 or m15 or m5
        if not main:
            continue

        regime_ok = _bullish_context(h4)
        structure_ok = _bullish_context(h1)
        timing = m15 or m5
        timing_ok = bool(timing and timing.get("indicators", {}).get("macd", 0) > timing.get("indicators", {}).get("macd_signal", 0))
        confirmations = sum([regime_ok, structure_ok, timing_ok])

        # A candidate from a lower timeframe cannot become a high-quality MTF
        # setup when the 4H/1H context is missing or bearish.
        qualified = bool(
            main.get("setup_type") in TRADE_SETUPS
            and main.get("qualified")
            and regime_ok
            and structure_ok
            and confirmations >= 2
        )
        mtf_score = int(main.get("entry_quality", main.get("score", 0)))
        mtf_score += 5 if regime_ok else -10
        mtf_score += 5 if structure_ok else -10
        mtf_score += 3 if timing_ok else 0
        mtf_score = max(0, min(100, mtf_score))

        out.append({
            "symbol": symbol,
            "avg_score": round(sum(r.get("score", 0) for r in by_tf.values()) / len(by_tf), 1),
            "entry_quality": mtf_score,
            "qualified": qualified,
            "bullish_timeframes": confirmations,
            "mtf": {"4h": regime_ok, "1h": structure_ok, "15m": timing_ok, "5m": bool(m5)},
            "timeframes": by_tf,
            "setup_type": main.get("setup_type"),
            "score": main.get("score", 0),
            "analysis": main.get("analysis", {}),
            "indicators": main.get("indicators", {}),
            "reasons": main.get("reasons", []),
            "rejection_reasons": main.get("rejection_reasons", []),
        })

    out.sort(key=lambda x: (x["qualified"], x["entry_quality"], x["avg_score"]), reverse=True)
    return out
