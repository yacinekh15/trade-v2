"""FastAPI endpoints for Trade-HHJ long-only Binance Spot scanner."""
import os,sys,time
from concurrent.futures import ThreadPoolExecutor, as_completed
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0,ROOT)
from fastapi import FastAPI,Header,HTTPException,Query
from pydantic import BaseModel,Field
app=FastAPI(title='Trade-HHJ Manual Spot Scanner')

def deps():
    from config import load_coins,TIMEFRAMES,DEFAULT_TIMEFRAME,CANDLE_LOOKBACK,SCAN_SECRET,BACKTEST_DEFAULT_LIMIT,BACKTEST_MAX_LIMIT,DEFAULT_MIN_QUOTE_VOLUME,TELEGRAM_BOT_TOKEN,TELEGRAM_CHAT_ID
    from scanner import run_scan,combine_mtf
    from telegram_alerts import check_and_alert,check_and_alert_mtf
    from upstash_client import get_json,set_json,configured as upstash_configured
    from binance_data import get_klines
    from backtest import backtest_candles
    return locals()

def auth(d,secret,header):
    if d['SCAN_SECRET'] and (header or secret)!=d['SCAN_SECRET']: raise HTTPException(401,'Invalid scan secret')

def persist(d,tf,payload):
    d['set_json'](f'results:{tf}',payload)
    d['set_json'](f'scan_status:{tf}',{k:payload[k] for k in ('status','timeframe','updated_at','duration_seconds','coin_count','successful_count','failed_count','skipped_count')})

def do_scan(tf,symbols,telegram_enabled=False):
    d=deps(); started=time.time(); results,failed,skipped=d['run_scan'](symbols,tf,d['CANDLE_LOOKBACK'],d['DEFAULT_MIN_QUOTE_VOLUME'])
    # Two-stage confirmation for Telegram: only candidates get higher-timeframe context.
    if telegram_enabled and results:
        higher={'1h':['4h'],'15m':['1h','4h'],'5m':['15m','1h','4h']}.get(tf,[])
        for r in results:
            if not r.get('telegram_eligible'): continue
            states={tf:'bullish' if r.get('qualified') else 'neutral'}; bear=0; bull=1 if r.get('qualified') else 0
            # Stage-2 MTF confirmation is parallelized because 15m candidates
            # can require both 1h and 4h candles. A slow sequential path can
            # exceed Vercel's function timeout. Failures remain neutral rather
            # than turning the whole scan into a 500/timeout.
            from setup_score import score_symbol
            def _check_htf(htf):
                hc=d['get_klines'](r['symbol'],htf,d['CANDLE_LOOKBACK'])
                return htf, score_symbol(r['symbol'],hc,0,htf)
            with ThreadPoolExecutor(max_workers=min(2,len(higher))) as pool:
                futures=[pool.submit(_check_htf,htf) for htf in higher]
                for f in as_completed(futures):
                    try:
                        htf,hr=f.result()
                        states[htf]='bullish' if hr and hr.get('qualified') else ('bearish' if hr and hr.get('setup_type')=='FAKEOUT' else 'neutral')
                    except Exception:
                        # Recover the timeframe name even when the request fails.
                        htf = higher[futures.index(f)]
                        states[htf]='neutral'
            bull=sum(v=='bullish' for v in states.values())
            bear=sum(v=='bearish' for v in states.values())
            r['mtf_states']=states
            if bear>=2 or (tf=='1h' and states.get('4h')=='bearish'):
                r['telegram_eligible']=False; r['analysis']['penalties']['contradiction']=25; r['score']=max(0,r['score']-25)
    # Alerting must never turn a successful market scan into HTTP 500.
    try:
        alerts=d['check_and_alert'](results,tf,enabled=telegram_enabled)
    except Exception as e:
        alerts=[]
        for r in results:
            r.setdefault('analysis',{}).setdefault('warnings',[]).append(f'Telegram error: {e}')
    payload={'status':'ok' if not failed else 'partial','timeframe':tf,'updated_at':time.time(),'duration_seconds':round(time.time()-started,2),'coin_count':len(symbols),'successful_count':len(results),'failed_count':len(failed),'skipped_count':len(skipped),'failed': [{'symbol':s,'reason':e} for s,e in failed], 'skipped':[{'symbol':s,'reason':e} for s,e in skipped], 'results':results,'alerts':alerts}
    # Persistence is best-effort: scanner results remain usable without Redis.
    try:
        persist(d,tf,payload)
    except Exception as e:
        payload['persistence_warning']=str(e)
    return payload

@app.get('/api/health')
async def health():
    d=deps(); return {'status':'ok','upstash_configured':d['upstash_configured'](),'telegram_configured':bool(d['TELEGRAM_BOT_TOKEN'] and d['TELEGRAM_CHAT_ID']),'timeframes':d['TIMEFRAMES'],'coins_file':len(d['load_coins']()),'auto_scan_supported':True,'auto_scan_interval_seconds':60}

@app.get('/api/universe')
async def universe():
    d=deps(); return {'symbols':d['load_coins'](),'count':len(d['load_coins']())}

