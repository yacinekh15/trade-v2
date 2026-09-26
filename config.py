"""Configuration for the selective Halal Crypto Scanner."""
import os

BINANCE_BASE_URL = os.environ.get("BINANCE_BASE_URL", "https://data-api.binance.vision")
COINS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "coins.txt")
# 220 is enough to initialize EMA200 while keeping one-timeframe scans within
# Vercel's execution budget. The engine ignores the open candle.
CANDLE_LOOKBACK = int(os.environ.get("CANDLE_LOOKBACK", "220"))
TIMEFRAMES = ["5m", "15m", "1h", "4h"]
DEFAULT_TIMEFRAME = "1h"

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
ALERT_SETUP_TYPES = {"PULLBACK", "SUPPORT_BOUNCE", "BREAKOUT_RETEST", "EMA200_MACD"}
ALERT_MIN_SCORE = int(os.environ.get("ALERT_MIN_SCORE", "80"))
ALERT_MIN_ENTRY_QUALITY = int(os.environ.get("ALERT_MIN_ENTRY_QUALITY", "78"))
ALERT_MIN_VOLUME_RATIO = float(os.environ.get("ALERT_MIN_VOLUME_RATIO", "1.15"))
ALERT_COOLDOWN_MINUTES = int(os.environ.get("ALERT_COOLDOWN_MINUTES", "240"))
ALERT_MAX_PER_SCAN = int(os.environ.get("ALERT_MAX_PER_SCAN", "5"))
EMA_EQUAL_TOLERANCE_PCT = float(os.environ.get("EMA_EQUAL_TOLERANCE_PCT", "0.05"))
ALERT_EMA_EQUAL = os.environ.get("ALERT_EMA_EQUAL", "1") == "1"
BACKTEST_DEFAULT_LIMIT = int(os.environ.get("BACKTEST_DEFAULT_LIMIT", "500"))
BACKTEST_MAX_LIMIT = int(os.environ.get("BACKTEST_MAX_LIMIT", "1000"))
UPSTASH_REDIS_URL = os.environ.get("UPSTASH_REDIS_REST_URL", "")
UPSTASH_REDIS_TOKEN = os.environ.get("UPSTASH_REDIS_REST_TOKEN", "")
SCAN_SECRET = os.environ.get("SCAN_SECRET", "")


def load_coins(path=COINS_FILE):
    with open(path, encoding="utf-8") as f:
        return [line.strip().upper() for line in f if line.strip()]
