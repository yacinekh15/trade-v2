"""Five independent spot/long strategy scanners for Trade-HHJ.

Strategies intentionally mirror the five strategy definitions agreed for this build:
1) EMA200 Cross
2) RSI Regular Bullish Divergence + EMA200
3) 5m VWAP + RSI Bullish Divergence + 15m EMA200
4) Bollinger Band Pullback + EMA200
5) Kijun-sen + SSL Channel

The scanner never places trades. Signals use closed candles only.
"""
from indicators_engine import (
    compute_ema_series, compute_rsi_series, compute_macd_series,
    compute_atr_series, compute_volume_ratio, compute_support_resistance,
    ema_relationship, compute_trend_speed_analyzer, compute_adaptive_expansion,
)
from config import (
    DIVERGENCE_MAX_SPACING, DIVERGENCE_MIN_RSI_DELTA, DIVERGENCE_MIN_SPACING,
    DIVERGENCE_P1_RSI_MAX, DIVERGENCE_USE_P1_RSI_FILTER, EMA_EQUAL_TOLERANCE_PCT,
)

STRATEGIES = {
    "EMA200_CROSS": "EMA200 Cross",
    "RSI_DIVERGENCE": "RSI Divergence + EMA200",
    "VWAP_RSI_15M_EMA200": "5m VWAP + RSI Divergence + 15m EMA200",
    "BB_PULLBACK": "Bollinger Pullback + EMA200",
    "KIJUN_SSL": "Kijun-sen + SSL Channel",
    "TWO_GREEN": "Two Indicators — Both Green",
}


def _r(v, n=8):
    return None if v is None else round(float(v), n)


def _base(symbol, timeframe, setup, ctx, conditions, signal=False, status=None, extra=None):
    if status is None:
        status = "SIGNAL" if signal else "WATCH"
    out = {
        "symbol": symbol, "timeframe": timeframe, "setup_type": setup,
        "direction": "LONG", "status": status, "signal": bool(signal),
        "score": int(ctx.get("context_score", 0)),
        "conditions": conditions, "reasons": [c["text"] for c in conditions],
        **ctx,
    }
    if extra:
        out.update(extra)
    return out


def _context(candles):
    closes = [c["close"] for c in candles]
    volumes = [c["volume"] for c in candles]
    e20 = compute_ema_series(closes, 20)
    e50 = compute_ema_series(closes, 50)
    e200 = compute_ema_series(closes, 200)
    rsi = compute_rsi_series(closes, 14)
    macd, macd_signal, hist = compute_macd_series(closes)
    atr = compute_atr_series(candles, 14)
    vr = compute_volume_ratio(volumes, 20)
    support, resistance = compute_support_resistance(candles, 20)
    i = len(candles) - 1
    required = (e20, e50, e200, rsi, macd, macd_signal, hist, atr)
    if any(x[i] is None for x in required) or vr is None:
        return None
    gap_state, gap = ema_relationship(e20[i], e50[i], EMA_EQUAL_TOLERANCE_PCT)
    price = closes[i]
    extension = (price - e20[i]) / atr[i] if atr[i] else 0
    score = 0
    if price > e200[i]: score += 25
    if e20[i] > e50[i]: score += 15
    if macd[i] > macd_signal[i]: score += 15
    if hist[i] > 0: score += 5
    if vr >= 1.5: score += 15
    elif vr >= 1.2: score += 10
    elif vr >= 1.0: score += 5
    if 40 <= rsi[i] <= 70: score += 10
    if resistance and price >= resistance: score += 10
    return {
        "price": _r(price),
        "signal_time": candles[i].get("close_time", candles[i].get("open_time")),
        "indicators": {
            "rsi": _r(rsi[i], 2), "ema20": _r(e20[i]), "ema50": _r(e50[i]),
            "ema200": _r(e200[i]), "ema_gap_pct": _r(gap, 4),
            "macd": _r(macd[i]), "macd_signal": _r(macd_signal[i]),
            "macd_histogram": _r(hist[i]), "atr": _r(atr[i]),
            "volume_ratio": _r(vr, 2), "support": _r(support),
            "resistance": _r(resistance), "extension_atr": _r(extension, 2),
        },
        "context_score": min(100, score), "ema_state": gap_state,
    }


def _cond(name, passed, text, state=None):
    return {"name": name, "passed": bool(passed), "state": state or ("PASS" if passed else "WAIT"), "text": text}


def _pivots(candles, rsi, left=2, right=2):
    out=[]
    for i in range(left, len(candles)-right):
        lows=[candles[j]["low"] for j in range(i-left, i+right+1)]
        if candles[i]["low"] == min(lows) and rsi[i] is not None:
            out.append(i)
    return out


