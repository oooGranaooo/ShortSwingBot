"""
エアトレードエンジン。
実際の取引は行わず、仮想ポートフォリオでシミュレーションする。
"""
import json
import logging
import time
from dataclasses import dataclass, field, asdict
from typing import Optional

from config.settings import PARAMS, TRADE_LOG_PATH
from execution.risk_manager import calc_sl_tp, calc_position_size

logger = logging.getLogger(__name__)


@dataclass
class Position:
    address: str
    symbol: str
    entry_price: float
    size: float          # トークン数
    stop_loss: float
    take_profit: float
    entry_time: float = field(default_factory=time.time)
    entry_cost: float = 0.0  # エントリー時の USD コスト


@dataclass
class ClosedTrade:
    address: str
    symbol: str
    entry_price: float
    exit_price: float
    size: float
    entry_time: float
    exit_time: float
    pnl_usd: float
    pnl_pct: float
    exit_reason: str     # "TP", "SL", "SIGNAL"


class PaperTrader:
    def __init__(self, params: Optional[dict] = None):
        self.params = params or PARAMS
        self.capital: float = self.params["initial_capital"]
        self.positions: dict[str, Position] = {}   # address -> Position
        self.closed_trades: list[ClosedTrade] = []
        self._load_trades()

    # -------- エントリー --------

    def open_position(
        self,
        address: str,
        symbol: str,
        entry_price: float,
        atr: float,
    ) -> Optional[Position]:
        """ポジションを開く。"""
        if address in self.positions:
            logger.debug(f"{symbol}: 既にポジションあり。スキップ。")
            return None

        if len(self.positions) >= self.params["max_positions"]:
            logger.info("最大ポジション数に達しました。エントリーをスキップ。")
            return None

        size = calc_position_size(self.capital, entry_price, self.params)
        cost = size * entry_price
        if cost > self.capital:
            logger.warning(f"{symbol}: 資金不足 (必要: {cost:.2f}, 残高: {self.capital:.2f})")
            return None

        sl, tp = calc_sl_tp(entry_price, atr, self.params)

        pos = Position(
            address=address,
            symbol=symbol,
            entry_price=entry_price,
            size=size,
            stop_loss=sl,
            take_profit=tp,
            entry_cost=cost,
        )
        self.positions[address] = pos
        self.capital -= cost

        logger.info(
            f"[BUY]  {symbol} @ ${entry_price:.6f} | "
            f"size={size:.4f} | SL=${sl:.6f} | TP=${tp:.6f} | "
            f"残高=${self.capital:.2f}"
        )
        return pos

    # -------- エグジット --------

    def close_position(
        self,
        address: str,
        exit_price: float,
        reason: str = "SIGNAL",
    ) -> Optional[ClosedTrade]:
        """ポジションを閉じる。"""
        pos = self.positions.pop(address, None)
        if pos is None:
            return None

        proceeds = pos.size * exit_price
        pnl_usd  = proceeds - pos.entry_cost
        pnl_pct  = pnl_usd / pos.entry_cost * 100 if pos.entry_cost else 0.0
        self.capital += proceeds

        trade = ClosedTrade(
            address=address,
            symbol=pos.symbol,
            entry_price=pos.entry_price,
            exit_price=exit_price,
            size=pos.size,
            entry_time=pos.entry_time,
            exit_time=time.time(),
            pnl_usd=pnl_usd,
            pnl_pct=pnl_pct,
            exit_reason=reason,
        )
        self.closed_trades.append(trade)
        self._save_trades()

        logger.info(
            f"[SELL] {pos.symbol} @ ${exit_price:.6f} | "
            f"PnL=${pnl_usd:+.2f} ({pnl_pct:+.1f}%) | "
            f"理由={reason} | 残高=${self.capital:.2f}"
        )
        return trade

    # -------- ポジション監視 --------

    def check_exits(self, prices: dict[str, float]) -> list[ClosedTrade]:
        """現在価格を確認し、SL/TP に達したポジションを自動クローズする。"""
        closed = []
        for address, pos in list(self.positions.items()):
            price = prices.get(address)
            if price is None:
                continue

            if price >= pos.take_profit:
                trade = self.close_position(address, price, reason="TP")
                if trade:
                    closed.append(trade)
            elif price <= pos.stop_loss:
                trade = self.close_position(address, price, reason="SL")
                if trade:
                    closed.append(trade)

        return closed

    # -------- サマリー --------

    def portfolio_value(self, prices: dict[str, float]) -> float:
        """現在の総資産 (現金 + ポジション評価額) を返す。"""
        position_value = sum(
            pos.size * prices.get(pos.address, pos.entry_price)
            for pos in self.positions.values()
        )
        return self.capital + position_value

    def stats(self) -> dict:
        """トレード統計を返す。"""
        if not self.closed_trades:
            return {
                "total_trades": 0,
                "win_rate": 0.0,
                "total_pnl_usd": 0.0,
                "avg_pnl_pct": 0.0,
                "sharpe": 0.0,
            }

        pnls = [t.pnl_usd for t in self.closed_trades]
        wins = [p for p in pnls if p > 0]
        import numpy as np
        pnl_arr = np.array(pnls)
        sharpe = (pnl_arr.mean() / pnl_arr.std()) * (252 ** 0.5) if pnl_arr.std() > 0 else 0.0

        return {
            "total_trades": len(self.closed_trades),
            "win_rate": len(wins) / len(pnls),
            "total_pnl_usd": sum(pnls),
            "avg_pnl_pct": sum(t.pnl_pct for t in self.closed_trades) / len(self.closed_trades),
            "sharpe": sharpe,
        }

    # -------- 永続化 --------

    def _save_trades(self):
        try:
            data = {
                "capital": self.capital,
                "closed_trades": [asdict(t) for t in self.closed_trades],
            }
            with open(TRADE_LOG_PATH, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"トレードログ保存失敗: {e}")

    def _load_trades(self):
        try:
            with open(TRADE_LOG_PATH) as f:
                data = json.load(f)
            self.capital = data.get("capital", self.params["initial_capital"])
            for t in data.get("closed_trades", []):
                self.closed_trades.append(ClosedTrade(**t))
            logger.info(f"トレードログ読み込み完了: {len(self.closed_trades)} 件")
        except FileNotFoundError:
            pass
        except Exception as e:
            logger.error(f"トレードログ読み込み失敗: {e}")
