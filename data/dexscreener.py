"""
DexScreener API を使って価格データを取得する（無料・APIキー不要）。
"""
import logging
from typing import Optional

import aiohttp

logger = logging.getLogger(__name__)

BASE_URL = "https://api.dexscreener.com"
_BATCH_SIZE = 30  # DexScreener は1リクエストあたり最大30アドレス


async def fetch_prices(
    session: aiohttp.ClientSession,
    addresses: list[str],
) -> dict[str, float]:
    """
    DexScreener で複数 Solana トークンの現在価格を取得する。
    戻り値: {address: price_usd}
    各トークンについて最も流動性の高いペアの価格を使用する。
    """
    if not addresses:
        return {}

    results: dict[str, float] = {}

    for i in range(0, len(addresses), _BATCH_SIZE):
        batch = addresses[i : i + _BATCH_SIZE]
        url = f"{BASE_URL}/tokens/v1/solana/{','.join(batch)}"
        try:
            async with session.get(url) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    logger.warning(f"DexScreener fetch_prices error: {resp.status} {body}")
                    continue
                pairs = await resp.json()
                for pair in (pairs or []):
                    addr = pair.get("baseToken", {}).get("address", "")
                    price_str = pair.get("priceUsd")
                    # アドレスごとに最初に出現したペア（最高流動性）の価格を使用
                    if addr and price_str and addr not in results:
                        try:
                            results[addr] = float(price_str)
                        except (ValueError, TypeError):
                            pass
        except Exception as e:
            logger.warning(f"DexScreener fetch_prices error: {e}")

    return results


async def fetch_price(
    session: aiohttp.ClientSession,
    address: str,
) -> Optional[float]:
    """DexScreener で単一トークンの現在価格を取得する。"""
    prices = await fetch_prices(session, [address])
    return prices.get(address)
