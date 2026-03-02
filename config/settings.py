import os
from dotenv import load_dotenv

load_dotenv()

# --- API Keys ---
BIRDEYE_API_KEY = os.getenv("BIRDEYE_API_KEY", "")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")

# --- Candle settings ---
TIMEFRAME = "15m"
CANDLE_LIMIT = 100

# --- Main loop interval (seconds) ---
LOOP_INTERVAL = 300  # 5 min

# --- Default parameters (ML が調整する対象) ---
PARAMS = {
    # Screener
    "min_market_cap": 100_000,       # $100K 最低時価総額
    "max_market_cap": 50_000_000,    # $50M 最大時価総額
    "min_listing_hours": 24,         # 上場から最低24時間
    "top_n_candidates": 20,          # スクリーニング候補数
    "min_1h_change": 0.05,           # 1時間変化率の最低値 (5%)
    "weight_price_change": 0.4,      # スクリーニングスコア重み
    "weight_volume": 0.3,
    "weight_mc": 0.3,

    # RSI
    "rsi_period": 14,
    "rsi_oversold": 30,              # 買いシグナル閾値
    "rsi_overbought": 70,            # 売りシグナル閾値

    # EMA
    "ema_fast": 9,
    "ema_slow": 21,

    # Bollinger Bands
    "bb_period": 20,
    "bb_std": 2.0,

    # MACD
    "macd_fast": 12,
    "macd_slow": 26,
    "macd_signal": 9,

    # ATR
    "atr_period": 14,
    "atr_sl_multiplier": 2.0,        # SL = entry_price - ATR * multiplier
    "atr_tp_multiplier": 3.0,        # TP = entry_price + ATR * multiplier

    # Paper trading
    "initial_capital": 1000.0,       # 初期仮想資金 ($)
    "position_size_pct": 0.10,       # 1トレードあたりの資金割合 (10%)
    "max_positions": 5,              # 同時保有ポジション数上限

    # ML
    "ml_retrain_interval_hours": 24, # ML再学習間隔
    "optuna_n_trials": 50,           # Optunaトライアル数
    "min_trades_for_ml": 20,         # ML学習に必要な最低トレード数

    # 通知
    "status_interval_hours": 6,      # 現在状況の定期通知間隔 (時間)
}

# --- Paths ---
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGS_DIR = os.path.join(BASE_DIR, "logs")
MODELS_DIR = os.path.join(BASE_DIR, "ml", "saved_models")
TRADE_LOG_PATH = os.path.join(LOGS_DIR, "trades.json")
PARAMS_LOG_PATH = os.path.join(LOGS_DIR, "optimized_params.json")

os.makedirs(LOGS_DIR, exist_ok=True)
os.makedirs(MODELS_DIR, exist_ok=True)
