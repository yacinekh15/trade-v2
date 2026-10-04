# Trade-HHJ — Multi-Strategy Spot Scanner

This build contains **exactly five independent strategy scanners**. The scanner is decision-support only and never places real orders.

## Strategies

1. **EMA200 Cross** — previous closed candle close <= its EMA200, and the latest closed candle close > its EMA200. This cross is the signal by itself; RSI, MACD, volume, liquidity, score, MTF and divergence do not gate it.
2. **RSI Regular Bullish Divergence + EMA200** — long-only regular bullish RSI divergence with the EMA200 trend filter and confirmed 5-candle pivot interpretation.
3. **5m VWAP + RSI Bullish Divergence + 15m EMA200** — 5m execution, 15m EMA200 trend filter, bullish RSI divergence near session VWAP.
4. **Bollinger Band Pullback + EMA200** — price above EMA200, close below the lower Bollinger Band, then close back inside the lower band.
5. **Kijun-sen + SSL Channel** — price above Kijun 26, bullish SSL cross confirmed on candle close, with the red SSL line available as the trailing stop after +2R.

Short setups are excluded. No automatic trading is included.

## Core behavior

- Uses the **242-symbol `coins.txt`** supplied with the project.
- Binance **Spot** public market data only.
- Closed candles are used for signal confirmation.
- Supported timeframes: 5m / 15m / 1h / 4h / 1d.
- Browser-driven batches prevent the full universe from being scanned in one Vercel invocation.
- Optional browser auto-scan every 60 seconds while the page is open. No server cron is used.
- Website alerts are generated for full strategy setups.
- Telegram sending remains optional and controlled by the existing Telegram environment variables and website toggle.
- Informational context metrics do not replace the individual strategy rules.
- TradingView and Binance links are included in result details.
- Paper trades can use the existing Upstash configuration; no real trading API is included.

## Existing environment configuration

The existing configuration was intentionally preserved. In particular, this build does **not** replace, regenerate, or hard-code the existing:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `TELEGRAM_ENABLED_DEFAULT`
- `UPSTASH_REDIS_REST_URL`
- `UPSTASH_REDIS_REST_TOKEN`
- `SCAN_SECRET`
- existing scanner threshold environment variables

The scanner reads those values from the deployment environment exactly as before.

## Coin universe

`coins.txt` is treated as the **user-provided coin universe**. The software does not independently certify assets as halal and does not add coins automatically.

## Deployment

Deploy the project as a fresh version of this folder. After deployment, open the site and verify that the strategy selector contains exactly:

- EMA200 Cross
- RSI Divergence + EMA200
- 5m VWAP + RSI Divergence + 15m EMA200
- Bollinger Pullback + EMA200
- Kijun-sen + SSL Channel


## Private Two-Green Strategy

Added `TWO_GREEN` as a separate strategy module. It scans the user-provided coin universe using closed Binance Spot candles.

- Indicator 1: Trend Speed Analyzer (Zeiierman)
- Indicator 2: Adaptive Trend Expansion Bands (BigBeluga)
- Signal: both indicators green on the latest closed candle.
- Non-signal states are retained and shown as `TREND SPEED ONLY`, `EXPANSION BANDS ONLY`, or `NEITHER GREEN`.
- No Pump/Dump logic is used by this strategy.
- Auto scan remains browser/client driven at 60 seconds.
- Telegram is optional.

## Two-Green ordering and fresh transition
For `TWO_GREEN`, the scanner records the latest closed candle on which a coin **changed into BOTH GREEN** (previous closed candle was not BOTH GREEN; current closed candle is BOTH GREEN). Results are ordered by that transition time: newest transition first, oldest transition last. Coins that have never reached BOTH GREEN in the loaded history are placed after transitioned coins.

A coin that remains BOTH GREEN does not get a new timestamp on every scan; it keeps the original transition candle. A website/Telegram signal is emitted only for a newly detected transition on the latest closed candle.

Daily (`1d`) scanning is supported.