def _bull_divergence(candles, rsi, latest_index, require_latest=True):
    pivots = _pivots(candles, rsi)
    candidates_p2 = [p for p in pivots if p + 2 <= latest_index]
    if require_latest:
        candidates_p2 = [p for p in candidates_p2 if latest_index - (p + 2) <= 2]
    for p2 in reversed(candidates_p2):
        for p1 in reversed([p for p in pivots if p < p2]):
            spacing=p2-p1
            if not (DIVERGENCE_MIN_SPACING <= spacing <= DIVERGENCE_MAX_SPACING): continue
            if candles[p2]["low"] >= candles[p1]["low"]: continue
            if rsi[p2] <= rsi[p1] + DIVERGENCE_MIN_RSI_DELTA: continue
            if DIVERGENCE_USE_P1_RSI_FILTER and rsi[p1] >= DIVERGENCE_P1_RSI_MAX: continue
            if any(candles[j]["low"] < candles[p2]["low"] for j in range(p1+1,p2)): continue
            return p1,p2
    return None,None


def ema200_cross(symbol, timeframe, candles):
    if len(candles) < 220: return None
    ctx=_context(candles)
    if not ctx:return None
    closes=[c["close"] for c in candles]; e200=compute_ema_series(closes,200)
    i=len(candles)-1; p=i-1
    cross=e200[p] is not None and e200[i] is not None and closes[p] <= e200[p] and closes[i] > e200[i]
    conditions=[
        _cond("previous_at_or_below", closes[p] <= e200[p], "Previous closed candle <= its EMA200"),
        _cond("current_above", closes[i] > e200[i], "Latest closed candle > its EMA200"),
    ]
    return _base(symbol,timeframe,"EMA200_CROSS",ctx,conditions,cross,extra={"entry_reference":_r(closes[i])})


def rsi_divergence(symbol,timeframe,candles):
    if len(candles)<220:return None
    ctx=_context(candles)
    if not ctx:return None
    closes=[x["close"] for x in candles]; rsi=compute_rsi_series(closes,14); e200=compute_ema_series(closes,200); i=len(candles)-1
    p1,p2=_bull_divergence(candles,rsi,i,True)
    trend=closes[i]>e200[i]
    div=p2 is not None
    signal=div and trend
    conditions=[
        _cond("price_above_ema200",trend,"Price is above EMA200"),
        _cond("lower_price_low",div,"P2 has a lower low than P1"),
        _cond("higher_rsi_low",div,"P2 RSI is higher than P1 RSI"),
        _cond("five_candle_confirmation",div,"The 5-candle pivot is confirmed"),
    ]
    entry=closes[i] if signal else None
    atr=ctx["indicators"]["atr"] or 0
    stop=candles[p2]["low"]-0.1*atr if p2 is not None else None
    risk=entry-stop if entry is not None and stop is not None else None
    return _base(symbol,timeframe,"RSI_DIVERGENCE",ctx,conditions,signal,extra={
        "p1_index":p1,"p2_index":p2,"divergence_confirmed":div,"entry_reference":_r(entry),
        "stop":_r(stop),"tp1":_r(entry+2*risk) if risk else None,"tp2":_r(entry+3*risk) if risk else None
    })


def _session_vwap(candles):
    # Session anchored using UTC date of each candle. The last candle's session is used.
    from datetime import datetime, timezone
    last=datetime.fromtimestamp(candles[-1]["open_time"]/1000,timezone.utc).date()
    pv=vol=0.0
    for c in reversed(candles):
        d=datetime.fromtimestamp(c["open_time"]/1000,timezone.utc).date()
        if d != last: break
        typical=(c["high"]+c["low"]+c["close"])/3
        pv += typical*c["volume"]; vol += c["volume"]
    return pv/vol if vol else None


