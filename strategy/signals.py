"""
テクニカル指標からエントリー/エグジットシグナルを生成する。

エントリー条件 (全て AND):
  1. RSI が oversold 以下 (売られすぎ反発を狙う)
  2. ema_fast > ema_slow (上昇トレンド確認)
  3. 終値が bb_lower 付近 or bb_lower をタッチ (バンドタッチエントリー)
  4. MACD ヒストグラムが正転 (macd_hist > 0 かつ 前足 <= 0)
  5. ML モデルが ENTER を予測 (使用可能な場合)

エグジット条件 (OR):
  - 価格が TP に到達
  - 価格が SL を割り込む
  - RSI が overbought 以上かつ ema_fast < ema_slow (トレンド反転)
"""
from typing import Optional
import logging
import pandas as pd

logger = logging.getLogger(__name__)

SIGNAL_ENTER = "ENTER"
SIGNAL_EXIT  = "EXIT"
SIGNAL_HOLD  = "HOLD"


def entry_signal(
    ind: pd.Series,
    prev_ind: Optional[pd.Series],
    params: dict,
    ml_predict: Optional[int] = None,  # 1=ENTER, 0=HOLD
) -> str:
    """
    最新指標値からエントリーシグナルを判定する。
    戻り値: SIGNAL_ENTER or SIGNAL_HOLD
    """
    try:
        rsi      = ind["rsi"]
        ema_f    = ind["ema_fast"]
        ema_s    = ind["ema_slow"]
        close    = ind["close"]
        bb_lower = ind["bb_lower"]
        macd_h   = ind["macd_hist"]

        cond_rsi   = rsi <= params["rsi_oversold"]
        cond_trend = ema_f > ema_s
        cond_bb    = close <= bb_lower * 1.01  # 1% の余裕を持たせる
        cond_macd  = macd_h > 0

        if prev_ind is not None and "macd_hist" in prev_ind.index:
            cond_macd = (macd_h > 0) and (prev_ind["macd_hist"] <= 0)

        technical_ok = cond_rsi and cond_trend and cond_bb and cond_macd

        # ML シグナルが利用可能な場合は AND 条件に加える
        if ml_predict is not None:
            if technical_ok and ml_predict == 1:
                return SIGNAL_ENTER
        else:
            if technical_ok:
                return SIGNAL_ENTER

        return SIGNAL_HOLD

    except (KeyError, TypeError) as e:
        logger.debug(f"entry_signal 計算エラー: {e}")
        return SIGNAL_HOLD


def exit_signal(
    ind: pd.Series,
    entry_price: float,
    stop_loss: float,
    take_profit: float,
    params: dict,
) -> str:
    """
    保有ポジションのエグジットシグナルを判定する。
    戻り値: SIGNAL_EXIT or SIGNAL_HOLD
    """
    try:
        close  = ind["close"]
        rsi    = ind["rsi"]
        ema_f  = ind["ema_fast"]
        ema_s  = ind["ema_slow"]

        if close >= take_profit:
            return SIGNAL_EXIT
        if close <= stop_loss:
            return SIGNAL_EXIT

        # トレンド反転による早期撤退
        cond_overbought  = rsi >= params["rsi_overbought"]
        cond_trend_break = ema_f < ema_s
        if cond_overbought and cond_trend_break:
            return SIGNAL_EXIT

        return SIGNAL_HOLD

    except (KeyError, TypeError) as e:
        logger.debug(f"exit_signal 計算エラー: {e}")
        return SIGNAL_HOLD
