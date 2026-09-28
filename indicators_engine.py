"""Auditable technical-analysis calculations using only standard Python."""
from datetime import datetime, timezone

def compute_ema_series(values, period):
    if len(values)<period: return [None]*len(values)
    out=[None]*(period-1); prev=sum(values[:period])/period; out.append(prev)
    k=2/(period+1)
    for v in values[period:]: prev=(v-prev)*k+prev; out.append(prev)
    return out

def compute_ema(values, period):
    s=compute_ema_series(values,period); return s[-1] if s else None

def compute_rsi_series(closes, period=14):
    out=[None]*len(closes)
    if len(closes)<period+1:return out
    gains=[max(closes[i]-closes[i-1],0) for i in range(1,len(closes))]
    losses=[max(closes[i-1]-closes[i],0) for i in range(1,len(closes))]
    ag=sum(gains[:period])/period; al=sum(losses[:period])/period
    def val(): return 100.0 if al==0 else 100-100/(1+ag/al)
    out[period]=val()
    for i in range(period,len(gains)):
        ag=(ag*(period-1)+gains[i])/period; al=(al*(period-1)+losses[i])/period; out[i+1]=val()
    return out

def compute_rsi(closes,period=14):
    s=compute_rsi_series(closes,period); return s[-1] if s else None

def compute_macd_series(closes,fast=12,slow=26,signal=9):
    ef=compute_ema_series(closes,fast); es=compute_ema_series(closes,slow)
    line=[(a-b if a is not None and b is not None else None) for a,b in zip(ef,es)]
    valid=[x for x in line if x is not None]; sig_valid=compute_ema_series(valid,signal)
    sig=[]; hist=[]; vi=0
    for x in line:
        if x is None: sig.append(None); hist.append(None)
        else:
            s=sig_valid[vi]; sig.append(s); hist.append(x-s if s is not None else None); vi+=1
    return line,sig,hist

def compute_atr_series(candles,period=14):
    out=[None]*len(candles)
    if len(candles)<period+1:return out
    trs=[]
    for i in range(1,len(candles)):
        c=candles[i]; p=candles[i-1]['close']; trs.append(max(c['high']-c['low'],abs(c['high']-p),abs(c['low']-p)))
    atr=sum(trs[:period])/period; out[period]=atr
    for i in range(period,len(trs)):
        atr=(atr*(period-1)+trs[i])/period; out[i+1]=atr
    return out

def compute_volume_ratio_series(volumes,lookback=20):
    out=[None]*len(volumes)
    for i in range(lookback,len(volumes)):
        avg=sum(volumes[i-lookback:i])/lookback; out[i]=volumes[i]/avg if avg else None
    return out

def compute_session_vwap(candles):
    """UTC-session anchored VWAP, reset at each UTC date."""
    out=[]; day=None; pv=0.0; vv=0.0
    for c in candles:
        d=datetime.fromtimestamp(c['open_time']/1000,tz=timezone.utc).date()
        if d!=day: day=d; pv=0.0; vv=0.0
        typical=(c['high']+c['low']+c['close'])/3; pv+=typical*c['volume']; vv+=c['volume']; out.append(pv/vv if vv else None)
    return out

def compute_zones(candles,lookback=20):
    if len(candles)<lookback+1:return None,None
    w=candles[-(lookback+1):-1]
    support=min(x['low'] for x in w); resistance=max(x['high'] for x in w)
    width=max((max(x['high'] for x in w)-min(x['low'] for x in w))*0.01,1e-12)
    return {'low':support,'high':support+width},{'low':resistance-width,'high':resistance}
