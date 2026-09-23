# Autonomous Halal Crypto Scanner

This version is designed to run without manual scanning.

## What is automated

Every 5 minutes GitHub Actions triggers **four independent scans**:

- 5m
- 15m
- 1h
- 4h

Each scan:

1. Reads the configured coin universe from `coins.txt`.
2. Downloads Binance Spot public OHLCV data.
3. Uses completed candles for scoring, avoiding signals based on a still-forming candle.
4. Calculates RSI, EMA20/EMA50, MACD, ATR, volume ratio, support and resistance.
5. Produces a transparent 0–100 technical screening score.
6. Saves results and scan health data in Upstash Redis.
7. Sends a Telegram alert when a coin newly enters a configured alert setup.
8. The dashboard automatically refreshes every 25 seconds.

**The system does not place orders.** Entry/target/invalidation numbers in Telegram are informational reference levels generated from price, ATR and recent support/resistance.

## 1. Upstash

Create a Redis database in Upstash and copy its REST URL and REST token.

Vercel environment variables:

| Variable | Required | Purpose |
|---|---|---|
| `UPSTASH_REDIS_REST_URL` | Yes | Persistent results/state |
| `UPSTASH_REDIS_REST_TOKEN` | Yes | Persistent results/state |
| `SCAN_SECRET` | Yes | Protect scan endpoint |
| `TELEGRAM_BOT_TOKEN` | For alerts | Telegram bot token |
| `TELEGRAM_CHAT_ID` | For alerts | Destination chat/channel |
| `ALERT_MIN_SCORE` | No | Default `70` |
| `ALERT_COOLDOWN_MINUTES` | No | Default `240` |
| `CANDLE_LOOKBACK` | No | Default `220` |

## 2. Vercel

Import the GitHub repository into Vercel and deploy it.

Check:

`/api/health`

The response should show `status: ok`, `upstash_configured: true`, and the number of coins in `coins.txt`.

## 3. GitHub Actions

The workflow in `.github/workflows/scan-cron.yml` runs every 5 minutes and uses a matrix to scan all four timeframes.

Create these GitHub Actions repository secrets:

| Secret | Value |
|---|---|
| `VERCEL_APP_DOMAIN` | Vercel hostname only, e.g. `trade-v1.vercel.app` |
| `SCAN_SECRET` | Exactly the same value as Vercel's `SCAN_SECRET` |

Then use **Actions → Autonomous crypto scanner → Run workflow** once to test it immediately.

## 4. Telegram

Create a Telegram bot, obtain its bot token and configure `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in Vercel.

Alerts are deduplicated in Upstash. A setup is alerted when it newly qualifies; staying in the same setup does not create a message every five minutes. If a setup disappears and later qualifies again, a new alert can be sent.

## 5. Dashboard

Open the Vercel domain root. The dashboard reads the latest independent result for the selected timeframe and refreshes automatically every 60 seconds.

It also shows:

- selected timeframe
- last scan time
- successful/failed coverage
- Telegram status
- Breakout/Momentum/Trend/Watch filters

## 6. Important architecture choice

The scheduler passes the timeframe directly to `/api/scan`:

`POST /api/scan?timeframe=1h&secret=...`

The server no longer relies on one global `current_timeframe`. This prevents concurrent 5m/15m/1h/4h jobs from overwriting one another.

## 7. Coin universe / halal status

`coins.txt` is the scanner's source of truth for the coin universe. The software does **not** independently certify whether a cryptocurrency is halal. Keep only the assets you have chosen according to your own screening method in that file.

## 8. Binance data

The scanner uses Binance's public market-data host:

`https://data-api.binance.vision`

No Binance API key is required for the public kline data used here.

## 9. Troubleshooting

### `failed_count` is high
Open `/api/results?timeframe=1h` and inspect `failed_samples`. The API records the first ten errors.

### GitHub Action returns 401
Check that the GitHub `SCAN_SECRET` exactly matches the Vercel environment variable.

### Telegram says OFF
Set both `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`, then redeploy Vercel.

### No results persist
Check `/api/health` and make sure `upstash_configured` is `true`.

### Dashboard is empty
Run the GitHub Action manually once, then refresh the dashboard.
