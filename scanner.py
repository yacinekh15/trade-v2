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
    """Run one strategy or all five in one request.

    Strategy #3 has fixed execution/trend timeframes (5m + 15m), so ALL
    automatically fetches those required datasets even when the dashboard
    timeframe is 15m/1h/4h. The other four use the selected dashboard timeframe.
    """
    passed, skipped, liquidity_error = liquidity_filter(symbols, minimum_liquidity)

    if strategy == "ALL":
        # One fetch for the selected timeframe, reused by four strategies.
        candles, failed = get_klines_batch(passed, interval=timeframe, limit=candle_lookback)
        results = []
        for symbol, data in candles.items():
            results.extend(scan_symbol(symbol, timeframe, data, "EMA200_CROSS"))
            results.extend(scan_symbol(symbol, timeframe, data, "RSI_DIVERGENCE"))
            results.extend(scan_symbol(symbol, timeframe, data, "BB_PULLBACK"))
            results.extend(scan_symbol(symbol, timeframe, data, "KIJUN_SSL"))

        # Strategy #3 always uses 5m execution + 15m EMA200, regardless of UI TF.
        exec5m, failed5m = get_klines_batch(passed, interval="5m", limit=candle_lookback)
        trend15m, failed15m = get_klines_batch(passed, interval="15m", limit=candle_lookback)
        failed.extend(failed5m)
        failed.extend(failed15m)
        for symbol, data in exec5m.items():
            results.extend(scan_symbol(symbol, "5m", data, "VWAP_RSI_15M_EMA200", trend15m.get(symbol)))

    else:
        passed2 = passed
        candles, failed = get_klines_batch(passed2, interval=timeframe, limit=candle_lookback)
        trend_candles = {}
        if strategy == "VWAP_RSI_15M_EMA200":
            # This strategy is intrinsically 5m + 15m. Ignore an incompatible
            # dashboard TF rather than producing a false/error signal.
            if timeframe != "5m":
                candles, failed = get_klines_batch(passed2, interval="5m", limit=candle_lookback)
                trend_candles, trend_failed = get_klines_batch(passed2, interval="15m", limit=candle_lookback)
                failed.extend(trend_failed)
                timeframe = "5m"
            else:
                trend_candles, trend_failed = get_klines_batch(passed2, interval="15m", limit=candle_lookback)
                failed.extend(trend_failed)
        results = []
        for symbol, data in candles.items():
            results.extend(scan_symbol(symbol, timeframe, data, strategy, trend_candles.get(symbol)))

    signals = [r for r in results if r.get("signal")]
    results.sort(key=lambda r: (not r.get("signal"), -r.get("score", 0), r.get("symbol", ""), r.get("setup_type", "")))
    return {
        "results": results, "signals": signals, "failed": failed, "skipped": skipped,
        "liquidity_error": liquidity_error, "scanned_count": len(symbols),
        "analyzed_count": len(passed) if passed else 0,
    }


def combine_mtf(payloads):
    by_symbol = {}
    for tf, payload in payloads.items():
        for r in payload.get("results", []):
            by_symbol.setdefault(r["symbol"], {}).setdefault(r["setup_type"], {})[tf] = r
    return by_symbol
