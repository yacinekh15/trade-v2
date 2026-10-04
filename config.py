"""Central configuration for the fresh Trade-HHJ scanner build."""
import os

BINANCE_BASE_URL = os.environ.get("BINANCE_BASE_URL", "https://data-api.binance.vision")
COINS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "coins.txt")
TIMEFRAMES = ["5m", "15m", "1h", "4h", "1d"]
DEFAULT_TIMEFRAME = "1h"
CANDLE_LOOKBACK = int(os.environ.get("CANDLE_LOOKBACK", "280"))
LIQUIDITY_MIN_USDT = float(os.environ.get("LIQUIDITY_MIN_USDT", "5000000"))
AUTO_SCAN_SECONDS = 60

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
TELEGRAM_ENABLED_DEFAULT = os.environ.get("TELEGRAM_ENABLED_DEFAULT", "1") == "1"
ALERT_COOLDOWN_MINUTES = int(os.environ.get("ALERT_COOLDOWN_MINUTES", "60"))
ALERT_MAX_PER_SCAN = int(os.environ.get("ALERT_MAX_PER_SCAN", "20"))

EMA_EQUAL_TOLERANCE_PCT = float(os.environ.get("EMA_EQUAL_TOLERANCE_PCT", "0.05"))
MAX_EXTENSION_ATR = float(os.environ.get("MAX_EXTENSION_ATR", "3"))
DIVERGENCE_MIN_RSI_DELTA = float(os.environ.get("DIVERGENCE_MIN_RSI_DELTA", "1"))
DIVERGENCE_MIN_SPACING = int(os.environ.get("DIVERGENCE_MIN_SPACING", "5"))
DIVERGENCE_MAX_SPACING = int(os.environ.get("DIVERGENCE_MAX_SPACING", "30"))
DIVERGENCE_P1_RSI_MAX = float(os.environ.get("DIVERGENCE_P1_RSI_MAX", "45"))
DIVERGENCE_USE_P1_RSI_FILTER = os.environ.get("DIVERGENCE_USE_P1_RSI_FILTER", "1") == "1"

UPSTASH_REDIS_URL = os.environ.get("UPSTASH_REDIS_REST_URL", "")
UPSTASH_REDIS_TOKEN = os.environ.get("UPSTASH_REDIS_REST_TOKEN", "")
SCAN_SECRET = os.environ.get("SCAN_SECRET", "")

BACKTEST_DEFAULT_LIMIT = int(os.environ.get("BACKTEST_DEFAULT_LIMIT", "500"))
BACKTEST_MAX_LIMIT = int(os.environ.get("BACKTEST_MAX_LIMIT", "1000"))


def load_coins(path=COINS_FILE):
    with open(path, encoding="utf-8") as f:
        coins = []
        for line in f:
            s = line.strip().upper()
            if not s or s.startswith("#"):
                continue
            if s.startswith("BINANCE:"):
                s = s.split(":", 1)[1]
            if s not in coins:
                coins.append(s)
        return coins
