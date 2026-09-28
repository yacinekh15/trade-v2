"""Binance Spot public-data client. Never uses futures endpoints."""
import time,requests
from concurrent.futures import ThreadPoolExecutor,as_completed
from config import BINANCE_BASE_URL
HEADERS={'Accept':'application/json','User-Agent':'Trade-HHJ/1.0'}

def _get(url,params=None,attempts=3):
    for n in range(attempts):
        try:
            r=requests.get(url,params=params,headers=HEADERS,timeout=10)
            if r.status_code in (418,429): time.sleep(1.5*(n+1)); continue
            r.raise_for_status(); return r.json()
        except Exception:
            if n==attempts-1: raise
            time.sleep(0.7*(n+1))

_TICKER_CACHE={'ts':0,'data':{}}

def get_tickers():
    # Cache the 24h ticker list briefly; every scanner batch does not need a new request.
    now=time.time()
    if _TICKER_CACHE['data'] and now-_TICKER_CACHE['ts'] < 20:
        return _TICKER_CACHE['data']
    rows=_get(f'{BINANCE_BASE_URL}/api/v3/ticker/24hr')
    data={x['symbol']:{'quote_volume':float(x.get('quoteVolume',0)),'last_price':float(x.get('lastPrice',0)),'price_change_pct':float(x.get('priceChangePercent',0))} for x in rows if x.get('symbol','').endswith('USDT')}
    _TICKER_CACHE.update(ts=now,data=data)
    return data

def validate_symbols(symbols):
    try:
        rows=_get(f'{BINANCE_BASE_URL}/api/v3/exchangeInfo')
        active={s['symbol'] for s in rows['symbols'] if s.get('status')=='TRADING' and s.get('quoteAsset')=='USDT'}
        return [s for s in symbols if s in active],[s for s in symbols if s not in active]
    except Exception as e: return symbols,[]

def get_klines(symbol,interval='1h',limit=260):
    raw=_get(f'{BINANCE_BASE_URL}/api/v3/klines',{'symbol':symbol,'interval':interval,'limit':min(limit,1000)})
    return [{'open_time':r[0],'open':float(r[1]),'high':float(r[2]),'low':float(r[3]),'close':float(r[4]),'volume':float(r[5]),'close_time':r[6]} for r in raw]

def get_klines_batch(symbols,interval='1h',limit=260,max_workers=8):
    results={}; failed=[]
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        fs={pool.submit(get_klines,s,interval,limit):s for s in symbols}
        for f in as_completed(fs):
            s=fs[f]
            try:
                rows=f.result(); now=int(time.time()*1000); closed=[x for x in rows if x.get('close_time',0)<=now]
                if len(closed)<250: raise RuntimeError(f'Only {len(closed)} closed candles returned')
                results[s]=closed
            except Exception as e: failed.append((s,str(e)))
    return results,failed
