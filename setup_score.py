"""Setup detection, risk validation and transparent 0-100 scoring.
No signal is a probability or guarantee. All decisions use closed candles only.
"""
from indicators_engine import *
from config import MAX_RISK_PCT,MIN_STOP_ATR,EXTENSION_ATR,ALERT_MIN_SCORE

ALL_SETUPS={
 'BULLISH_BREAKOUT','EARLY_MOMENTUM_SURGE','BULLISH_PULLBACK','SUPPORT_BOUNCE',
 'EMA_BULLISH_CROSSOVER','EMA200_RECLAIM','RSI_DIVERGENCE_PULLBACK','BULLISH_REVERSAL',
 'EMA20_50_CONVERGENCE','VOLUME_EXPANSION','FAKEOUT'
}
TRADE_SETUPS={'BULLISH_BREAKOUT','EARLY_MOMENTUM_SURGE','BULLISH_PULLBACK','SUPPORT_BOUNCE','EMA_BULLISH_CROSSOVER','EMA200_RECLAIM','RSI_DIVERGENCE_PULLBACK','BULLISH_REVERSAL'}
PIVOT_LEFT=PIVOT_RIGHT=2

def _r(v,d=8): return None if v is None else round(float(v),d)

def _pivots(candles,rsi,left=2,right=2):
    out=[]
    for i in range(left,len(candles)-right):
        lo=candles[i]['low']
        if all(lo<candles[j]['low'] for j in range(i-left,i)) and all(lo<=candles[j]['low'] for j in range(i+1,i+right+1)) and rsi[i] is not None: out.append(i)
    return out

def _divergence(candles,rsi,min_delta=1.0):
    piv=_pivots(candles,rsi)
    if len(piv)<2:return None
    p2=piv[-1]
    if len(candles)-1-p2>2:return None
    for p1 in reversed(piv[:-1]):
        gap=p2-p1
        if gap<5: continue
        if gap>30: break
        if candles[p2]['low']<candles[p1]['low'] and rsi[p2]>rsi[p1]+min_delta:
            if min(c['low'] for c in candles[p1+1:p2])>=candles[p2]['low']:
                if rsi[p1]<45:
                    return {'p1':p1,'p2':p2,'price_1':candles[p1]['low'],'price_2':candles[p2]['low'],'rsi_1':rsi[p1],'rsi_2':rsi[p2]}
    return None

def _five_pattern(candles):
    # Source specification: 2 candles before pivot + pivot + 2 after; signal=N=i+2.
    # At N the pivot is known and no future candle is used. The confirmation is the
    # confirmed fractal itself, not an invented directional candle rule.
    return len(candles)>=5

def _risk(price,stop,atr):
    R=price-stop
    if price<=0 or stop<=0 or R<=0:return False,['invalid stop'],R
    reasons=[]
    if R/price>MAX_RISK_PCT: reasons.append(f'risk {R/price:.2%} exceeds {MAX_RISK_PCT:.0%}')
    if atr and R<MIN_STOP_ATR*atr: reasons.append('stop is tighter than 0.5 ATR')
    return not reasons,reasons,R

