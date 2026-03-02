"""
クローズドトレードから ML 学習用の特徴量を抽出する。
"""
import numpy as np
import pandas as pd
from typing import Optional

from execution.paper_trader import ClosedTrade


# エントリー時の指標スナップショットを保存するキャッシュ
# { address+entry_time_str : pd.Series }
_indicator_cache: dict[str, dict] = {}


def cache_entry_indicators(address: str, entry_time: float, ind: pd.Series):
    """エントリー時の指標をキャッシュする。"""
    key = f"{address}_{entry_time:.0f}"
    _indicator_cache[key] = {
        "rsi":        ind.get("rsi", np.nan),
        "ema_fast":   ind.get("ema_fast", np.nan),
        "ema_slow":   ind.get("ema_slow", np.nan),
        "bb_upper":   ind.get("bb_upper", np.nan),
        "bb_lower":   ind.get("bb_lower", np.nan),
        "macd_hist":  ind.get("macd_hist", np.nan),
        "atr":        ind.get("atr", np.nan),
        "close":      ind.get("close", np.nan),
    }


def build_feature_matrix(
    trades: list[ClosedTrade],
) -> tuple[Optional[pd.DataFrame], Optional[pd.Series]]:
    """
    クローズドトレードから特徴量行列 X とラベル y を構築する。
    ラベル: 1 = 利益トレード (pnl > 0), 0 = 損失トレード
    """
    rows = []
    labels = []

    for t in trades:
        key = f"{t.address}_{t.entry_time:.0f}"
        ind = _indicator_cache.get(key)
        if ind is None:
            continue

        close = ind.get("close", 0)
        bb_lower = ind.get("bb_lower", 1e-10)
        ema_fast = ind.get("ema_fast", 1e-10)
        ema_slow = ind.get("ema_slow", 1e-10)

        row = {
            "rsi":            ind.get("rsi", np.nan),
            "macd_hist":      ind.get("macd_hist", np.nan),
            "atr_pct":        ind.get("atr", 0) / close if close > 0 else 0,
            "bb_pct":         (close - bb_lower) / bb_lower if bb_lower > 0 else 0,
            "ema_spread_pct": (ema_fast - ema_slow) / ema_slow if ema_slow > 0 else 0,
            "hold_hours":     (t.exit_time - t.entry_time) / 3600,
        }
        rows.append(row)
        labels.append(1 if t.pnl_usd > 0 else 0)

    if not rows:
        return None, None

    X = pd.DataFrame(rows).fillna(0)
    y = pd.Series(labels)
    return X, y
