"""Scan orchestration shared by all five independent strategy scanners."""
from binance_data import get_klines_batch, liquidity_filter
from strategy_engine import scan_symbol, STRATEGIES


GENERIC_STRATEGIES = [
    "EMA200_CROSS",
    "RSI_DIVERGENCE",
    "BB_PULLBACK",
    "KIJUN_SSL",
]


def run_scan(symbols, timeframe, strategy="ALL", candle_lookback=280, minimum_liquidity=5_000_000):
    """Run one strategy or all five, sharing liquidity filtering and candle fetches.

    For ALL: strategies 1,2,4,5 use the selected timeframe; strategy 3 always
    uses 5m execution with a 15m EMA200 trend filter.
    """
    passed, skipped, liquidity_error = liquidity_filter(symbols, minimum_liquidity)
    if not passed:
        return {"results": [], "signals": [], "failed": [], "skipped": skipped,
                "liquidity_error": liquidity_error, "scanned_count": len(symbols), "analyzed_count": 0}

    strategies = list(STRATEGIES) if strategy == "ALL" else [strategy]
    timeframes = set()
    for key in strategies:
        timeframes.add("5m" if key == "VWAP_RSI_15M_EMA200" else timeframe)

    candle_sets = {}
    failed = []
    for interval in sorted(timeframes):
        candles, interval_failed = get_klines_batch(passed, interval=interval, limit=candle_lookback)
        candle_sets[interval] = candles
        failed.extend((s, f"{interval}: {reason}") for s, reason in interval_failed)

    trend_candles = {}
    if "VWAP_RSI_15M_EMA200" in strategies:
        trend_candles, trend_failed = get_klines_batch(passed, interval="15m", limit=candle_lookback)
        failed.extend((s, f"15m: {reason}") for s, reason in trend_failed)

    results = []
    for key in strategies:
        exec_tf = "5m" if key == "VWAP_RSI_15M_EMA200" else timeframe
        candles = candle_sets.get(exec_tf, {})
        for symbol, data in candles.items():
            results.extend(scan_symbol(symbol, exec_tf, data, key, trend_candles.get(symbol)))

    signals = [r for r in results if r.get("signal")]
    results.sort(key=lambda r: (not r.get("signal"), -r.get("score", 0), r.get("symbol", ""), r.get("setup_type", "")))
    return {"results": results, "signals": signals, "failed": failed, "skipped": skipped,
            "liquidity_error": liquidity_error, "scanned_count": len(symbols),
            "analyzed_count": len(candle_sets.get(timeframe, {}))}


def combine_mtf(payloads):
    by_symbol = {}
    for tf, payload in payloads.items():
        for r in payload.get("results", []):
            by_symbol.setdefault(r["symbol"], {}).setdefault(r["setup_type"], {})[tf] = r
    return by_symbol
