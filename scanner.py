"""Run one complete scan for one timeframe."""

from binance_data import get_klines_batch
from setup_score import score_symbol


def run_scan(symbols, timeframe, candle_lookback):
    candle_data, failed = get_klines_batch(
        symbols,
        interval=timeframe,
        limit=candle_lookback,
    )

    results = []
    for symbol, candles in candle_data.items():
        scored = score_symbol(symbol, candles)
        if scored:
            scored["timeframe"] = timeframe
            results.append(scored)

    results.sort(key=lambda r: r["score"], reverse=True)
    return results, failed
