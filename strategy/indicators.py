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
        # EMA は fast==slow のとき列名が衝突するため常に手動計算
        df["ema_fast"] = _manual_ema(df["close"], ema_fast)
        df["ema_slow"] = _manual_ema(df["close"], ema_slow)

        df.ta.rsi(length=rsi_p, append=True)
        df.ta.bbands(length=bb_p, std=bb_std, append=True)
        df.ta.macd(fast=macd_f, slow=macd_s, signal=macd_sig, append=True)
        df.ta.atr(length=atr_p, append=True)

        # カラム名を統一する
        # BBands はバージョンによって小数点フォーマットが異なるためプレフィックス検索
        rename_map: dict[str, str] = {}
        for col in df.columns:
            if col == f"RSI_{rsi_p}":
                rename_map[col] = "rsi"
            elif col.startswith(f"BBU_{bb_p}_"):
                rename_map[col] = "bb_upper"
            elif col.startswith(f"BBM_{bb_p}_"):
                rename_map[col] = "bb_mid"
            elif col.startswith(f"BBL_{bb_p}_"):
                rename_map[col] = "bb_lower"
            elif col == f"MACD_{macd_f}_{macd_s}_{macd_sig}":
                rename_map[col] = "macd"
            elif col == f"MACDs_{macd_f}_{macd_s}_{macd_sig}":
                rename_map[col] = "macd_signal"
            elif col == f"MACDh_{macd_f}_{macd_s}_{macd_sig}":
                rename_map[col] = "macd_hist"
            elif col == f"ATRr_{atr_p}":
                rename_map[col] = "atr"
        df.rename(columns=rename_map, inplace=True)

        # pandas-ta が失敗した列を手動計算でフォールバック
        if "rsi" not in df.columns:
            df["rsi"] = _manual_rsi(df["close"], rsi_p)

        if "bb_lower" not in df.columns:
            rolling = df["close"].rolling(bb_p)
            df["bb_mid"]   = rolling.mean()
            df["bb_upper"] = df["bb_mid"] + bb_std * rolling.std(ddof=0)
            df["bb_lower"] = df["bb_mid"] - bb_std * rolling.std(ddof=0)

        if "macd_hist" not in df.columns:
            _ema_f = _manual_ema(df["close"], macd_f)
            _ema_s = _manual_ema(df["close"], macd_s)
            df["macd"]        = _ema_f - _ema_s
            df["macd_signal"] = _manual_ema(df["macd"], macd_sig)
            df["macd_hist"]   = df["macd"] - df["macd_signal"]

        if "atr" not in df.columns:
            df["atr"] = _manual_atr(df, atr_p)
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
