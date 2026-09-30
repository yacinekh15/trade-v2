"""Binance Spot public-data client. No futures endpoints are used."""
import time
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from config import BINANCE_BASE_URL, LIQUIDITY_MIN_USDT

HEADERS = {"Accept": "application/json", "User-Agent": "trade-hhj-scanner/1.0"}


def _get(path, params=None, retries=3):
    last = None
    for attempt in range(retries):
        try:
            r = requests.get(f"{BINANCE_BASE_URL}{path}", params=params, headers=HEADERS, timeout=8)
            if r.status_code in (418, 429):
                time.sleep(0.7 * (attempt + 1))
                last = RuntimeError(f"Binance rate limit HTTP {r.status_code}")
                continue
            r.raise_for_status()
            return r.json()
        except Exception as e:
            last = e
            if attempt + 1 < retries:
                time.sleep(0.35 * (attempt + 1))
    raise last or RuntimeError("Binance request failed")


def get_24h_tickers():
    rows = _get("/api/v3/ticker/24hr")
    return {r["symbol"]: float(r.get("quoteVolume") or 0) for r in rows}


def liquidity_filter(symbols, minimum=LIQUIDITY_MIN_USDT):
    try:
        volumes = get_24h_tickers()
    except Exception as e:
        # If the single ticker endpoint fails, do not silently discard the universe.
        return list(symbols), [], f"liquidity endpoint unavailable: {e}"
    passed, skipped = [], []
    for s in symbols:
        qv = volumes.get(s)
        if qv is None:
            skipped.append((s, "not present in Binance Spot 24h ticker"))
        elif qv < minimum:
            skipped.append((s, f"24h quote volume {qv:,.0f} < {minimum:,.0f} USDT"))
        else:
            passed.append(s)
    return passed, skipped, None


def get_klines(symbol, interval="1h", limit=280):
    raw = _get("/api/v3/klines", {"symbol": symbol, "interval": interval, "limit": min(1000, int(limit))})
    now_ms = int(time.time() * 1000)
    out = []
    for row in raw:
        close_time = int(row[6])
        if close_time > now_ms:
            continue
        out.append({
            "open_time": int(row[0]), "open": float(row[1]), "high": float(row[2]),
            "low": float(row[3]), "close": float(row[4]), "volume": float(row[5]),
            "close_time": close_time,
        })
    return out


def get_klines_batch(symbols, interval="1h", limit=280, max_workers=8):
    results, failed = {}, []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(get_klines, s, interval, limit): s for s in symbols}
        for future in as_completed(futures):
            s = futures[future]
            try:
                candles = future.result()
                if len(candles) < 220:
                    raise RuntimeError(f"Only {len(candles)} closed candles returned; need at least 220")
                results[s] = candles
            except Exception as e:
                failed.append((s, str(e)))
    return results, failed
