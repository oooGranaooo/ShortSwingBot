# ShortSwing Bot

Solana ミームコイン向けエアトレード (ペーパートレード) Bot。
実際の売買は行わず、仮想資金でシミュレーションしながら Discord に通知します。

---

## 機能

- **自動スクリーニング** — 1時間変化率・出来高・時価総額でトレード候補を自動選定
- **テクニカル分析** — RSI / EMA / ボリンジャーバンド / MACD / ATR の複合シグナル
- **動的 SL/TP** — ATR ベースでストップロス・テイクプロフィットを自動計算
- **Discord 通知** — 購入・売却・定期状況レポート・日次サマリー・エラーをリアルタイム通知
- **ML 最適化** — Optuna (パラメーター探索) + RandomForest (エントリー判定) で自動チューニング
- **エアトレード** — 実際の資金を使わず仮想 $1,000 でシミュレーション

---

## 必要なもの

| 項目 | 説明 |
|------|------|
| Python | 3.10 以上 |
| Birdeye API Key | 価格・OHLCV データの取得に使用 |
| Discord Webhook URL | 売買通知の送信に使用 |

---

## セットアップ

### 1. リポジトリのクローン / ディレクトリ移動

```bash
cd ShortSwing_bot
```

### 2. 依存ライブラリのインストール

```bash
pip install -r requirements.txt
```

### 3. 環境変数ファイルの作成

```bash
cp .env.example .env
```

`.env` をテキストエディタで開き、取得した値を貼り付けます。

```
BIRDEYE_API_KEY=your_birdeye_api_key_here
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/xxxxxxxxx/xxxxxxxxx
```

---

## API キーの取得方法

### Birdeye API Key

1. https://birdeye.so にアクセスしてアカウントを作成
2. ログイン後、https://birdeye.so/developer を開く
3. **「Create API Key」** をクリックしてキーを発行
4. 発行されたキーを `.env` の `BIRDEYE_API_KEY=` に貼り付ける

> 無料プランは 1分あたり 100 リクエストまで。
> 候補コイン数を絞ることで制限内に収まります (後述)。

---

### Discord Webhook URL

1. 通知を受け取りたい Discord サーバーを開く
2. 通知用チャンネルの **歯車アイコン (チャンネルの編集)** をクリック
3. 左メニューの **「連携サービス」** → **「ウェブフック」** を開く
4. **「新しいウェブフック」** をクリック
5. 名前を設定し **「ウェブフック URL をコピー」** をクリック
6. コピーした URL を `.env` の `DISCORD_WEBHOOK_URL=` に貼り付ける

---

## 起動

```bash
python main.py
```

起動すると以下のサイクルが 5 分ごとに繰り返されます。

```
1. スクリーニング (上位候補を選定)
2. OHLCV 取得 + テクニカル指標計算
3. 保有ポジションの SL/TP チェック
4. エントリーシグナル判定
5. Discord 通知 (売買発生時)
6. 定期状況レポート送信 (status_interval_hours ごと、デフォルト 6h)
7. 日次サマリー送信 (UTC 日付変更時)
8. ML モデル再学習 (24h ごと)
9. Optuna パラメーター最適化 (48h ごと)
```

ログは `logs/bot.log` にも保存されます。

---

## 主要パラメーターの調整

`config/settings.py` の `PARAMS` を変更することで動作をカスタマイズできます。
ML が自動最適化するため、初期値のまま起動しても問題ありません。

### よく変更する項目

```python
PARAMS = {
    # --- 資金設定 ---
    "initial_capital": 1000.0,      # 仮想初期資金 (USD)
    "position_size_pct": 0.10,      # 1トレードあたりの資金割合 (10%)
    "max_positions": 5,             # 同時保有ポジション数の上限

    # --- スクリーニング ---
    "min_market_cap": 100_000,      # 最低時価総額 ($100K)
    "max_market_cap": 50_000_000,   # 最高時価総額 ($50M)
    "min_listing_hours": 24,        # 上場からの最低経過時間 (ラグプル対策)
    "top_n_candidates": 20,         # 候補数 (API 制限が厳しい場合は 10 に下げる)
    "min_1h_change": 0.05,          # 最低 1時間変化率 (5%)

    # --- リスク管理 ---
    "atr_sl_multiplier": 2.0,       # SL = エントリー価格 - ATR × この値
    "atr_tp_multiplier": 3.0,       # TP = エントリー価格 + ATR × この値

    # --- 通知 ---
    "status_interval_hours": 6,     # 定期状況レポートの間隔 (時間)
                                    # 1 = 1時間ごと / 6 = 6時間ごと / 12 = 12時間ごと

    # --- ループ間隔 ---
    # LOOP_INTERVAL (settings.py のトップレベル変数) で変更
    # デフォルト: 300秒 (5分)
}
```

