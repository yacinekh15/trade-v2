"""Walk-forward backtesting with no look-ahead."""
from setup_score import score_symbol

def _levels(result):
    p=float(result["price"]); atr=float(result["indicators"].get("atr") or 0)
    support=float(result["indicators"].get("support") or p)
    resistance=float(result["indicators"].get("resistance") or p)
    if atr<=0: return p,resistance,support
    stop=max(0.0,min(support,p-1.5*atr))
    target=max(resistance,p+2*atr)
    return p,target,stop

def backtest_candles(symbol,candles,timeframe="1h",min_score=70,max_hold=24):
    """Signal on closed candle i; enter at next candle open; evaluate subsequent OHLC."""
    trades=[]; warmup=201
    for i in range(warmup,len(candles)-1):
        window=candles[:i+1]
        r=score_symbol(symbol,window+[candles[i+1]]) if False else score_symbol(symbol,window)
        # score_symbol removes the last candle, so window must include a dummy current candle.
        # Rebuild with a copy of the signal candle plus a synthetic current candle is unsafe.
        # Instead use the exact historical prefix ending at i+1 and treat candle i as closed.
        if i+1 >= len(candles): break
        r=score_symbol(symbol,candles[:i+2])
        if not r or r["score"]<min_score or r["setup_type"] not in {"BREAKOUT","MOMENTUM","EMA200_MACD"}: continue
        entry_c=candles[i+1]; entry=float(entry_c["open"])
        # Use signal-derived ATR/support/resistance from candle i, but entry is next open.
        atr=float(r["indicators"].get("atr") or 0); support=float(r["indicators"].get("support") or entry); resistance=float(r["indicators"].get("resistance") or entry)
        stop=max(0.0,min(support,entry-1.5*atr)) if atr else entry*0.98
        target=max(resistance,entry+2*atr) if atr else entry*1.03
        outcome="TIMEOUT"; exit_price=float(candles[min(i+1+max_hold,len(candles)-1)]["close"]); exit_i=min(i+1+max_hold,len(candles)-1)
        for j in range(i+1,min(len(candles),i+1+max_hold)):
            c=candles[j]
            hit_stop=c["low"]<=stop; hit_target=c["high"]>=target
            if hit_stop and hit_target:
                outcome="STOP_AND_TARGET_SAME_CANDLE"; exit_price=stop; exit_i=j; break
            if hit_stop:
                outcome="STOP"; exit_price=stop; exit_i=j; break
            if hit_target:
                outcome="TARGET"; exit_price=target; exit_i=j; break
        pnl_pct=(exit_price-entry)/entry*100
        trades.append({"symbol":symbol,"timeframe":timeframe,"signal_index":i,"entry_time":entry_c["open_time"],"entry":entry,"target":target,"stop":stop,"exit":exit_price,"exit_time":candles[exit_i]["open_time"],"outcome":outcome,"pnl_pct":round(pnl_pct,4),"score":r["score"]})
    wins=sum(t["outcome"]=="TARGET" for t in trades); losses=sum(t["outcome"]=="STOP" for t in trades)
    total_pnl=round(sum(t["pnl_pct"] for t in trades),4)
    return {"symbol":symbol,"timeframe":timeframe,"trades":trades,"summary":{"signals":len(trades),"wins":wins,"losses":losses,"timeouts":len(trades)-wins-losses,"win_rate_pct":round(wins/len(trades)*100,2) if trades else 0,"total_pnl_pct":total_pnl}}
