"""Trade-HHJ Vercel API for the fresh multi-strategy Binance Spot scanner."""
import os,sys,time,traceback
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)));sys.path.insert(0,ROOT)
from fastapi import FastAPI,Header,HTTPException,Query
from config import *
from scanner import run_scan,STRATEGIES
from telegram_alerts import alert_signals
from upstash_client import get_json,set_json,configured as upstash_configured
from binance_data import get_klines

app=FastAPI(title="Trade-HHJ Scanner API")

from pydantic import BaseModel

class BatchRequest(BaseModel):
    symbols: list[str]
    timeframe: str = DEFAULT_TIMEFRAME
    strategy: str = "EMA200_CROSS"
    telegram: bool = False

class TelegramSetting(BaseModel):
    enabled: bool


MEM_RESULTS={}

def _auth(secret,header):
    if SCAN_SECRET and (header or secret)!=SCAN_SECRET: raise HTTPException(401,"Invalid scan secret")

def _save(key,payload):
    MEM_RESULTS[key]=payload
    try:set_json(key,payload)
    except Exception:pass

def _load(key,default):
    if key in MEM_RESULTS:return MEM_RESULTS[key]
    try:return get_json(key,default)
    except Exception:return default

def do_scan(tf,strategy,telegram_enabled=False):
    started=time.time(); coins=load_coins()
    payload=run_scan(coins,tf,strategy,CANDLE_LOOKBACK,LIQUIDITY_MIN_USDT)
    alerts=alert_signals(payload["signals"],tf,telegram_enabled)
    results=payload["results"]
    out={"status":"ok","timeframe":tf,"strategy":strategy,"updated_at":time.time(),"duration_seconds":round(time.time()-started,2),
         "coin_count":len(coins),"scanned_count":payload["scanned_count"],"analyzed_count":payload["analyzed_count"],
         "failed_count":len(payload["failed"]),"failed":payload["failed"],"skipped_count":len(payload["skipped"]),
         "skipped":payload["skipped"],"results":results,"signals":payload["signals"],"alerts":alerts,
         "liquidity_error":payload["liquidity_error"]}
    _save(f"results:{strategy}:{tf}",out);return out

@app.get("/api/health")
async def health():
    return {"status":"ok","python":sys.version.split()[0],"upstash_configured":upstash_configured(),"telegram_configured":bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID),"timeframes":TIMEFRAMES,"coin_count":len(load_coins()),"strategies":list(STRATEGIES)}

@app.get("/api/config")
async def config_endpoint():
    return {"timeframes":TIMEFRAMES,"strategies":["EMA200_CROSS","RSI_DIVERGENCE","VWAP_RSI_15M_EMA200","BB_PULLBACK","KIJUN_SSL"],"all_strategies":list(STRATEGIES),"default_timeframe":DEFAULT_TIMEFRAME,"auto_scan_seconds":AUTO_SCAN_SECONDS,"liquidity_min_usdt":LIQUIDITY_MIN_USDT,"telegram_configured":bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID),"coin_count":len(load_coins())}

@app.get("/api/results")
async def results(timeframe:str=DEFAULT_TIMEFRAME,strategy:str="EMA200_CROSS"):
    if timeframe not in TIMEFRAMES:raise HTTPException(400,"invalid timeframe")
    if strategy not in STRATEGIES and strategy != "ALL":raise HTTPException(400,"invalid strategy")
    return _load(f"results:{strategy}:{timeframe}",{"status":"no_results","timeframe":timeframe,"strategy":strategy,"results":[],"signals":[]})

@app.get("/api/status")
async def status(timeframe:str=DEFAULT_TIMEFRAME,strategy:str="EMA200_CROSS"):
    r=_load(f"results:{strategy}:{timeframe}",{})
    return {"status":"ok","server_time":time.time(),"timeframe":timeframe,"strategy":strategy,"scan":r,"telegram_configured":bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID),"upstash_configured":upstash_configured()}

@app.post("/api/scan_batch")
async def scan_batch(req: BatchRequest, secret: str = Query(""), x_scan_secret: str = Header("", alias="X-Scan-Secret")):
    _auth(secret, x_scan_secret)
    if req.timeframe not in TIMEFRAMES: raise HTTPException(400, "invalid timeframe")
    if req.strategy not in STRATEGIES and req.strategy != "ALL": raise HTTPException(400, "invalid strategy")
    if not req.symbols or len(req.symbols) > 50: raise HTTPException(400, "symbols must contain 1-50 coins")
    # ALL is a single request: one liquidity pass, one primary timeframe candle
    # fetch, and (for 5m) one 15m fetch shared by the VWAP strategy.
    a=run_scan(req.symbols, req.timeframe, req.strategy, CANDLE_LOOKBACK, LIQUIDITY_MIN_USDT)
    results=a["results"]; signals=a["signals"]
    alerts=alert_signals(signals,req.timeframe,req.telegram)
    return {"ok":True,"results":results,"signals":signals,"failed":a["failed"],"skipped":a["skipped"],"liquidity_error":a["liquidity_error"],"alerts":alerts}

@app.get("/api/settings/telegram")
async def get_telegram_setting():
    default=TELEGRAM_ENABLED_DEFAULT
    return {"enabled":bool(_load("settings:telegram",{"enabled":default}).get("enabled",default)),"configured":bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)}

@app.post("/api/settings/telegram")
async def set_telegram_setting(setting: TelegramSetting):
    _save("settings:telegram",{"enabled":setting.enabled})
    return {"ok":True,"enabled":setting.enabled,"configured":bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)}

@app.post("/api/scan")
async def scan(timeframe:str=Query(DEFAULT_TIMEFRAME),strategy:str=Query("EMA200_CROSS"),telegram:int=Query(0,ge=0,le=1),secret:str=Query(""),x_scan_secret:str=Header("",alias="X-Scan-Secret")):
    _auth(secret,x_scan_secret)
    if timeframe not in TIMEFRAMES:raise HTTPException(400,"invalid timeframe")
    p=do_scan(timeframe,strategy,bool(telegram));return {"ok":True,**p}

@app.get("/api/candles")
async def candles(symbol:str,timeframe:str="1h",limit:int=280):
    if timeframe not in TIMEFRAMES:raise HTTPException(400,"invalid timeframe")
    try:return {"symbol":symbol.upper().strip(),"timeframe":timeframe,"candles":get_klines(symbol.upper().strip(),timeframe,max(220,min(limit,1000)))}
    except Exception as e:raise HTTPException(502,f"Market data error: {e}")

@app.get("/api/coins")
async def coins(): return {"name":"user-provided coin universe","count":len(load_coins()),"coins":load_coins()}

class PaperTrade(BaseModel):
    symbol: str
    timeframe: str = "1h"
    entry: float
    score: int = 0
    note: str = ""

@app.get("/api/paper-trades")
async def paper_trades():
    return {"trades": _load("paper_trades", []) or []}

@app.post("/api/paper-trades")
async def add_paper_trade(trade: PaperTrade):
    rows=_load("paper_trades",[]) or []
    row={"id":int(time.time()*1000),**trade.model_dump(),"created_at":time.time(),"status":"OPEN"}
    rows.insert(0,row);_save("paper_trades",rows[:200])
    return {"ok":True,"trade":row}
