"""
Optuna を使った戦略パラメーター最適化。
バックテストを内包し、Sharpe Ratio を最大化するパラメーターを探索する。
"""
import json
import logging
from copy import deepcopy
from typing import Optional

import numpy as np
import optuna
import pandas as pd

from config.settings import PARAMS, PARAMS_LOG_PATH
from strategy.indicators import add_indicators
from strategy.signals import entry_signal, exit_signal, SIGNAL_ENTER, SIGNAL_EXIT
from execution.risk_manager import calc_sl_tp, calc_position_size

logger = logging.getLogger(__name__)

# Optuna のログを抑制
optuna.logging.set_verbosity(optuna.logging.WARNING)


def _backtest(ohlcv_df: pd.DataFrame, params: dict) -> float:
    """
    単純なバックテストを実行し、Sharpe Ratio を返す。
    """
    df = add_indicators(ohlcv_df, params)
    if df.empty or len(df) < 30:
        return -1.0

    capital = params["initial_capital"]
    trades_pnl: list[float] = []

    position: Optional[dict] = None
    prev_ind = None

    for i in range(1, len(df)):
        row = df.iloc[i]
        needed = ["rsi", "ema_fast", "ema_slow", "bb_lower", "macd_hist", "atr", "close"]
        if row[needed].isna().any():
            prev_ind = row
            continue

        close = row["close"]
        atr   = row["atr"]

        if position is not None:
            sig = exit_signal(row, position["entry_price"], position["sl"], position["tp"], params)
            if sig == SIGNAL_EXIT:
                pnl = (close - position["entry_price"]) * position["size"]
                trades_pnl.append(pnl)
                capital += position["cost"] + pnl
                position = None

        if position is None:
            sig = entry_signal(row, prev_ind, params, ml_predict=None)
            if sig == SIGNAL_ENTER:
                size = calc_position_size(capital, close, params)
                cost = size * close
                if cost <= capital:
                    sl, tp = calc_sl_tp(close, atr, params)
                    capital -= cost
                    position = {"entry_price": close, "size": size, "cost": cost, "sl": sl, "tp": tp}

        prev_ind = row

    if not trades_pnl:
        return -1.0

    arr = np.array(trades_pnl)
    if arr.std() == 0:
        return float(arr.mean())
    sharpe = (arr.mean() / arr.std()) * np.sqrt(252)
    return float(sharpe)


def optimize(
    historical_ohlcv: dict[str, pd.DataFrame],
    base_params: Optional[dict] = None,
    n_trials: Optional[int] = None,
) -> dict:
    """
    Optuna でパラメーターを最適化し、更新後の params dict を返す。

    Args:
        historical_ohlcv: {address: ohlcv_df} の辞書
        base_params: ベースパラメーター (None の場合は settings.PARAMS を使用)
        n_trials: Optuna トライアル数
    """
    if not historical_ohlcv:
        logger.warning("Optuna: 履歴データなし。最適化をスキップ。")
        return base_params or PARAMS

    p = deepcopy(base_params or PARAMS)
    trials = n_trials or p["optuna_n_trials"]

    def objective(trial: optuna.Trial) -> float:
        candidate = deepcopy(p)

        # --- 最適化対象パラメーター ---
        candidate["rsi_oversold"]       = trial.suggest_int("rsi_oversold", 20, 40)
        candidate["rsi_overbought"]     = trial.suggest_int("rsi_overbought", 60, 80)
        candidate["atr_sl_multiplier"]  = trial.suggest_float("atr_sl_multiplier", 1.0, 4.0)
        candidate["atr_tp_multiplier"]  = trial.suggest_float("atr_tp_multiplier", 1.5, 6.0)
        candidate["weight_price_change"] = trial.suggest_float("weight_price_change", 0.1, 0.8)
        candidate["weight_volume"]       = trial.suggest_float("weight_volume", 0.1, 0.8)
        candidate["weight_mc"]           = trial.suggest_float("weight_mc", 0.1, 0.8)
        candidate["ema_fast"]            = trial.suggest_int("ema_fast", 5, 20)
        candidate["ema_slow"]            = trial.suggest_int("ema_slow", 15, 50)

        # 重みの合計を 1 に正規化
        w_sum = (candidate["weight_price_change"]
                 + candidate["weight_volume"]
                 + candidate["weight_mc"])
        if w_sum > 0:
            candidate["weight_price_change"] /= w_sum
            candidate["weight_volume"]       /= w_sum
            candidate["weight_mc"]           /= w_sum

        # 全通貨のバックテスト結果の平均 Sharpe を目的関数にする
        sharpes = []
        for df in historical_ohlcv.values():
            s = _backtest(df, candidate)
            sharpes.append(s)

        return float(np.mean(sharpes)) if sharpes else -1.0

    study = optuna.create_study(direction="maximize")
    study.optimize(objective, n_trials=trials, show_progress_bar=False)

    best = study.best_params
    logger.info(f"Optuna 最適化完了 | Best Sharpe: {study.best_value:.3f} | Params: {best}")

    # 最適パラメーターを反映
    updated = deepcopy(p)
    updated.update(best)

    # 重みを正規化
    w_sum = (updated["weight_price_change"]
             + updated["weight_volume"]
             + updated["weight_mc"])
    if w_sum > 0:
        updated["weight_price_change"] /= w_sum
        updated["weight_volume"]       /= w_sum
        updated["weight_mc"]           /= w_sum

    # 保存
    try:
        with open(PARAMS_LOG_PATH, "w") as f:
            json.dump(updated, f, indent=2)
        logger.info(f"最適化済みパラメーターを保存: {PARAMS_LOG_PATH}")
    except Exception as e:
        logger.error(f"パラメーター保存失敗: {e}")

    return updated


def load_optimized_params() -> dict:
    """保存済みの最適化パラメーターを読み込む。なければ PARAMS を返す。"""
    try:
        with open(PARAMS_LOG_PATH) as f:
            p = json.load(f)
        logger.info("最適化済みパラメーターを読み込みました。")
        return p
    except FileNotFoundError:
        return deepcopy(PARAMS)
    except Exception as e:
        logger.error(f"最適化パラメーター読み込み失敗: {e}")
        return deepcopy(PARAMS)
