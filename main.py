"""
ShortSwing Bot - メインエントリーポイント

ループ処理:
  1. スクリーニングでトレード候補を選定
  2. 各候補の OHLCV を取得してテクニカル指標を計算
  3. 保有ポジションの SL/TP チェック
  4. エントリーシグナル判定 (ML + テクニカル)
  5. Discord 通知
  6. 定期的に ML モデルと Optuna パラメーターを更新
"""
import asyncio
import logging
import time
from copy import deepcopy

import aiohttp

from config.settings import LOOP_INTERVAL, TIMEFRAME
from data.fetcher import fetch_ohlcv
from data.dexscreener import fetch_prices as fetch_multi_prices
from data.ohlcv import to_dataframe
from execution.paper_trader import PaperTrader
from ml.features import build_feature_matrix, cache_entry_indicators
from ml.model import EntryClassifier
from ml.optimizer import optimize, load_optimized_params
from monitor.notifier import notify_buy, notify_sell, notify_ml_update, notify_error
from monitor.tracker import maybe_send_daily_summary, maybe_send_status
from strategy.indicators import add_indicators, latest
from strategy.screener import screen_tokens
from strategy.signals import entry_signal, exit_signal, SIGNAL_ENTER, SIGNAL_EXIT

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("logs/bot.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("main")


async def run():
    logger.info("===== ShortSwing Bot 起動 =====")

    params     = load_optimized_params()
    trader     = PaperTrader(params)
    classifier = EntryClassifier()

    # 履歴 OHLCV キャッシュ (Optuna 用)
    ohlcv_history: dict[str, object] = {}

    # ML / Optuna の最終実行時刻
    last_ml_train   = 0.0
    last_ml_optimize = 0.0
    ml_interval_sec = params["ml_retrain_interval_hours"] * 3600

    async with aiohttp.ClientSession() as session:
        while True:
            loop_start = time.time()
            try:
                await _main_cycle(
                    session, params, trader, classifier, ohlcv_history
                )
            except Exception as e:
                logger.error(f"メインサイクルエラー: {e}", exc_info=True)
                notify_error(str(e))

            # --- ML 定期再学習 ---
            if time.time() - last_ml_train > ml_interval_sec:
                try:
                    await _retrain_ml(trader, classifier)
                except Exception as e:
                    logger.error(f"ML再学習エラー: {e}", exc_info=True)
                last_ml_train = time.time()

            # --- Optuna 定期最適化 (ML 再学習の 2 倍間隔) ---
            if time.time() - last_ml_optimize > ml_interval_sec * 2:
                if ohlcv_history:
                    try:
                        logger.info("Optuna パラメーター最適化を開始...")
                        params = optimize(ohlcv_history, params)
                        trader.params = params
                        notify_ml_update(params)
                    except Exception as e:
                        logger.error(f"Optuna最適化エラー: {e}", exc_info=True)
                last_ml_optimize = time.time()

            elapsed = time.time() - loop_start
            sleep_sec = max(0, LOOP_INTERVAL - elapsed)
            logger.info(f"次のサイクルまで {sleep_sec:.0f}s 待機")
            await asyncio.sleep(sleep_sec)


async def _main_cycle(
    session: aiohttp.ClientSession,
    params: dict,
    trader: PaperTrader,
    classifier: EntryClassifier,
    ohlcv_history: dict,
):
    # --- 1. スクリーニング ---
    candidates = await screen_tokens(session, params)
    if not candidates:
        logger.info("候補なし。スキップ。")
        return

    # --- 2. OHLCV 取得 + 指標計算 ---
    token_data: dict[str, dict] = {}
    for token in candidates:
        addr = token["address"]
        await asyncio.sleep(1.0)  # Birdeye 無料プランのレートリミット対策
        items = await fetch_ohlcv(session, addr, TIMEFRAME)
        raw_df = to_dataframe(items)
        if raw_df.empty:
            continue
        df = add_indicators(raw_df, params)
        ind = latest(df)
        if ind is None:
            continue
        token_data[addr] = {"token": token, "df": df, "ind": ind}

        # Optuna 用に生の OHLCV をキャッシュ（指標なし）
        ohlcv_history[addr] = raw_df

    if not token_data:
        logger.info("有効な指標データなし。スキップ。")
        return

    # --- 3. 保有ポジションの SL/TP チェック ---
    all_addresses = list(token_data.keys()) + list(trader.positions.keys())
    prices = await fetch_multi_prices(session, list(set(all_addresses)))

    auto_closed = trader.check_exits(prices)
    for trade in auto_closed:
        notify_sell(
            symbol=trade.symbol,
            address=trade.address,
            entry_price=trade.entry_price,
            exit_price=trade.exit_price,
            pnl_usd=trade.pnl_usd,
            pnl_pct=trade.pnl_pct,
            reason=trade.exit_reason,
            capital_remaining=trader.capital,
        )

    # --- 4. 保有ポジションのシグナルエグジット確認 ---
    for addr, pos in list(trader.positions.items()):
        data = token_data.get(addr)
        if data is None:
            continue
        ind = data["ind"]
        sig = exit_signal(ind, pos.entry_price, pos.stop_loss, pos.take_profit, params)
        if sig == SIGNAL_EXIT:
            exit_price = prices.get(addr, ind["close"])
            trade = trader.close_position(addr, exit_price, reason="SIGNAL")
            if trade:
                notify_sell(
                    symbol=trade.symbol,
                    address=trade.address,
                    entry_price=trade.entry_price,
                    exit_price=trade.exit_price,
                    pnl_usd=trade.pnl_usd,
                    pnl_pct=trade.pnl_pct,
                    reason=trade.exit_reason,
                    capital_remaining=trader.capital,
                )

    # --- 5. 新規エントリー判定 ---
    for addr, data in token_data.items():
        if addr in trader.positions:
            continue

        token = data["token"]
        df    = data["df"]
        ind   = data["ind"]

        # 1 つ前の足を prev として渡す
        prev_ind = None
        subset = [c for c in ["macd_hist"] if c in df.columns]
        valid = df.dropna(subset=subset) if subset else df
        if len(valid) >= 2:
            prev_ind = valid.iloc[-2]

        ml_pred = classifier.predict(ind)
        sig = entry_signal(ind, prev_ind, params, ml_predict=ml_pred)

        if sig == SIGNAL_ENTER:
            entry_price = prices.get(addr, float(ind["close"]))
            atr = float(ind["atr"])
            pos = trader.open_position(addr, token["symbol"], entry_price, atr)
            if pos:
                cache_entry_indicators(addr, pos.entry_time, ind)
                notify_buy(
                    symbol=pos.symbol,
                    address=addr,
                    entry_price=pos.entry_price,
                    size=pos.size,
                    stop_loss=pos.stop_loss,
                    take_profit=pos.take_profit,
                    capital_remaining=trader.capital,
                )

    # --- 6. 定期通知 ---
    maybe_send_daily_summary(trader, prices)
    maybe_send_status(trader, prices, params)


async def _retrain_ml(trader: PaperTrader, classifier: EntryClassifier):
    """ML モデルを再学習する。"""
    logger.info("ML モデル再学習を開始...")
    X, y = build_feature_matrix(trader.closed_trades)
    if X is not None and y is not None:
        score = classifier.train(X, y)
        logger.info(f"ML 再学習完了: CV 精度={score:.3f}")
    else:
        logger.info("ML 学習データ不足。スキップ。")


if __name__ == "__main__":
    asyncio.run(run())
