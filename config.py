"""Configuration for the autonomous Halal Crypto Scanner."""

import os

BINANCE_BASE_URL = os.environ.get(
    "BINANCE_BASE_URL",
    "https://data-api.binance.vision",
)
COINS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "coins.txt")
CANDLE_LOOKBACK = int(os.environ.get("CANDLE_LOOKBACK", "220"))

TIMEFRAMES = ["5m", "15m", "1h", "4h"]
DEFAULT_TIMEFRAME = "1h"

# Telegram
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
ALERT_SETUP_TYPES = {"BREAKOUT", "MOMENTUM", "TREND", "PULLBACK", "SUPPORT_BOUNCE", "REVERSAL"}
# Telegram is intentionally selective: only high-quality, multi-confirmed setups alert by default.
ALERT_MIN_SCORE = int(os.environ.get("ALERT_MIN_SCORE", "80"))
ALERT_MIN_VOLUME_RATIO = float(os.environ.get("ALERT_MIN_VOLUME_RATIO", "1.2"))
ALERT_COOLDOWN_MINUTES = int(os.environ.get("ALERT_COOLDOWN_MINUTES", "240"))
ALERT_MAX_PER_SCAN = int(os.environ.get("ALERT_MAX_PER_SCAN", "10"))
EMA_EQUAL_TOLERANCE_PCT = float(os.environ.get("EMA_EQUAL_TOLERANCE_PCT", "0.05"))
ALERT_EMA_EQUAL = os.environ.get("ALERT_EMA_EQUAL", "1") == "1"
BACKTEST_DEFAULT_LIMIT = int(os.environ.get("BACKTEST_DEFAULT_LIMIT", "500"))
BACKTEST_MAX_LIMIT = int(os.environ.get("BACKTEST_MAX_LIMIT", "1000"))

# Upstash Redis
UPSTASH_REDIS_URL = os.environ.get("UPSTASH_REDIS_REST_URL", "")
UPSTASH_REDIS_TOKEN = os.environ.get("UPSTASH_REDIS_REST_TOKEN", "")

# Secret used by GitHub Actions to trigger scans.
SCAN_SECRET = os.environ.get("SCAN_SECRET", "")


def load_coins(path=COINS_FILE):
    with open(path, encoding="utf-8") as f:
        return [line.strip().upper() for line in f if line.strip()]