def vwap_rsi_15m_ema200(symbol,timeframe,candles,trend_candles=None):
    if timeframe != "5m" or len(candles)<220 or not trend_candles:return None
    ctx=_context(candles)
    if not ctx:return None
    closes=[x["close"] for x in candles]; rsi=compute_rsi_series(closes,14); i=len(candles)-1
    tcloses=[x["close"] for x in trend_candles]; te200=compute_ema_series(tcloses,200); ti=len(trend_candles)-1
    vwap=_session_vwap(candles); p1,p2=_bull_divergence(candles,rsi,i,True)
    trend=tcloses[ti]>te200[ti]
    near=vwap is not None and abs(closes[i]-vwap)/vwap <= 0.005
    div=p2 is not None
    signal=trend and div and near
    conditions=[
        _cond("15m_above_ema200",trend,"15m price is above 15m EMA200"),
        _cond("bullish_divergence",div,"5m price lower low + RSI higher low"),
        _cond("near_vwap",near,"5m close is within 0.5% of session VWAP"),
        _cond("confirmation_close",True,"Signal is evaluated on the latest closed 5m candle"),
    ]
    atr=ctx["indicators"]["atr"] or 0; entry=closes[i] if signal else None
    stop=candles[p2]["low"]-0.1*atr if p2 is not None else None
    risk=entry-stop if entry is not None and stop is not None else None
    extra={"vwap":_r(vwap),"trend_15m":{"price":_r(tcloses[ti]),"ema200":_r(te200[ti])},
           "p1_index":p1,"p2_index":p2,"entry_reference":_r(entry),"stop":_r(stop),
           "tp2":_r(entry+2*risk) if risk else None}
    return _base(symbol,timeframe,"VWAP_RSI_15M_EMA200",ctx,conditions,signal,extra=extra)


def bb_pullback(symbol,timeframe,candles):
    if len(candles)<220:return None
    ctx=_context(candles)
    if not ctx:return None
    closes=[x["close"] for x in candles]; i=len(candles)-1; p=i-1
    e200=compute_ema_series(closes,200)
    mid=compute_ema_series(closes,20)
    vals=closes[max(0,i-30):i+1]
    mean=mid[i]
    variance=sum((x-mean)**2 for x in vals)/len(vals)
    sd=variance**0.5
    lower=mean-2*sd
    prev_mean=mid[p]; prev_vals=closes[max(0,p-30):p+1]; prev_sd=(sum((x-prev_mean)**2 for x in prev_vals)/len(prev_vals))**0.5
    prev_lower=prev_mean-2*prev_sd
    trend=closes[i]>e200[i]
    outside=closes[p]<prev_lower
    reentry=closes[i]>=lower and closes[i]<mean
    signal=trend and outside and reentry
    conditions=[
        _cond("above_ema200",trend,"Price is above EMA200"),
        _cond("closed_below_lower_bb",outside,"Previous closed candle closed below the lower Bollinger Band"),
        _cond("closed_back_inside",reentry,"Latest closed candle closed back inside the lower band"),
    ]
    atr=ctx["indicators"]["atr"] or 0
    swing=min(x["low"] for x in candles[max(0,i-5):i+1])
    entry=closes[i] if signal else None; stop=swing-0.1*atr if signal else None; risk=entry-stop if entry and stop else None
    return _base(symbol,timeframe,"BB_PULLBACK",ctx,conditions,signal,extra={"bb_mid":_r(mean),"bb_lower":_r(lower),"bb_upper":_r(mean+2*sd),"entry_reference":_r(entry),"stop":_r(stop),"tp2":_r(entry+2*risk) if risk else None})


def _kijun(candles,period=26):
    if len(candles)<period:return None
    hi=max(x["high"] for x in candles[-period:]); lo=min(x["low"] for x in candles[-period:]); return (hi+lo)/2


def _ssl_series(candles,period=22):
    # Standard SSL Channel implementation: SMA(high), SMA(low), HLV state.
    hs=[x["high"] for x in candles]; ls=[x["low"] for x in candles]; closes=[x["close"] for x in candles]
    sma_h=[];sma_l=[]
    for i in range(len(candles)):
        if i+1<period:sma_h.append(None);sma_l.append(None)
        else:sma_h.append(sum(hs[i-period+1:i+1])/period);sma_l.append(sum(ls[i-period+1:i+1])/period)
    hlv=[None]*len(candles); up=[None]*len(candles); dn=[None]*len(candles)
    for i in range(len(candles)):
        if sma_h[i] is None:continue
        if closes[i]>sma_h[i]: hlv[i]=1
        elif closes[i]<sma_l[i]: hlv[i]=-1
        elif i>0: hlv[i]=hlv[i-1]
        if hlv[i]==-1: up[i]=sma_l[i]; dn[i]=sma_h[i]
        elif hlv[i]==1: up[i]=sma_h[i]; dn[i]=sma_l[i]
        else: up[i]=sma_h[i]; dn[i]=sma_l[i]
    return up,dn


