"""Tiny Upstash REST wrapper with an in-process fallback for local development."""
import json, requests
from config import UPSTASH_REDIS_URL, UPSTASH_REDIS_TOKEN
_MEMORY={}

def configured(): return bool(UPSTASH_REDIS_URL and UPSTASH_REDIS_TOKEN)

def _command(*args):
    if not configured(): raise RuntimeError("Upstash is not configured")
    r=requests.post(UPSTASH_REDIS_URL,headers={"Authorization":f"Bearer {UPSTASH_REDIS_TOKEN}"},json=list(args),timeout=8);r.raise_for_status();return r.json().get("result")

def set_json(key,obj):
    if not configured(): _MEMORY[key]=obj; return "OK"
    return _command("SET",key,json.dumps(obj,separators=(",",":")))

def get_json(key,default=None):
    if not configured(): return _MEMORY.get(key,default)
    raw=_command("GET",key)
    return default if raw is None else json.loads(raw)
