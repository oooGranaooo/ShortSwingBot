"""
Birdeye API を使って Solana 上のトークンデータと OHLCV を取得する。
"""
import asyncio
import time
import logging
from typing import Optional

import aiohttp

from config.settings import BIRDEYE_API_KEY, TIMEFRAME, CANDLE_LIMIT

logger = logging.getLogger(__name__)

BASE_URL = "https://public-api.birdeye.so"

TIMEFRAME_SECONDS = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "1h": 3600,
    "4h": 14400,
    "1D": 86400,
}


def _headers() -> dict:
    return {
        "X-API-KEY": BIRDEYE_API_KEY,
        "x-chain": "solana",
    }


async def fetch_token_list(
    session: aiohttp.ClientSession,
    sort_by: str = "v24hUSD",
    limit: int = 50,
    min_liquidity: float = 10_000,
) -> list[dict]:
    """
    Birdeye のトークンリストを取得する。
    sort_by: "v24hUSD" (出来高), "mc" (時価総額), "v24hChangePercent" (変化率)
    """
    url = f"{BASE_URL}/defi/tokenlist"
    params = {
        "sort_by": sort_by,
        "sort_type": "desc",
        "offset": 0,
        "limit": limit,
        "min_liquidity": min_liquidity,
    }
    try:
        async with session.get(url, headers=_headers(), params=params) as resp:
            resp.raise_for_status()
            data = await resp.json()
            return data.get("data", {}).get("tokens", [])
    except Exception as e:
        logger.error(f"fetch_token_list error: {e}")
        return []


async def fetch_token_overview(
    session: aiohttp.ClientSession,
    address: str,
) -> Optional[dict]:
    """
    トークンの概要情報 (MC, 24h変化率, 上場時刻等) を取得する。
    """
    url = f"{BASE_URL}/defi/token_overview"
    params = {"address": address}
    try:
        async with session.get(url, headers=_headers(), params=params) as resp:
            resp.raise_for_status()
            data = await resp.json()
            return data.get("data")
    except Exception as e:
        logger.error(f"fetch_token_overview({address}) error: {e}")
        return None


async def fetch_ohlcv(
    session: aiohttp.ClientSession,
    address: str,
    timeframe: str = TIMEFRAME,
    limit: int = CANDLE_LIMIT,
) -> list[dict]:
    """
    指定トークンの OHLCV データを取得する。
    戻り値: [{"unixTime": int, "o": float, "h": float, "l": float, "c": float, "v": float}, ...]
    """
    tf_sec = TIMEFRAME_SECONDS.get(timeframe, 900)
    time_to = int(time.time())
    time_from = time_to - tf_sec * limit

    url = f"{BASE_URL}/defi/ohlcv"
    params = {
        "address": address,
        "type": timeframe,
        "time_from": time_from,
        "time_to": time_to,
    }
    try:
        async with session.get(url, headers=_headers(), params=params) as resp:
            resp.raise_for_status()
            data = await resp.json()
            items = data.get("data", {}).get("items", [])
            return items
    except Exception as e:
        logger.error(f"fetch_ohlcv({address}) error: {e}")
        return []


async def fetch_price(
    session: aiohttp.ClientSession,
    address: str,
) -> Optional[float]:
    """現在価格を取得する。"""
    url = f"{BASE_URL}/defi/price"
    params = {"address": address}
    try:
        async with session.get(url, headers=_headers(), params=params) as resp:
            resp.raise_for_status()
            data = await resp.json()
            return data.get("data", {}).get("value")
    except Exception as e:
        logger.error(f"fetch_price({address}) error: {e}")
        return None


async def fetch_multi_prices(
    session: aiohttp.ClientSession,
    addresses: list[str],
) -> dict[str, float]:
    """複数トークンの現在価格を一括取得する。"""
    url = f"{BASE_URL}/defi/multi_price"
    params = {"list_address": ",".join(addresses)}
    try:
        async with session.get(url, headers=_headers(), params=params) as resp:
            resp.raise_for_status()
            data = await resp.json()
            raw = data.get("data", {})
            return {addr: info.get("value", 0.0) for addr, info in raw.items()}
    except Exception as e:
        logger.error(f"fetch_multi_prices error: {e}")
        return {}
