"""Vercel API for the manual Halal Crypto Scanner."""
import os,sys,time,traceback
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0,ROOT)
from fastapi import FastAPI,Header,HTTPException,Query
app=FastAPI(title="Halal Crypto Scanner API")

def deps():
    try:
        from config import load_coins,TIMEFRAMES,DEFAULT_TIMEFRAME,CANDLE_LOOKBACK,SCAN_SECRET,TELEGRAM_BOT_TOKEN,TELEGRAM_CHAT_ID,BACKTEST_DEFAULT_LIMIT,BACKTEST_MAX_LIMIT
        from scanner import run_scan,combine_mtf
        from telegram_alerts import check_and_alert, check_and_alert_mtf
        from upstash_client import get_json,set_json,configured as upstash_configured
        from binance_data import get_klines
        from backtest import backtest_candles
        return locals()
    except Exception:
        traceback.print_exc(); raise

def key(tf):return f"results:{tf}"
def status_key(tf):return f"scan_status:{tf}"
def _auth(d,secret,header):
    expected=d["SCAN_SECRET"]; supplied=header or secret
    if expected and supplied!=expected:raise HTTPException(401,"Invalid scan secret")

def do_scan(tf, telegram_enabled=True):
    d=deps(); started=time.time(); symbols=d["load_coins"](); results,failed=d["run_scan"](symbols,tf,d["CANDLE_LOOKBACK"]); alerts=d["check_and_alert"](results,tf,enabled=telegram_enabled); finished=time.time()
    payload={"status":"ok" if not failed else "partial","timeframe":tf,"updated_at":finished,"duration_seconds":round(finished-started,2),"coin_count":len(symbols),"successful_count":len(results),"failed_count":len(failed),"failed_samples":[{"symbol":s,"error":e} for s,e in failed[:10]],"results":results,"alerts":alerts}
    d["set_json"](key(tf),payload); d["set_json"](status_key(tf),{k:payload[k] for k in ("status","timeframe","updated_at","duration_seconds","coin_count","successful_count","failed_count","failed_samples","alerts")}); return payload

@app.get("/api/health")
async def health():
    d=deps(); return {"status":"ok","python":sys.version,"upstash_configured":d["upstash_configured"](),"telegram_configured":bool(d["TELEGRAM_BOT_TOKEN"] and d["TELEGRAM_CHAT_ID"]),"timeframes":d["TIMEFRAMES"],"coins_file":len(d["load_coins"]())}

@app.get("/api/results")
async def results(timeframe:str=None):
    d=deps(); tf=timeframe or d["DEFAULT_TIMEFRAME"]
    if tf == "all":
        return d["get_json"]("results:all",default={"status":"no_results","timeframe":"all","results":[]})
    if tf not in d["TIMEFRAMES"]:raise HTTPException(400,f"timeframe must be one of {d['TIMEFRAMES']}")
    return d["get_json"](key(tf),default={"status":"no_results","timeframe":tf,"results":[],"failed_count":0})

@app.get("/api/status")
async def status(timeframe:str=None):
    d=deps(); tf=timeframe or d["DEFAULT_TIMEFRAME"]
    if tf not in d["TIMEFRAMES"]:raise HTTPException(400,f"timeframe must be one of {d['TIMEFRAMES']}")
    return {"status":"ok","server_time":time.time(),"timeframe":tf,"scan":d["get_json"](status_key(tf),default={"status":"never_run","timeframe":tf}),"telegram_configured":bool(d["TELEGRAM_BOT_TOKEN"] and d["TELEGRAM_CHAT_ID"])}

@app.post("/api/scan")
async def scan(timeframe:str=Query(None),secret:str=Query(""),telegram:int=Query(1, ge=0, le=1),x_scan_secret:str=Header("",alias="X-Scan-Secret")):
    d=deps(); _auth(d,secret,x_scan_secret); tf=timeframe or d["DEFAULT_TIMEFRAME"]
    if tf=="all":
        payloads={}; all_alerts=[]; started=time.time()
        telegram_enabled = bool(telegram)
        for one in d["TIMEFRAMES"]:
            p=do_scan(one, telegram_enabled=telegram_enabled); payloads[one]=p; all_alerts.append(p["alerts"])
        combined=d["combine_mtf"](payloads)
        selective_alerts=d["check_and_alert_mtf"](payloads, enabled=telegram_enabled)
        d["set_json"]("results:all",{"status":"ok","updated_at":time.time(),"timeframes":d["TIMEFRAMES"],"results":combined,"alerts":selective_alerts,"duration_seconds":round(time.time()-started,2)})
        return {"ok":True,"timeframe":"all","num_results":len(combined),"telegram_enabled":telegram_enabled,"alerts":selective_alerts,"duration_seconds":round(time.time()-started,2)}
    if tf not in d["TIMEFRAMES"]:raise HTTPException(400,f"timeframe must be one of {d['TIMEFRAMES']}")
    telegram_enabled = bool(telegram)
    p=do_scan(tf, telegram_enabled=telegram_enabled); return {"ok":True,"timeframe":tf,"num_results":len(p["results"]),"failed_count":p["failed_count"],"duration_seconds":p["duration_seconds"],"telegram_enabled":telegram_enabled,"alerts":p["alerts"]}

@app.get("/api/candles")
async def candles(symbol:str,timeframe:str="1h",limit:int=220):
    d=deps(); symbol=symbol.upper().strip();
    if timeframe not in d["TIMEFRAMES"]:raise HTTPException(400,"invalid timeframe")
    limit=max(60,min(limit,1000))
    try:return {"symbol":symbol,"timeframe":timeframe,"candles":d["get_klines"](symbol,timeframe,limit)}
    except Exception as e:raise HTTPException(502,f"Market data error: {e}")

@app.post("/api/backtest")
async def backtest(symbol:str,timeframe:str="1h",limit:int=None,min_score:int=70,max_hold:int=24):
    d=deps(); symbol=symbol.upper().strip()
    if timeframe not in d["TIMEFRAMES"]:raise HTTPException(400,"invalid timeframe")
    limit=max(100,min(limit or d["BACKTEST_DEFAULT_LIMIT"],d["BACKTEST_MAX_LIMIT"]))
    max_hold=max(1,min(max_hold,200)); min_score=max(0,min(min_score,100))
    try:
        candles=d["get_klines"](symbol,timeframe,limit); return d["backtest_candles"](symbol,candles,timeframe,min_score,max_hold)
    except Exception as e:raise HTTPException(502,f"Backtest data error: {e}")

from pydantic import BaseModel

class PaperTrade(BaseModel):
    symbol: str
    timeframe: str = "1h"
    entry: float
    score: int = 0
    note: str = ""

@app.get("/api/paper-trades")
async def paper_trades():
    d=deps(); return {"trades": d["get_json"]("paper_trades", default=[]) or []}

@app.post("/api/paper-trades")
async def add_paper_trade(trade: PaperTrade):
    d=deps(); rows=d["get_json"]("paper_trades", default=[]) or []
    rows.insert(0,{"id":int(time.time()*1000),**trade.model_dump(),"created_at":time.time(),"status":"OPEN"})
    rows=rows[:200]; d["set_json"]("paper_trades",rows); return {"ok":True,"trade":rows[0]}

@app.post("/api/timeframe")
async def set_timeframe(timeframe:str=Query(...)):
    d=deps()
    if timeframe not in d["TIMEFRAMES"]:raise HTTPException(400,"invalid timeframe")
    return {"ok":True,"current_timeframe":timeframe}
