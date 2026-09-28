"""No-look-ahead backtesting for the scanner's long-only setups."""
from collections import defaultdict
from setup_score import score_symbol,TRADE_SETUPS
from indicators_engine import compute_ema

def _summary(trades,skipped=0):
    r=[x['r_multiple'] for x in trades]; wins=[x for x in trades if x['outcome']=='TARGET']; losses=[x for x in trades if x['outcome'].startswith('STOP')]
    eq=peak=dd=0
    for x in r: eq+=x; peak=max(peak,eq); dd=max(dd,peak-eq)
    gp=sum(max(0,x) for x in r); gl=abs(sum(min(0,x) for x in r))
    return {'signals':len(trades)+skipped,'entries':len(trades),'wins':len(wins),'losses':len(losses),'timeouts':len(trades)-len(wins)-len(losses),'win_rate_pct':round(len(wins)/len(trades)*100,2) if trades else 0,'avg_r':round(sum(r)/len(r),4) if r else 0,'expectancy_r':round(sum(r)/len(r),4) if r else 0,'profit_factor':round(gp/gl,3) if gl else None,'max_drawdown_r':round(dd,4),'avg_duration':round(sum(x['hold_bars'] for x in trades)/len(trades),2) if trades else 0}

def backtest_candles(symbol,candles,timeframe='1h',max_hold=200):
    trades=[]; skipped=0; fees=0.001
    # Signal at N uses candles through N only; entry is N+1 open.
    for n in range(249,len(candles)-1):
        r=score_symbol(symbol,candles[:n+1],0,timeframe)
        if not r or r['setup_type'] not in TRADE_SETUPS or not r['qualified']: continue
        entry=float(candles[n+1]['open']); stop=float(r['analysis']['sl']); risk=entry-stop
        if risk<=0: continue
        # Entry gap is accepted; costs are charged per side.
        target=entry+2*risk if r['setup_type']!='EMA200_RECLAIM' else None
        stage2=False; trail=stop; outcome='TIMEOUT'; exit_price=float(candles[min(len(candles)-1,n+max_hold)]['close']); exit_i=min(len(candles)-1,n+max_hold)
        for j in range(n+1,min(len(candles),n+1+max_hold)):
            c=candles[j]
            if not stage2 and r['setup_type']=='EMA200_RECLAIM':
                if c['low']<=trail: outcome='STOP'; exit_price=trail; exit_i=j; break
                one_r=c['close']>=entry+risk; e200=compute_ema([x['close'] for x in candles[:j+1]],200)
                if one_r and e200 is not None and e200>=entry: stage2=True; trail=e200
            elif r['setup_type']!='EMA200_RECLAIM':
                if c['low']<=stop and target and c['high']>=target: outcome='STOP'; exit_price=stop; exit_i=j; break
                if c['low']<=stop: outcome='STOP'; exit_price=stop; exit_i=j; break
                if target and c['high']>=target: outcome='TARGET'; exit_price=target; exit_i=j; break
            else:
                if stage2:
                    e200=compute_ema([x['close'] for x in candles[:j+1]],200)
                    if e200 is not None: trail=e200
                    if e200 is not None and c['close']<e200: outcome='TRAIL_EXIT'; exit_price=candles[j+1]['open'] if j+1<len(candles) else c['close']; exit_i=min(j+1,len(candles)-1); break
        gross=(exit_price-entry)/entry; net=gross-2*fees; rmult=(exit_price-entry)/risk
        trades.append({'symbol':symbol,'timeframe':timeframe,'signal_time':candles[n]['open_time'],'entry':entry,'stop':stop,'target':target,'exit':exit_price,'exit_time':candles[exit_i]['open_time'],'hold_bars':exit_i-n,'outcome':outcome,'pnl_pct':round(net*100,4),'r_multiple':round(rmult,4),'setup_type':r['setup_type'],'score':r['score']})
    by=defaultdict(list)
    for t in trades: by[t['setup_type']].append(t)
    return {'symbol':symbol,'timeframe':timeframe,'trades':trades,'summary':_summary(trades,skipped),'setup_breakdown':{k:_summary(v) for k,v in by.items()}}
