"""
テクニカル指標を計算する。
pandas-ta を使用。失敗時は手動計算にフォールバック。
"""
import logging
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

try:
    import pandas_ta as ta
    _HAS_PANDAS_TA = True
except ImportError:
    _HAS_PANDAS_TA = False
    logger.warning("pandas-ta が見つかりません。手動計算にフォールバックします。")


# ---------- 手動計算フォールバック ----------

def _manual_rsi(close: pd.Series, period: int) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(com=period - 1, min_periods=period).mean()
    loss = (-delta.clip(upper=0)).ewm(com=period - 1, min_periods=period).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def _manual_ema(close: pd.Series, period: int) -> pd.Series:
    return close.ewm(span=period, adjust=False).mean()


def _manual_atr(df: pd.DataFrame, period: int) -> pd.Series:
    h, l, c = df["high"], df["low"], df["close"]
    prev_c = c.shift(1)
    tr = pd.concat([h - l, (h - prev_c).abs(), (l - prev_c).abs()], axis=1).max(axis=1)
    return tr.ewm(com=period - 1, min_periods=period).mean()


# ---------- 公開 API ----------

def add_indicators(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    """
    DataFrame に全テクニカル指標を追加して返す。
    追加カラム:
      rsi, ema_fast, ema_slow, bb_upper, bb_mid, bb_lower,
      macd, macd_signal, macd_hist, atr
    """
    if df.empty or len(df) < 30:
        return df

    df = df.copy()

    rsi_p    = int(params["rsi_period"])
    ema_fast = int(params["ema_fast"])
    ema_slow = int(params["ema_slow"])
    bb_p     = int(params["bb_period"])
    bb_std   = float(params["bb_std"])
    macd_f   = int(params["macd_fast"])
    macd_s   = int(params["macd_slow"])
    macd_sig = int(params["macd_signal"])
    atr_p    = int(params["atr_period"])

    if _HAS_PANDAS_TA:
        df.ta.rsi(length=rsi_p, append=True)
        df.ta.ema(length=ema_fast, append=True)
        df.ta.ema(length=ema_slow, append=True)
        df.ta.bbands(length=bb_p, std=bb_std, append=True)
        df.ta.macd(fast=macd_f, slow=macd_s, signal=macd_sig, append=True)
        df.ta.atr(length=atr_p, append=True)

        # カラム名を統一する
        df.rename(columns={
            f"RSI_{rsi_p}":                       "rsi",
            f"EMA_{ema_fast}":                    "ema_fast",
            f"EMA_{ema_slow}":                    "ema_slow",
            f"BBU_{bb_p}_{bb_std}":               "bb_upper",
            f"BBM_{bb_p}_{bb_std}":               "bb_mid",
            f"BBL_{bb_p}_{bb_std}":               "bb_lower",
            f"MACD_{macd_f}_{macd_s}_{macd_sig}": "macd",
            f"MACDs_{macd_f}_{macd_s}_{macd_sig}":"macd_signal",
            f"MACDh_{macd_f}_{macd_s}_{macd_sig}":"macd_hist",
            f"ATRr_{atr_p}":                      "atr",
        }, inplace=True)
    else:
        df["rsi"]        = _manual_rsi(df["close"], rsi_p)
        df["ema_fast"]   = _manual_ema(df["close"], ema_fast)
        df["ema_slow"]   = _manual_ema(df["close"], ema_slow)
        # Bollinger Bands
        rolling = df["close"].rolling(bb_p)
        df["bb_mid"]    = rolling.mean()
        df["bb_upper"]  = df["bb_mid"] + bb_std * rolling.std(ddof=0)
        df["bb_lower"]  = df["bb_mid"] - bb_std * rolling.std(ddof=0)
        # MACD
        ema_f = _manual_ema(df["close"], macd_f)
        ema_s = _manual_ema(df["close"], macd_s)
        df["macd"]       = ema_f - ema_s
        df["macd_signal"] = _manual_ema(df["macd"], macd_sig)
        df["macd_hist"]  = df["macd"] - df["macd_signal"]
        # ATR
        df["atr"] = _manual_atr(df, atr_p)

    return df


def latest(df: pd.DataFrame) -> Optional[pd.Series]:
    """直近の完成済みローソク足の指標値を返す。"""
    needed = ["rsi", "ema_fast", "ema_slow", "bb_upper", "bb_lower",
              "macd", "macd_signal", "macd_hist", "atr", "close"]
    valid = df.dropna(subset=[c for c in needed if c in df.columns])
    if valid.empty:
        return None
    return valid.iloc[-1]
