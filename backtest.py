"""Walk-forward backtesting for the same entry engine used by the scanner.

No look-ahead: the signal is computed from a closed candle, entry is the next
candle open, and TP/SL are evaluated only on candles after entry.
"""
from collections import defaultdict
from setup_score import score_symbol, TRADE_SETUPS


def _trade_levels(result, entry):
    analysis = result.get("analysis", {})
    sl = float(analysis.get("sl") or 0)
    tps = analysis.get("tp") or []
    tp1 = float(tps[0]["level"]) if tps else 0
    if sl <= 0 or tp1 <= entry:
        return None
    risk = entry - sl
    if risk <= 0:
        return None
    return sl, tp1, risk


def _max_excursion(candles, start, end, entry):
    highs = [float(c["high"]) for c in candles[start:end]]
    lows = [float(c["low"]) for c in candles[start:end]]
    mfe = ((max(highs) - entry) / entry * 100) if highs else 0
    mae = ((min(lows) - entry) / entry * 100) if lows else 0
    return mfe, mae


def _summary(trades, skipped=0):
    wins = [t for t in trades if t["outcome"] == "TARGET"]
    losses = [t for t in trades if t["outcome"] in {"STOP", "STOP_AND_TARGET_SAME_CANDLE"}]
    timeouts = [t for t in trades if t["outcome"] == "TIMEOUT"]
    r_values = [float(t["r_multiple"]) for t in trades]
    gross_profit = sum(max(0.0, x) for x in r_values)
    gross_loss = abs(sum(min(0.0, x) for x in r_values))
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for r in r_values:
        equity += r
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
    return {
        "signals": len(trades) + skipped,
        "entries": len(trades),
        "skipped_no_fill": skipped,
        "wins": len(wins),
        "losses": len(losses),
        "timeouts": len(timeouts),
        "win_rate_pct": round(len(wins) / len(trades) * 100, 2) if trades else 0,
        "total_pnl_pct": round(sum(float(t["pnl_pct"]) for t in trades), 4),
        "avg_pnl_pct": round(sum(float(t["pnl_pct"]) for t in trades) / len(trades), 4) if trades else 0,
        "avg_r": round(sum(r_values) / len(r_values), 4) if r_values else 0,
        "expectancy_r": round(sum(r_values) / len(r_values), 4) if r_values else 0,
        "profit_factor": round(gross_profit / gross_loss, 3) if gross_loss else (None if not gross_profit else "inf"),
        "max_drawdown_r": round(max_dd, 4),
        "avg_hold_bars": round(sum(t["hold_bars"] for t in trades) / len(trades), 2) if trades else 0,
        "avg_mfe_pct": round(sum(t["mfe_pct"] for t in trades) / len(trades), 3) if trades else 0,
        "avg_mae_pct": round(sum(t["mae_pct"] for t in trades) / len(trades), 3) if trades else 0,
    }


def backtest_candles(symbol, candles, timeframe="1h", min_score=70, max_hold=24):
    """Backtest all trade setups with a closed-candle signal and next-open entry."""
    trades = []
    skipped_no_fill = 0
    warmup = 205
    for i in range(warmup, len(candles) - 2):
        # score_symbol removes the last candle, so passing through i+1 makes
        # candle i the closed signal candle. The i+1 candle is not used by the
        # indicator engine; it is the future entry candle.
        result = score_symbol(symbol, candles[:i + 2])
        if not result:
            continue
        if result.get("score", 0) < min_score or result.get("setup_type") not in TRADE_SETUPS:
            continue
        if not result.get("qualified"):
            continue

        entry_c = candles[i + 1]
        entry = float(entry_c["open"])
        a = result.get("analysis", {})
        zone = a.get("entry", {})
        low = float(zone.get("low") or entry)
        high = float(zone.get("high") or entry)
        atr = float(result.get("indicators", {}).get("atr") or 0)
        # Do not pretend a gap/pump is an entry. Allow a small volatility band
        # below the zone, but reject an open materially above the planned zone.
        if entry > high + max(0.5 * atr, entry * 0.003):
            skipped_no_fill += 1
            continue

        levels = _trade_levels(result, entry)
        if not levels:
            continue
        stop, target, risk = levels
        outcome = "TIMEOUT"
        exit_price = float(candles[min(i + max_hold, len(candles) - 1)]["close"])
        exit_i = min(i + max_hold, len(candles) - 1)
        for j in range(i + 1, min(len(candles), i + 1 + max_hold)):
            c = candles[j]
            hit_stop = float(c["low"]) <= stop
            hit_target = float(c["high"]) >= target
            if hit_stop and hit_target:
                outcome = "STOP_AND_TARGET_SAME_CANDLE"
                exit_price = stop
                exit_i = j
                break
            if hit_stop:
                outcome = "STOP"
                exit_price = stop
                exit_i = j
                break
            if hit_target:
                outcome = "TARGET"
                exit_price = target
                exit_i = j
                break

        pnl_pct = (exit_price - entry) / entry * 100
        r_multiple = (exit_price - entry) / risk
        mfe, mae = _max_excursion(candles, i + 1, min(len(candles), i + 1 + max_hold), entry)
        trades.append({
            "symbol": symbol,
            "timeframe": timeframe,
            "signal_index": i,
            "signal_time": candles[i]["open_time"],
            "entry_time": entry_c["open_time"],
            "entry": entry,
            "entry_zone": {"low": low, "high": high},
            "target": target,
            "stop": stop,
            "exit": exit_price,
            "exit_time": candles[exit_i]["open_time"],
            "hold_bars": exit_i - i,
            "outcome": outcome,
            "pnl_pct": round(pnl_pct, 4),
            "r_multiple": round(r_multiple, 4),
            "mfe_pct": round(mfe, 3),
            "mae_pct": round(mae, 3),
            "score": result["score"],
            "entry_quality": result.get("entry_quality", 0),
            "setup_type": result["setup_type"],
        })

    summary = _summary(trades, skipped_no_fill)
    by_setup = defaultdict(list)
    for trade in trades:
        by_setup[trade["setup_type"]].append(trade)
    setup_summary = {k: _summary(v) for k, v in sorted(by_setup.items())}
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "max_hold": max_hold,
        "trades": trades,
        "summary": summary,
        "setup_breakdown": setup_summary,
    }
