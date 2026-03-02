"""
エントリー判定 ML モデル。
RandomForestClassifier を使い、指標値からエントリーの勝率を予測する。
"""
import logging
import os
from typing import Optional

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import cross_val_score
from sklearn.preprocessing import StandardScaler

from config.settings import MODELS_DIR, PARAMS

logger = logging.getLogger(__name__)

MODEL_PATH  = os.path.join(MODELS_DIR, "entry_classifier.pkl")
SCALER_PATH = os.path.join(MODELS_DIR, "scaler.pkl")


class EntryClassifier:
    def __init__(self):
        self.model: Optional[RandomForestClassifier] = None
        self.scaler: Optional[StandardScaler] = None
        self._load()

    def train(self, X: pd.DataFrame, y: pd.Series) -> float:
        """
        モデルを学習し、クロスバリデーション精度を返す。
        Returns:
            cv_score (float): 平均クロスバリデーション精度
        """
        if len(X) < PARAMS["min_trades_for_ml"]:
            logger.info(f"学習データ不足 ({len(X)} 件 < {PARAMS['min_trades_for_ml']})")
            return 0.0

        self.scaler = StandardScaler()
        X_scaled = self.scaler.fit_transform(X)

        self.model = RandomForestClassifier(
            n_estimators=100,
            max_depth=5,
            random_state=42,
            class_weight="balanced",
        )

        scores = cross_val_score(self.model, X_scaled, y, cv=3, scoring="accuracy")
        cv_score = float(scores.mean())
        logger.info(f"ML モデル CV 精度: {cv_score:.3f}")

        self.model.fit(X_scaled, y)
        self._save()
        return cv_score

    def predict(self, ind: pd.Series) -> Optional[int]:
        """
        指標値からエントリー判定を返す。
        Returns:
            1: エントリー推奨, 0: 見送り, None: モデル未学習
        """
        if self.model is None or self.scaler is None:
            return None

        close    = ind.get("close", 0)
        bb_lower = ind.get("bb_lower", 1e-10)
        ema_fast = ind.get("ema_fast", 1e-10)
        ema_slow = ind.get("ema_slow", 1e-10)

        features = np.array([[
            ind.get("rsi", 50),
            ind.get("macd_hist", 0),
            ind.get("atr", 0) / close if close > 0 else 0,
            (close - bb_lower) / bb_lower if bb_lower > 0 else 0,
            (ema_fast - ema_slow) / ema_slow if ema_slow > 0 else 0,
            0.0,  # hold_hours (エントリー時は 0)
        ]])

        try:
            X_scaled = self.scaler.transform(features)
            pred = int(self.model.predict(X_scaled)[0])
            proba = self.model.predict_proba(X_scaled)[0][1]
            logger.debug(f"ML 予測: {pred} (確率={proba:.2f})")
            return pred
        except Exception as e:
            logger.error(f"ML 予測エラー: {e}")
            return None

    def _save(self):
        try:
            joblib.dump(self.model, MODEL_PATH)
            joblib.dump(self.scaler, SCALER_PATH)
            logger.info("ML モデルを保存しました。")
        except Exception as e:
            logger.error(f"ML モデル保存失敗: {e}")

    def _load(self):
        try:
            if os.path.exists(MODEL_PATH) and os.path.exists(SCALER_PATH):
                self.model  = joblib.load(MODEL_PATH)
                self.scaler = joblib.load(SCALER_PATH)
                logger.info("ML モデルを読み込みました。")
        except Exception as e:
            logger.error(f"ML モデル読み込み失敗: {e}")