@app.get('/api/results')
async def results(timeframe:str='1h'):
    d=deps()
    if timeframe=='all': return d['get_json']('results:all',{'status':'no_results','results':[]})
    if timeframe not in d['TIMEFRAMES']: raise HTTPException(400,'invalid timeframe')
    return d['get_json'](f'results:{timeframe}',{'status':'no_results','timeframe':timeframe,'results':[]})

@app.post('/api/scan')
async def scan(timeframe:str=Query('1h'),symbols:str=Query(''),telegram:int=Query(0,ge=0,le=1),secret:str=Query(''),x_scan_secret:str=Header('',alias='X-Scan-Secret')):
    d=deps(); auth(d,secret,x_scan_secret)
    if timeframe not in d['TIMEFRAMES']: raise HTTPException(400,'invalid timeframe')
    universe=d['load_coins'](); chosen=[s.strip().upper() for s in symbols.split(',') if s.strip()] if symbols else universe
    chosen=[s for s in chosen if s in universe]
    if not chosen: raise HTTPException(400,'No valid symbols selected')
    try:
        p=do_scan(timeframe,chosen,bool(telegram))
        return {'ok':True,**p}
    except Exception as e:
        # Return a useful API error instead of an opaque Vercel 500.
        raise HTTPException(502,f'Scan engine error: {type(e).__name__}: {e}')

@app.post('/api/scan-all')
async def scan_all(timeframes:str=Query('1h,4h'),symbols:str=Query(''),telegram:int=Query(0,ge=0,le=1),secret:str=Query(''),x_scan_secret:str=Header('',alias='X-Scan-Secret')):
    d=deps(); auth(d,secret,x_scan_secret); universe=d['load_coins']; chosen=[s.strip().upper() for s in symbols.split(',') if s.strip()] if symbols else universe(); tfs=[x.strip() for x in timeframes.split(',') if x.strip()]
    if any(x not in d['TIMEFRAMES'] for x in tfs): raise HTTPException(400,'invalid timeframe')
    payloads={tf:do_scan(tf,[s for s in chosen if s in universe()],False) for tf in tfs}; combined=d['combine_mtf'](payloads); alerts=d['check_and_alert_mtf'](combined,bool(telegram))
    out={'status':'ok','updated_at':time.time(),'timeframes':tfs,'results':combined,'alerts':alerts}; d['set_json']('results:all',out); return out

@app.get('/api/candles')
async def candles(symbol:str,timeframe:str='1h',limit:int=260):
    d=deps(); symbol=symbol.upper().strip()
    if timeframe not in d['TIMEFRAMES']: raise HTTPException(400,'invalid timeframe')
    try:return {'symbol':symbol,'timeframe':timeframe,'candles':d['get_klines'](symbol,timeframe,max(250,min(limit,1000)))}
    except Exception as e: raise HTTPException(502,f'Market data error: {e}')

@app.post('/api/backtest')
async def backtest(symbol:str,timeframe:str='1h',limit:int=None,max_hold:int=200):
    d=deps(); symbol=symbol.upper().strip()
    if timeframe not in d['TIMEFRAMES']: raise HTTPException(400,'invalid timeframe')
    limit=max(250,min(limit or d['BACKTEST_DEFAULT_LIMIT'],d['BACKTEST_MAX_LIMIT']))
    try:return d['backtest_candles'](symbol,d['get_klines'](symbol,timeframe,limit),timeframe,max_hold)
    except Exception as e: raise HTTPException(502,f'Backtest data error: {e}')

class PaperTrade(BaseModel):
    symbol:str; timeframe:str='1h'; setup:str; direction:str='LONG'; entry:float; invalidation:float; tp1:float|None=None; tp2:float|None=None; score:int=0; note:str=''

@app.get('/api/paper-trades')
async def paper_trades():
    d=deps(); return {'trades':d['get_json']('paper_trades',[]) or []}

@app.post('/api/paper-trades')
async def add_paper_trade(trade:PaperTrade):
    if trade.direction!='LONG': raise HTTPException(400,'Paper trading is long-only')
    d=deps(); rows=d['get_json']('paper_trades',[]) or []; row={'id':int(time.time()*1000),**trade.model_dump(),'status':'OPEN','created_at':time.time()}; rows.insert(0,row); d['set_json']('paper_trades',rows[:500]); return {'ok':True,'trade':row}

@app.get('/api/telegram')
async def telegram_status():
    d=deps(); state=d['get_json']('telegram_enabled',True); return {'enabled':bool(state),'configured':bool(d['TELEGRAM_BOT_TOKEN'] and d['TELEGRAM_CHAT_ID'])}

@app.post('/api/telegram')
async def telegram_toggle(enabled:bool=Query(...)):
    d=deps(); d['set_json']('telegram_enabled',bool(enabled)); return {'ok':True,'enabled':bool(enabled),'configured':bool(d['TELEGRAM_BOT_TOKEN'] and d['TELEGRAM_CHAT_ID'])}
