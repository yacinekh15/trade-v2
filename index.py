"""Vercel API for the autonomous Halal Crypto Scanner."""

import os
import sys
import time
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from fastapi import FastAPI, Header, HTTPException, Query

app = FastAPI(title="Halal Crypto Scanner API")


def get_dependencies():
    try:
        from config import (
            load_coins,
            TIMEFRAMES,
            DEFAULT_TIMEFRAME,
            CANDLE_LOOKBACK,
            SCAN_SECRET,
            TELEGRAM_BOT_TOKEN,
            TELEGRAM_CHAT_ID,
        )
        from scanner import run_scan
        from telegram_alerts import check_and_alert
        from upstash_client import get_json, set_json, configured as upstash_configured

        return locals()
    except Exception:
        print("DEPENDENCY IMPORT ERROR:")
        traceback.print_exc()
        raise


def results_key(timeframe):
    return f"results:{timeframe}"


def status_key(timeframe):
    return f"scan_status:{timeframe}"


def _authorize(deps, secret, header_secret=""):
    expected = deps["SCAN_SECRET"]
    # If no secret is configured, keep local/manual use possible.
    supplied = header_secret or secret
    if expected and supplied != expected:
        raise HTTPException(status_code=401, detail="Invalid scan secret")


def do_scan(timeframe):
    deps = get_dependencies()
    started = time.time()
    symbols = deps["load_coins"]()

    results, failed = deps["run_scan"](
        symbols,
        timeframe,
        deps["CANDLE_LOOKBACK"],
    )

    alert_info = deps["check_and_alert"](results, timeframe)
    finished = time.time()

    payload = {
        "status": "ok" if not failed else "partial",
        "timeframe": timeframe,
        "updated_at": finished,
        "duration_seconds": round(finished - started, 2),
        "coin_count": len(symbols),
        "successful_count": len(results),
        "failed_count": len(failed),
        "failed_samples": [
            {"symbol": symbol, "error": error}
            for symbol, error in failed[:10]
        ],
        "results": results,
        "alerts": alert_info,
    }

    # Persist the complete result and lightweight status independently.
    deps["set_json"](results_key(timeframe), payload)
    deps["set_json"](
        status_key(timeframe),
        {
            k: payload[k]
            for k in (
                "status",
                "timeframe",
                "updated_at",
                "duration_seconds",
                "coin_count",
                "successful_count",
                "failed_count",
                "failed_samples",
                "alerts",
            )
        },
    )
    return payload


@app.get("/api/health")
async def health():
    deps = get_dependencies()
    return {
        "status": "ok",
        "python": sys.version,
        "upstash_configured": deps["upstash_configured"](),
        "telegram_configured": bool(
            deps["TELEGRAM_BOT_TOKEN"] and deps["TELEGRAM_CHAT_ID"]
        ),
        "timeframes": deps["TIMEFRAMES"],
        "coins_file": len(deps["load_coins"]()),
    }


@app.get("/api/results")
async def api_results(timeframe: str = None):
    deps = get_dependencies()
    timeframe = timeframe or deps["DEFAULT_TIMEFRAME"]

    if timeframe not in deps["TIMEFRAMES"]:
        raise HTTPException(
            status_code=400,
            detail=f"timeframe must be one of {deps['TIMEFRAMES']}",
        )

    cached = deps["get_json"](results_key(timeframe))
    if cached is None:
        return {
            "status": "no_results",
            "timeframe": timeframe,
            "updated_at": None,
            "results": [],
            "failed_count": 0,
            "message": "No scan has completed for this timeframe yet.",
        }
    return cached


@app.get("/api/status")
async def api_status(timeframe: str = None):
    """Compact status for the selected timeframe; never includes secrets."""
    deps = get_dependencies()
    timeframe = timeframe or deps["DEFAULT_TIMEFRAME"]
    if timeframe not in deps["TIMEFRAMES"]:
        raise HTTPException(
            status_code=400,
            detail=f"timeframe must be one of {deps['TIMEFRAMES']}",
        )
    status = deps["get_json"](
        status_key(timeframe),
        default={"status": "never_run", "timeframe": timeframe},
    )
    return {
        "status": "ok",
        "server_time": time.time(),
        "timeframe": timeframe,
        "scan": status,
        "telegram_configured": bool(
            deps["TELEGRAM_BOT_TOKEN"] and deps["TELEGRAM_CHAT_ID"]
        ),
    }


@app.post("/api/scan")
async def api_scan(
    timeframe: str = Query(default=None),
    secret: str = Query(default=""),
    x_scan_secret: str = Header(default="", alias="X-Scan-Secret"),
):
    deps = get_dependencies()
    _authorize(deps, secret, x_scan_secret)
    timeframe = timeframe or deps["DEFAULT_TIMEFRAME"]

    if timeframe not in deps["TIMEFRAMES"]:
        raise HTTPException(
            status_code=400,
            detail=f"timeframe must be one of {deps['TIMEFRAMES']}",
        )

    payload = do_scan(timeframe)
    return {
        "ok": True,
        "timeframe": timeframe,
        "num_results": len(payload["results"]),
        "failed_count": payload["failed_count"],
        "duration_seconds": payload["duration_seconds"],
        "alerts": payload["alerts"],
    }


@app.post("/api/timeframe")
async def set_timeframe(timeframe: str = Query(...)):
    deps = get_dependencies()
    if timeframe not in deps["TIMEFRAMES"]:
        raise HTTPException(
            status_code=400,
            detail=f"timeframe must be one of {deps['TIMEFRAMES']}",
        )
    # Kept for dashboard/backward compatibility. Scans are now independent.
    return {"ok": True, "current_timeframe": timeframe}