### Birdeye 無料プランで使う場合

API 制限 (100 req/min) に収めるため以下を推奨:

```python
"top_n_candidates": 10,   # 20 → 10 に下げる
```

また `settings.py` の `LOOP_INTERVAL` を `600`(10 分) にするとより安全です。

---

## Discord 通知の種類

| 通知 | タイミング | 内容 |
|------|-----------|------|
| 🟢 BUY | エントリーシグナル発生時 | 価格・数量・SL/TP・残高 |
| 🔵 SELL (利益) | TP 到達 or エグジットシグナル (利益) | エントリー/エグジット価格・PnL・残高 |
| 🔴 SELL (損失) | SL 到達 or エグジットシグナル (損失) | エントリー/エグジット価格・PnL・残高 |
| 📈 現在の運用状況 | `status_interval_hours` ごと (デフォルト 6h) | 総資産・勝率・累計PnL・オープンポジション・現在のパラメーター |
| 📊 日次サマリー | UTC 日付変更時 (毎日 1 回) | 総資産・累計PnL・トレード数・勝率・Sharpe |
| 🤖 ML 更新 | Optuna によるパラメーター最適化後 | 更新後のRSI閾値・SL/TP倍率・スクリーニング重み |
| ⚠️ エラー | 重大なエラー発生時 | エラーメッセージ |

### 📈 現在の運用状況 の内訳

```
💰 総資産       $1,234.56  (+23.5%)
💵 現金         $567.89
📊 未実現 PnL   +$12.34

― 成績 ―
トレード数  45件  |  勝率  62.2%
累計 PnL    +$234.56  |  平均 PnL%  +3.2%  |  Sharpe  1.45

📌 オープンポジション (2件)
WIF      $0.001234 → $0.001456  +18.0% ▲
BONK     $0.000023 → $0.000021   -8.7% ▼

⚙️ 現在のパラメーター
RSI 買い: 28  |  RSI 売り: 72
SL: 1.8x ATR  |  TP: 3.5x ATR
重み — 変動率: 45% / 出来高: 32% / MC: 23%
```

---

## ファイル構成

```
ShortSwing_bot/
├── .env                    ← API キーを記入 (gitignore 推奨)
├── .env.example            ← .env のテンプレート
├── requirements.txt        ← 依存ライブラリ一覧
├── main.py                 ← エントリーポイント
├── config/
│   └── settings.py         ← 全パラメーター設定
├── data/
│   ├── fetcher.py          ← Birdeye API データ取得
│   └── ohlcv.py            ← DataFrame 整形
├── strategy/
│   ├── screener.py         ← コインスクリーニング
│   ├── indicators.py       ← テクニカル指標計算
│   └── signals.py          ← エントリー/エグジットシグナル
├── execution/
│   ├── paper_trader.py     ← エアトレードエンジン
│   └── risk_manager.py     ← SL/TP 計算
├── ml/
│   ├── features.py         ← 特徴量抽出
│   ├── model.py            ← RandomForest エントリー判定
│   ├── optimizer.py        ← Optuna パラメーター最適化
│   └── saved_models/       ← 学習済みモデルの保存先
├── monitor/
│   ├── notifier.py         ← Discord 通知 (売買・状況レポート・サマリー等)
│   └── tracker.py          ← 定期状況レポート・日次サマリー管理
└── logs/
    ├── bot.log             ← 実行ログ
    ├── trades.json         ← トレード履歴
    └── optimized_params.json ← ML 最適化済みパラメーター
```

---

## 注意事項

- このBotはエアトレード (ペーパートレード) 専用です。実際の資金は動きません。
- 過去の成績は将来の利益を保証しません。
- ML の最適化には最低 20 件のトレード履歴が必要です (それまではデフォルトパラメーターで動作)。
- `.env` ファイルを Git にコミットしないよう注意してください。
