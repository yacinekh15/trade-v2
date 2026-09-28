"""Manual scan orchestration with liquidity filtering and bounded batches."""
from binance_data import get_klines_batch,get_tickers
from setup_score import score_symbol
from config import DEFAULT_MIN_QUOTE_VOLUME

def run_scan(symbols,timeframe,candle_lookback,min_quote_volume=DEFAULT_MIN_QUOTE_VOLUME):
    tickers=get_tickers()
    eligible=[]; skipped=[]
    for s in symbols:
        t=tickers.get(s)
        if not t:
            skipped.append((s,'No Binance Spot USDT ticker'))
        elif t['quote_volume']<min_quote_volume:
            skipped.append((s,f"24h quote volume {t['quote_volume']:,.0f} < {min_quote_volume:,.0f} USDT"))
        else: eligible.append(s)
    data,failed=get_klines_batch(eligible,timeframe,candle_lookback,max_workers=8)
    results=[]
    for s,c in data.items():
        r=score_symbol(s,c,tickers[s]['quote_volume'],timeframe)
        if r: results.append(r)
    results.sort(key=lambda r:(r['telegram_eligible'],r['qualified'],r['score']),reverse=True)
    return results,failed,skipped

def combine_mtf(payloads):
    by={}
    for tf,p in payloads.items():
        for r in p.get('results',[]): by.setdefault(r['symbol'],{})[tf]=r
    out=[]
    for symbol,tfs in by.items():
        primary=tfs.get('1h') or tfs.get('4h') or max(tfs.values(),key=lambda x:x.get('score',0))
        states={tf:('bullish' if r.get('qualified') else ('bearish' if r.get('setup_type') in {'FAKEOUT'} else 'neutral')) for tf,r in tfs.items()}
        bullish=sum(v=='bullish' for v in states.values())
        bearish=sum(v=='bearish' for v in states.values())
        strong=bearish>=2 and bullish<=1
        r={**primary,'mtf_states':states,'mtf':{'bullish_count':bullish,'bearish_count':bearish,'strong_contradiction':strong}}
        r['score']=max(0,r['score']-25 if strong else r['score'])
        r['telegram_eligible']=bool(r.get('telegram_eligible')) and not strong
        out.append(r)
    return sorted(out,key=lambda x:(x.get('telegram_eligible'),x.get('qualified'),x.get('score')),reverse=True)
