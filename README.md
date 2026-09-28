# Halal Spot Scanner — Long Only

## Strategy rules

### 1. EMA200 Reclaim
A signal is generated only on a **closed candle** when:
- The two immediately preceding closed candles both closed below their EMA200.
- The current closed candle closes above its EMA200.
- Direction is LONG only.

### 2. Bullish RSI Divergence
A signal is generated only when:
- Price is above EMA200.
- Two confirmed pivot lows form a regular bullish divergence:
  price makes a lower low while RSI(14) makes a higher low.
- The current closed candle passes the conservative 5-candle confirmation:
  it is bullish and closes above the previous four closes.

### Risk levels
- Entry = signal candle close.
- SL = below the relevant recent/divergence swing low.
- TP references = 2R and 3R.

## Scanner behavior
- Spot / long only.
- No shorts, futures, leverage, MACD, EMA20/50, or automatic orders.
- Open candles are ignored.
- Manual Scan Now.
- Server-side Auto Scanner toggle and interval.
- Telegram toggle for qualifying alerts.
- Telegram cooldown prevents repeated alerts for the same symbol/setup/timeframe.

## Deployment
Set:
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `SCAN_SECRET`
- Upstash variables if persistent auto-scan state is desired.

GitHub Actions calls `/api/auto-scan` every 5 minutes; the server-side Auto Scanner setting decides whether a scan is due.
