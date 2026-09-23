"""Reliable Binance Spot public-market-data client."""

import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

from config import BINANCE_BASE_URL

HEADERS = {"Accept": "application/json", "User-Agent": "halal-crypto-scanner/1.0"}


def validate_symbols(symbols):
    try:
        resp = requests.get(
            f"{BINANCE_BASE_URL}/api/v3/exchangeInfo",
            timeout=10,
            headers=HEADERS,
        )
        resp.raise_for_status()
        active = {
            s["symbol"] for s in resp.json()["symbols"]
            if s["status"] == "TRADING" and s["quoteAsset"] == "USDT"
        }
        valid = [s for s in symbols if s in active]
        invalid = [s for s in symbols if s not in active]
        return valid, invalid
    except Exception as e:
        print(f"[binance] exchangeInfo failed ({e}) — using configured list")
        return symbols, []


def get_klines(symbol, interval="1h", limit=220):
    url = f"{BINANCE_BASE_URL}/api/v3/klines"
    params = {"symbol": symbol, "interval": interval, "limit": limit}
    resp = requests.get(url, params=params, timeout=8, headers=HEADERS)
    resp.raise_for_status()
    raw = resp.json()

    return [
        {
            "open_time": row[0],
            "open": float(row[1]),
            "high": float(row[2]),
            "low": float(row[3]),
            "close": float(row[4]),
            "volume": float(row[5]),
        }
        for row in raw
    ]


def get_klines_batch(symbols, interval="1h", limit=220, max_workers=20):
    results, failed = {}, []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        future_to_symbol = {
            pool.submit(get_klines, symbol, interval, limit): symbol
            for symbol in symbols
        }
        for future in as_completed(future_to_symbol):
            symbol = future_to_symbol[future]
            try:
                candles = future.result()
                if len(candles) < 60:
                    raise RuntimeError(f"Only {len(candles)} candles returned")
                results[symbol] = candles
            except Exception as e:
                failed.append((symbol, str(e)))
    return results, failed
