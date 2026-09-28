"""Scan orchestration for the long-only spot scanner."""
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
    results.sort(key=lambda r: (r.get("qualified", False), r.get("score", 0)), reverse=True)
    return results, failed


def combine_mtf(scan_payloads):
    """Return all long-only signals with their timeframe evidence attached."""
    by_symbol = {}
    for tf, payload in scan_payloads.items():
        for r in payload.get("results", []):
            by_symbol.setdefault(r["symbol"], {})[tf] = r
    out = []
    for symbol, by_tf in by_symbol.items():
        candidates = [r for r in by_tf.values() if r.get("qualified") and r.get("setup_type") in TRADE_SETUPS]
        main = max(candidates, key=lambda r: r.get("score", 0)) if candidates else max(by_tf.values(), key=lambda r: r.get("score", 0))
        out.append({
            **main,
            "timeframes": by_tf,
            "mtf": {tf: bool(r.get("qualified")) for tf, r in by_tf.items()},
        })
    out.sort(key=lambda r: (r.get("qualified", False), r.get("score", 0)), reverse=True)
    return out
