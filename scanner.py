"""Scan orchestration shared by all independent strategy scanners."""
from binance_data import get_klines_batch, liquidity_filter
from strategy_engine import scan_symbol, STRATEGIES


def run_scan(symbols, timeframe, strategy="ALL", candle_lookback=280, minimum_liquidity=5_000_000):
    passed, skipped, liquidity_error = liquidity_filter(symbols, minimum_liquidity)
    candles, failed = get_klines_batch(passed, interval=timeframe, limit=candle_lookback)
    trend_candles = {}
    if strategy == "VWAP_RSI_15M_EMA200" and timeframe == "5m":
        trend_candles, trend_failed = get_klines_batch(passed, interval="15m", limit=candle_lookback)
        failed.extend(trend_failed)
    results=[]
    for symbol, data in candles.items():
        results.extend(scan_symbol(symbol,timeframe,data,strategy,trend_candles.get(symbol)))
    signals=[r for r in results if r.get("signal")]
    results.sort(key=lambda r:(not r.get("signal"),-r.get("score",0),r.get("symbol","")))
    return {"results":results,"signals":signals,"failed":failed,"skipped":skipped,"liquidity_error":liquidity_error,"scanned_count":len(symbols),"analyzed_count":len(candles)}


def combine_mtf(payloads):
    by_symbol={}
    for tf,payload in payloads.items():
        for r in payload.get("results",[]):
            by_symbol.setdefault(r["symbol"],{}).setdefault(r["setup_type"],{})[tf]=r
    return by_symbol
