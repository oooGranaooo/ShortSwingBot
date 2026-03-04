"""
Birdeye のトークンリストからトレード候補をスクリーニングする。
スコアリング基準:
  - 1時間価格変動率  (weight_price_change)
  - 24時間出来高     (weight_volume)
  - 時価総額         (weight_mc)
フィルタリング基準:
  - 時価総額が min_market_cap 〜 max_market_cap の範囲内
  - 上場からの経過時間が min_listing_hours 以上
  - 1時間変化率が min_1h_change 以上
"""
import time
import logging
from typing import Optional

import aiohttp

from config.settings import PARAMS
from data.fetcher import fetch_token_list, fetch_token_overview

logger = logging.getLogger(__name__)


def _normalize(values: list[float]) -> list[float]:
    """0〜1 の範囲に正規化する。"""
    if not values:
        return values
    mn, mx = min(values), max(values)
    if mx == mn:
        return [0.5] * len(values)
    return [(v - mn) / (mx - mn) for v in values]


async def screen_tokens(
    session: aiohttp.ClientSession,
    params: Optional[dict] = None,
) -> list[dict]:
    """
    スクリーニングを実行し、スコア順にソートされた候補トークンリストを返す。
    各要素: {"address", "symbol", "name", "price", "mc", "v24h", "change1h",
             "listing_time", "score"}
    """
    p = params or PARAMS
    now = time.time()

    # --- 1. トークンリストを大量取得 ---
    raw_tokens = await fetch_token_list(
        session,
        sort_by="v24hUSD",
        limit=50,
    )
    if not raw_tokens:
        logger.warning("スクリーニング: トークンリスト取得失敗")
        return []

    # --- 2. 基本フィルタリング ---
    candidates = []
    for token in raw_tokens:
        mc = token.get("mc") or token.get("realMc") or 0
        change1h = token.get("v1hChangePercent", 0) or 0
        v24h = token.get("v24hUSD") or 0

        if mc < p["min_market_cap"]:
            continue
        if mc > p["max_market_cap"]:
            continue
        if change1h < p["min_1h_change"] * 100:  # API は % 表記
            continue

        # 上場時刻フィルター
        listing_time = token.get("listingTime") or token.get("createdTime")
        if listing_time:
            elapsed_hours = (now - listing_time) / 3600
            if elapsed_hours < p["min_listing_hours"]:
                continue
        else:
            listing_time = 0

        candidates.append({
            "address": token.get("address", ""),
            "symbol": token.get("symbol", ""),
            "name": token.get("name", ""),
            "price": token.get("price") or token.get("v24hUSD", 0),
            "mc": mc,
            "v24h": v24h,
            "change1h": change1h,
            "listing_time": listing_time,
        })

    if not candidates:
        logger.info("スクリーニング: フィルタリング後の候補なし")
        return []

    # --- 3. スコアリング ---
    changes = [c["change1h"] for c in candidates]
    volumes = [c["v24h"] for c in candidates]
    # MC は小さいほど爆発力があるため逆転スコア
    mcs_inv = [1.0 / max(c["mc"], 1) for c in candidates]

    norm_change = _normalize(changes)
    norm_volume = _normalize(volumes)
    norm_mc_inv = _normalize(mcs_inv)

    w_change = p["weight_price_change"]
    w_volume = p["weight_volume"]
    w_mc = p["weight_mc"]

    for i, c in enumerate(candidates):
        c["score"] = (
            w_change * norm_change[i]
            + w_volume * norm_volume[i]
            + w_mc * norm_mc_inv[i]
        )

    candidates.sort(key=lambda x: x["score"], reverse=True)
    top = candidates[: p["top_n_candidates"]]

    logger.info(f"スクリーニング完了: {len(top)} 件の候補")
    return top
