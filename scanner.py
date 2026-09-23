"""Scan orchestration."""
from binance_data import get_klines_batch
from setup_score import score_symbol

def run_scan(symbols, timeframe, candle_lookback):
    candle_data, failed = get_klines_batch(symbols, interval=timeframe, limit=candle_lookback)
    results=[]
    for symbol,candles in candle_data.items():
        scored=score_symbol(symbol,candles)
        if scored:
            scored["timeframe"]=timeframe
            results.append(scored)
    results.sort(key=lambda r:r["score"], reverse=True)
    return results, failed

def combine_mtf(scan_payloads):
    """Combine per-timeframe records by symbol without pretending MTF is a prediction."""
    by_symbol={}
    for tf,payload in scan_payloads.items():
        for r in payload.get("results",[]):
            by_symbol.setdefault(r["symbol"],{})[tf]=r
    out=[]
    for symbol,by_tf in by_symbol.items():
        scores=[r["score"] for r in by_tf.values()]
        bullish=sum(1 for r in by_tf.values() if r["indicators"]["ema20"] > r["indicators"]["ema50"])
        avg=round(sum(scores)/len(scores),1) if scores else 0
        out.append({"symbol":symbol,"avg_score":avg,"bullish_timeframes":bullish,"timeframes":by_tf})
    out.sort(key=lambda x:(x["avg_score"],x["bullish_timeframes"]),reverse=True)
    return out
