"""
ATR ベースのストップロス / テイクプロフィット計算。
"""
from typing import Tuple


def calc_sl_tp(
    entry_price: float,
    atr: float,
    params: dict,
) -> Tuple[float, float]:
    """
    エントリー価格と ATR からSL/TP を計算する。

    Returns:
        (stop_loss, take_profit)
    """
    sl_mult = params["atr_sl_multiplier"]
    tp_mult = params["atr_tp_multiplier"]

    stop_loss   = entry_price - atr * sl_mult
    take_profit = entry_price + atr * tp_mult

    # SL が entry の 50% 以下にならないよう上限を設ける
    max_sl_pct = 0.50
    min_sl = entry_price * (1 - max_sl_pct)
    stop_loss = max(stop_loss, min_sl)

    return stop_loss, take_profit


def calc_position_size(
    capital: float,
    entry_price: float,
    params: dict,
) -> float:
    """
    資金の position_size_pct を使ったポジションサイズ (トークン数) を計算する。
    """
    alloc = capital * params["position_size_pct"]
    if entry_price <= 0:
        return 0.0
    return alloc / entry_price
