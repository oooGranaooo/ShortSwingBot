"""
Birdeye API のレスポンスを pandas DataFrame に整形する。
"""
import pandas as pd
import logging

logger = logging.getLogger(__name__)


def to_dataframe(items: list[dict]) -> pd.DataFrame:
    """
    Birdeye OHLCV レスポンスを DataFrame に変換する。
    columns: timestamp, open, high, low, close, volume
    """
    if not items:
        return pd.DataFrame()

    df = pd.DataFrame(items)

    rename_map = {
        "unixTime": "timestamp",
        "o": "open",
        "h": "high",
        "l": "low",
        "c": "close",
        "v": "volume",
    }
    df.rename(columns=rename_map, inplace=True)

    required = ["timestamp", "open", "high", "low", "close", "volume"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        logger.error(f"OHLCV データに必要なカラムが不足: {missing}")
        return pd.DataFrame()

    df = df[required].copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="s", utc=True)
    df.set_index("timestamp", inplace=True)
    df = df.sort_index()

    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df.dropna(inplace=True)
    return df
