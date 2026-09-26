# Deployment

## Vercel
Deploy as a Python/FastAPI project. `vercel.json` sets the API function timeout.

## Required Vercel environment variables
- `UPSTASH_REDIS_REST_URL`
- `UPSTASH_REDIS_REST_TOKEN`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

Optional:
- `ALERT_MIN_SCORE` (default 70)
- `ALERT_COOLDOWN_MINUTES` (default 240)
- `EMA_EQUAL_TOLERANCE_PCT` (default 0.05). Exact floating-point equality is not used; an EMA20/EMA50 gap inside this percentage is treated as “equal/converged”.
- `ALERT_EMA_EQUAL=1` (default)
- `BACKTEST_DEFAULT_LIMIT=500`
- `BACKTEST_MAX_LIMIT=1000`
- `SCAN_SECRET` if you want to protect API scans.

## Manual workflow
The GitHub Action is `workflow_dispatch` only. There is no automatic cron. You can scan from the website's **SCAN NOW** button or manually from GitHub Actions.

## Endpoints
- `GET /api/health`
- `POST /api/scan?timeframe=5m|15m|1h|4h` (the dashboard runs ALL as four independent scans)
- `GET /api/results?timeframe=...`
- `GET /api/candles?symbol=BTCUSDT&timeframe=1h`
- `POST /api/backtest?symbol=BTCUSDT&timeframe=1h`
- `GET/POST /api/paper-trades`

## Backtest methodology
Signals are generated from closed candles only. The simulated entry is the next candle open, and target/stop are then evaluated candle-by-candle. If a candle touches both target and stop, the engine uses the conservative stop outcome because intrabar order is unknown from OHLC data. This is a screening backtest, not proof of future performance.
