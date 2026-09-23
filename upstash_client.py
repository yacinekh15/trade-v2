"""Minimal Upstash Redis REST client with clear configuration errors."""

import json
import requests

from config import UPSTASH_REDIS_URL, UPSTASH_REDIS_TOKEN


def configured():
    return bool(UPSTASH_REDIS_URL and UPSTASH_REDIS_TOKEN)


def _command(*args):
    if not configured():
        raise RuntimeError(
            "Upstash is not configured. Set UPSTASH_REDIS_REST_URL and "
            "UPSTASH_REDIS_REST_TOKEN in Vercel."
        )
    resp = requests.post(
        UPSTASH_REDIS_URL,
        headers={"Authorization": f"Bearer {UPSTASH_REDIS_TOKEN}"},
        json=list(args),
        timeout=10,
    )
    resp.raise_for_status()
    body = resp.json()
    return body.get("result")


def set_json(key, obj):
    return _command("SET", key, json.dumps(obj, separators=(",", ":")))


def get_json(key, default=None):
    raw = _command("GET", key)
    if raw is None:
        return default
    return json.loads(raw)
