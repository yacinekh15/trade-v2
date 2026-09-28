# Trade-HHJ — Manual Binance Spot Scanner

This project follows the supplied Trade-HHJ specification. It is decision-support only and never places real trades.

## Core behavior
- Binance **Spot** public data only.
- `coins.txt` is the authoritative user-provided universe.
- Manual **SCAN NOW** only. No cron and no automatic scanner.
- Long-side setups and caution/watch states; no short execution logic.
- Closed candles only; no look-ahead in setup detection/backtesting.
- Liquidity filter defaults to 5M USDT 24h quote volume.
- Indicators: EMA20/50/200, RSI14 Wilder, MACD, ATR14, volume ratio, support/resistance zones, session VWAP.
- Setups A/B exactly follow the supplied 200 EMA reclaim and RSI divergence rules; the other documented long/watch setups are also implemented.
- Transparent 0–100 alignment score, never a probability.
- Selective Telegram is server-side and optional.
- Paper trades are stored; no real orders exist.
- Backtesting enters at next candle open and applies fees; Setup A uses EMA200 trailing behavior.

## Security
Set `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `UPSTASH_REDIS_REST_URL`, `UPSTASH_REDIS_REST_TOKEN`, and optional `SCAN_SECRET` as server-side environment variables.
