import os
import time
import asyncio
from dotenv import load_dotenv
from scapi import AppClient

load_dotenv()

CLIENT_ID = os.getenv("STALZONE_CLIENT_ID")
CLIENT_SECRET = os.getenv("STALZONE_CLIENT_SECRET")
REGION = "ru"

# Таймауты и ретраи
REQUEST_TIMEOUT = 15       # секунд на один запрос
MAX_RETRIES = 3            # сколько попыток
RETRY_DELAY = 2            # секунд между попытками

_client = None

_cache = {}
CACHE_TTL = 30

_history_cache = {}
HISTORY_TTL = 300

_debug_logged = set()


def get_client():
    global _client
    if _client is None:
        _client = AppClient(client_id=CLIENT_ID, client_secret=CLIENT_SECRET)
    return _client


async def _call_with_retry(coro_factory, label: str):
    """Вызывает корутину с ретраями.

    coro_factory — функция, возвращающая корутину (для каждого вызова новую).
    """
    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return await asyncio.wait_for(coro_factory(), timeout=REQUEST_TIMEOUT)
        except asyncio.TimeoutError:
            last_error = f"timeout ({REQUEST_TIMEOUT}s)"
            print(f"[api] {label}: попытка {attempt}/{MAX_RETRIES} — timeout")
        except Exception as e:
            last_error = str(e)
            print(f"[api] {label}: попытка {attempt}/{MAX_RETRIES} — {e}")

        if attempt < MAX_RETRIES:
            await asyncio.sleep(RETRY_DELAY)

    print(f"[api] {label}: все {MAX_RETRIES} попыток провалились — {last_error}")
    return None


async def get_lots(item_id: str, use_cache: bool = True):
    if use_cache and item_id in _cache:
        ts, cached = _cache[item_id]
        if time.time() - ts < CACHE_TTL:
            return cached

    client = get_client()
    listing = await _call_with_retry(
        lambda: client.auction(item_id, region=REGION).lots(
            limit=200, additional=True
        ),
        f"lots {item_id}",
    )

    if listing is None:
        # Отдаём устаревший кэш, если есть
        if item_id in _cache:
            return _cache[item_id][1]
        return None

    result = []
    for lot in listing:
        add = getattr(lot, "additional", None) or {}
        result.append({
            "buyout_price": getattr(lot, "buyout_price", 0),
            "amount":       getattr(lot, "amount", 1),
            "start_time":   getattr(lot, "start_time", ""),
            "end_time":     getattr(lot, "end_time", ""),
            "qlt":          add.get("qlt"),
            "ptn":          add.get("ptn"),
            "bonuses":      add.get("bonus_properties", []),
        })

    _cache[item_id] = (time.time(), result)
    return result


async def get_price_history(item_id: str, limit: int = 100, use_cache: bool = True):
    cache_key = f"{item_id}:{limit}"
    if use_cache and cache_key in _history_cache:
        ts, cached = _history_cache[cache_key]
        if time.time() - ts < HISTORY_TTL:
            return cached

    client = get_client()
    history = await _call_with_retry(
        lambda: client.auction(item_id, region=REGION).price_history(
            limit=limit, region=REGION
        ),
        f"history {item_id}",
    )

    if history is None:
        if cache_key in _history_cache:
            return _history_cache[cache_key][1]
        return None

    result = []
    for record in history:
        add = getattr(record, "additional", None) or {}
        price = getattr(record, "price", 0)
        if price <= 0:
            continue
        result.append({
            "price":  price,
            "time":   getattr(record, "time", ""),
            "amount": getattr(record, "amount", 1),
            "qlt":    add.get("qlt"),
            "ptn":    add.get("ptn"),
        })

    _history_cache[cache_key] = (time.time(), result)
    return result


def clear_cache(item_id: str | None = None):
    if item_id is None:
        _cache.clear()
        _history_cache.clear()
    else:
        _cache.pop(item_id, None)
        for key in list(_history_cache.keys()):
            if key.startswith(f"{item_id}:"):
                _history_cache.pop(key, None)