def score_symbol(symbol,candles,quote_volume=0,timeframe='1h',mtf=None):
    if not candles or len(candles)<250:return None
    # Closed-only: the data client already drops forming candles, but retain a defensive check.
    closed=[c for c in candles if c.get('close_time',0)<=__import__('time').time()*1000]
    if len(closed)<250:return None
    cs=[c['close'] for c in closed]; highs=[c['high'] for c in closed]; vols=[c['volume'] for c in closed]
    ema20=compute_ema_series(cs,20); ema50=compute_ema_series(cs,50); ema200=compute_ema_series(cs,200); rsi=compute_rsi_series(cs,14)
    macd,macd_sig,macd_hist=compute_macd_series(cs); atr=compute_atr_series(closed); vr=compute_volume_ratio_series(vols); vwap=compute_session_vwap(closed); support,resistance=compute_zones(closed)
    i=len(closed)-1; price=cs[i]; e20=ema20[i]; e50=ema50[i]; e200=ema200[i]; a=atr[i]; rv=rsi[i]; hist=macd_hist[i]; prev_hist=macd_hist[i-1] if i else None
    ema_cross=i>0 and ema20[i-1] is not None and ema50[i-1] is not None and ema20[i-1]<=ema50[i-1] and e20>e50
    gap=abs(e20-e50)/e50 if e50 else 1; convergence=gap<=0.0005
    below2=cs[i-1]<ema200[i-1] and cs[i-2]<ema200[i-2]
    reclaim=below2 and price>e200
    div=_divergence(closed,rsi)
    div_valid=bool(div and price>e200 and _five_pattern(closed))
    support_bounce=bool(support and closed[i]['low']<=support['high'] and price>closed[i]['open'] and rv is not None and rv>45)
    breakout=bool(resistance and price>resistance['high'] and (vr[i] or 0)>=1.5 and price>e20>e50)
    surge=bool(vr[i] and vr[i]>=1.5 and price>closed[i]['open'] and e20>e50 and hist is not None and prev_hist is not None and hist>prev_hist and price-e20 <= (a or 1)*3)
    pullback=bool(price>e200 and e20>e50 and (closed[i]['low']<=e20 or (support and closed[i]['low']<=support['high'])) and price>closed[i]['open'])
    reversal=bool(price>e200 and reclaim and (vr[i] or 0)>=1.2 and hist is not None and hist>prev_hist if prev_hist is not None else False)
    fakeout=bool(resistance and highs[i-1]>resistance['high'] and price<resistance['high'])
    extension=bool(a and (price-e20)/a>EXTENSION_ATR)
    setup=None; evidence=[]
    if reclaim: setup='EMA200_RECLAIM'; evidence=['2 prior closes below their own EMA200','closed candle reclaimed EMA200']
    elif div_valid: setup='RSI_DIVERGENCE_PULLBACK'; evidence=['regular bullish RSI divergence','pivot confirmation (5-candle fractal)','price above EMA200']
    elif breakout: setup='BULLISH_BREAKOUT'; evidence=['closed resistance break','volume >= 1.5x','supportive EMA structure']
    elif surge: setup='EARLY_MOMENTUM_SURGE'; evidence=['strong closed-candle momentum','volume >= 1.5x','EMA20 > EMA50','MACD histogram strengthening','not >3 ATR extended']
    elif pullback: setup='BULLISH_PULLBACK'; evidence=['established uptrend','pullback to EMA/support','bullish close']
    elif support_bounce: setup='SUPPORT_BOUNCE'; evidence=['reaction at support zone','bullish confirmation']
    elif ema_cross: setup='EMA_BULLISH_CROSSOVER'; evidence=['EMA20 crossed above EMA50']
    elif reversal: setup='BULLISH_REVERSAL'; evidence=['multiple independent bullish pieces of evidence']
    elif convergence: setup='EMA20_50_CONVERGENCE'; evidence=['EMA20/EMA50 distance <= 0.05%'];
    elif (vr[i] or 0)>=1.2: setup='VOLUME_EXPANSION'; evidence=[f'volume ratio {vr[i]:.2f}x']
    elif fakeout: setup='FAKEOUT'; evidence=['breakout failed back below resistance']
    else: setup='NO_SIGNAL'
    # stop logic per setup
    if setup=='EMA200_RECLAIM':
        run=[]; j=i-1
        while j>=0 and cs[j]<ema200[j] and len(run)<60: run.append(j); j-=1
        stop=min(closed[k]['low'] for k in run) if run else min(c['low'] for c in closed[-12:])
    elif div: stop=closed[div['p2']]['low']-(a or price*0.01)*0.1
    else: stop=min(c['low'] for c in closed[-12:])
    valid,risk_reasons,R=_risk(price,stop,a or 0)
    tp2=price+2*R if R>0 else None; tp3=price+3*R if R>0 else None
    score_parts={'trend':20 if price>e200 else 0,'momentum':15 if ((hist is not None and hist>0) or div_valid) else 0,'volume':15 if (vr[i] or 0)>=1.2 else 0,'structure':15 if (breakout or support_bounce or pullback or reclaim or div_valid) else 0,'mtf':15 if (not mtf or mtf.get('bullish_count',0)>=1) else 0,'setup_quality':15 if setup in TRADE_SETUPS else 0,'risk_volatility':5 if valid else 0}
    penalty=0
    if extension: penalty+=35
    if mtf and mtf.get('strong_contradiction'): penalty+=25
    if quote_volume and quote_volume<5000000: penalty+=20
    score=max(0,min(100,sum(score_parts.values())-penalty))
    telegram_ok=setup in TRADE_SETUPS and valid and not extension and not (mtf and mtf.get('strong_contradiction')) and score>=ALERT_MIN_SCORE and (vr[i] or 0)>=1.2
    qualified=setup in TRADE_SETUPS and valid and not extension
    return {'symbol':symbol,'timeframe':timeframe,'direction':'LONG' if qualified else 'NONE','setup_type':setup,'qualified':qualified,'telegram_eligible':telegram_ok,'score':score,'price':_r(price),'quote_volume':quote_volume,'signal_time':closed[i]['open_time'],'reasons':evidence,'rejection_reasons':risk_reasons if not valid else ([] if qualified else ['setup is informational or lacks full confirmation']),'indicators':{'ema20':_r(e20),'ema50':_r(e50),'ema200':_r(e200),'rsi':_r(rv,2),'macd':_r(macd[i]),'macd_signal':_r(macd_sig[i]),'macd_histogram':_r(hist),'atr':_r(a),'volume_ratio':_r(vr[i],2),'vwap':_r(vwap[i]),'support_zone':support,'resistance_zone':resistance,'ema20_50_convergence':convergence,'ema_bullish_crossover':ema_cross,'extension':extension,'extension_atr':_r((price-e20)/a,2) if a else None,'divergence':div,'two_closes_below_ema200':below2,'ema200_reclaim':reclaim},'analysis':{'bias':'LONG' if qualified else 'WATCH','entry':{'low':_r(price),'high':_r(price)},'sl':_r(stop),'tp':[{'level':_r(tp2),'rr':2},{'level':_r(tp3),'rr':3}],'risk_pct':_r(R/price*100,2) if price else None,'invalidation':f'Long thesis invalid below {_r(stop)}.','counter_argument':'A setup can fail; score measures rule alignment, not probability.','historical':'Not a backtest result.','score_breakdown':score_parts,'penalties':{'extension':35 if extension else 0,'contradiction':25 if mtf and mtf.get('strong_contradiction') else 0,'illiquidity':20 if quote_volume and quote_volume<5000000 else 0},'total_score':score}}