def kijun_ssl(symbol,timeframe,candles):
    if len(candles)<220:return None
    ctx=_context(candles); 
    if not ctx:return None
    closes=[x["close"] for x in candles]; i=len(candles)-1;p=i-1
    kij=_kijun(candles,26); kij_prev=_kijun(candles[:-1],26)
    up,dn=_ssl_series(candles,22)
    if up[i] is None or dn[i] is None:return None
    cross=up[p] is not None and dn[p] is not None and up[p]<=dn[p] and up[i]>dn[i]
    above=closes[i]>kij
    signal=above and cross
    # A cross below Kijun invalidates the bullish setup.
    invalid=closes[i]<kij
    conditions=[
        _cond("above_kijun",above,"Price is above Kijun-sen 26"),
        _cond("ssl_bullish_cross",cross,"SSL green/upper line crossed above red/lower line"),
        _cond("close_confirmation",True,"Latest candle is closed; signal is confirmed at candle close"),
        _cond("not_below_kijun",not invalid,"SSL breakout is not invalidated below Kijun"),
    ]
    swing=min(x["low"] for x in candles[max(0,i-10):i+1]); atr=ctx["indicators"]["atr"] or 0
    entry=closes[i] if signal else None; stop=swing-0.1*atr if signal else None; risk=entry-stop if entry and stop else None
    return _base(symbol,timeframe,"KIJUN_SSL",ctx,conditions,signal,extra={"kijun":_r(kij),"ssl_green":_r(up[i]),"ssl_red":_r(dn[i]),"ssl_cross":cross,"entry_reference":_r(entry),"stop":_r(stop),"tp2":_r(entry+2*risk) if risk else None,"trailing_rule":"After +2R, trail with red SSL line; exit on close below red SSL"})


def two_green(symbol, timeframe, candles):
    if len(candles) < 220:
        return None
    ts = compute_trend_speed_analyzer(candles, max_length=50, accel_multiplier=5.0)
    ae = compute_adaptive_expansion(candles, ma_type="EMA", ma_length=20, atr_length=14, mult1=1.0)
    if not ts or not ae:
        return None
    both = bool(ts["green"] and ae["green"])
    ts_green = bool(ts["green"])
    ae_green = bool(ae["green"])
    if both:
        status = "BOTH GREEN"
        status_text = "Both indicators are green"
    elif ts_green:
        status = "TREND SPEED ONLY"
        status_text = "Trend Speed Analyzer is green; Expansion Bands is not green"
    elif ae_green:
        status = "EXPANSION BANDS ONLY"
        status_text = "Expansion Bands is green; Trend Speed Analyzer is not green"
    else:
        status = "NEITHER GREEN"
        status_text = "Neither indicator is green"
    ctx = {
        "price": _r(candles[-1]["close"]),
        "signal_time": candles[-1].get("close_time", candles[-1].get("open_time")),
        "context_score": 0,
        "indicators": {
            "trend_speed_dynamic_ema": _r(ts["dynamic_ema"]),
            "trend_speed_wma2": _r(ts["wma2"]),
            "trend_speed": _r(ts["trend_speed"]),
            "trend_speed_green": ts_green,
            "expansion_base_ma": _r(ae["base_ma"]),
            "expansion_atr14": _r(ae["atr"]),
            "expansion_upper_zone3": _r(ae["upper_zone3"]),
            "expansion_lower_zone3": _r(ae["lower_zone3"]),
            "expansion_green": ae_green,
        },
    }
    conditions = [
        _cond("trend_speed_green", ts_green, "Trend Speed Analyzer is green" if ts_green else "Trend Speed Analyzer is not green"),
        _cond("expansion_bands_green", ae_green, "Adaptive Trend Expansion Bands is green" if ae_green else "Adaptive Trend Expansion Bands is not green"),
    ]
    return _base(symbol, timeframe, "TWO_GREEN", ctx, conditions, signal=both, status=status, extra={
        "strategy_status": status, "status_text": status_text,
        "indicator_1": {"name": "Trend Speed Analyzer", "green": ts_green},
        "indicator_2": {"name": "Adaptive Trend Expansion Bands", "green": ae_green},
    })


def scan_symbol(symbol,timeframe,candles,strategy="ALL",trend_candles=None):
    funcs={
        "EMA200_CROSS":ema200_cross,
        "RSI_DIVERGENCE":rsi_divergence,
        "VWAP_RSI_15M_EMA200":vwap_rsi_15m_ema200,
        "BB_PULLBACK":bb_pullback,
        "KIJUN_SSL":kijun_ssl,
        "TWO_GREEN":two_green,
    }
    keys=list(funcs) if strategy=="ALL" else [strategy]
    out=[]
    for key in keys:
        try:
            if key=="VWAP_RSI_15M_EMA200": r=funcs[key](symbol,timeframe,candles,trend_candles)
            else: r=funcs[key](symbol,timeframe,candles)
            if r: out.append(r)
        except Exception as e:
            out.append({"symbol":symbol,"timeframe":timeframe,"setup_type":key,"status":"ERROR","signal":False,"score":0,"reasons":[f"Strategy error: {e}"],"indicators":{}})
    return out
