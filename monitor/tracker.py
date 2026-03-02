"""
P&L 追跡・定期サマリー送信モジュール。
"""
import logging
import time
from datetime import datetime, timezone

from execution.paper_trader import PaperTrader
from monitor.notifier import notify_daily_summary, notify_current_status

logger = logging.getLogger(__name__)

_last_summary_day: int = -1
_last_status_time: float = 0.0


def maybe_send_daily_summary(trader: PaperTrader, prices: dict[str, float]):
    """
    UTC 日付が変わったタイミングで日次サマリーを送信する。
    メインループから毎サイクル呼び出す。
    """
    global _last_summary_day
    now = datetime.now(timezone.utc)
    today = now.timetuple().tm_yday

    if today != _last_summary_day:
        _last_summary_day = today
        stats = trader.stats()
        pv = trader.portfolio_value(prices)
        notify_daily_summary(stats, pv)
        logger.info(f"日次サマリー送信: 総資産=${pv:.2f}")


def maybe_send_status(
    trader: PaperTrader,
    prices: dict[str, float],
    params: dict,
):
    """
    status_interval_hours ごとに現在の運用状況を送信する。
    メインループから毎サイクル呼び出す。
    """
    global _last_status_time
    interval_sec = params.get("status_interval_hours", 6) * 3600

    if time.time() - _last_status_time < interval_sec:
        return

    _last_status_time = time.time()

    stats = trader.stats()
    pv    = trader.portfolio_value(prices)
    initial = params.get("initial_capital", 1000.0)

    # オープンポジションの情報を構築
    open_positions = []
    for addr, pos in trader.positions.items():
        current_price = prices.get(addr, pos.entry_price)
        open_positions.append({
            "symbol":        pos.symbol,
            "address":       addr,
            "entry_price":   pos.entry_price,
            "current_price": current_price,
            "size":          pos.size,
        })

    notify_current_status(
        stats=stats,
        portfolio_value=pv,
        initial_capital=initial,
        cash=trader.capital,
        open_positions=open_positions,
        params=params,
    )
    logger.info(f"現在状況通知送信: 総資産=${pv:.2f}, ポジション={len(open_positions)}件")
