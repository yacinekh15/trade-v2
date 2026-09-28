# Deployment

## Vercel
Deploy the project root with `api/index.py` as the FastAPI entry point and the static dashboard in `public/index.html`.

## Server-side environment variables
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `UPSTASH_REDIS_REST_URL`
- `UPSTASH_REDIS_REST_TOKEN`
- optional `SCAN_SECRET`
- optional `MIN_QUOTE_VOLUME`, `MAX_RISK_PCT`, `MIN_STOP_ATR`, `EXTENSION_ATR`

No secrets are placed in browser JavaScript.

## Scanning
The supplied specification requires **manual SCAN NOW only**. There is no GitHub Actions schedule, cron, or automatic scanner. The browser scans the user-provided `coins.txt` universe in bounded batches and shows progress.
