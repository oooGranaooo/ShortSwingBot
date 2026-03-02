# Ubuntu Server デプロイ手順

ShortSwing Bot を自前の Ubuntu Server PC 上で常時稼働させるための手順書です。

---

## 目次

1. [前提条件](#1-前提条件)
2. [サーバーへの接続方法](#2-サーバーへの接続方法)
3. [Ubuntu Server の初期設定](#3-ubuntu-server-の初期設定)
4. [Python 環境のセットアップ](#4-python-環境のセットアップ)
5. [プロジェクトの配置](#5-プロジェクトの配置)
6. [依存ライブラリのインストール](#6-依存ライブラリのインストール)
7. [環境変数の設定](#7-環境変数の設定)
8. [動作確認](#8-動作確認)
9. [systemd サービス化 (常時稼働)](#9-systemd-サービス化-常時稼働)
10. [ログの確認](#10-ログの確認)
11. [よく使うコマンド](#11-よく使うコマンド)
12. [トラブルシューティング](#12-トラブルシューティング)

---

## 1. 前提条件

| 項目 | 要件 |
|------|------|
| OS | Ubuntu 22.04 LTS または 24.04 LTS |
| Python | 3.10 以上 |
| メモリ | 1GB 以上推奨 (ML 学習時に 512MB 以上消費) |
| ストレージ | 2GB 以上の空き容量 |
| ネットワーク | 外部 API へのアクセスが可能なこと |
| 事前準備 | Birdeye API Key / Discord Webhook URL を取得済みであること |

---

## 2. サーバーへの接続方法

自前の Ubuntu Server PC には **直接操作** または **SSH 経由** で接続できます。

---

### 2-1. 直接操作する (モニター・キーボードを接続する場合)

サーバー PC にモニターとキーボードを接続してそのまま操作できます。
この場合 SSH の設定は不要で、ログイン後すぐに手順 3 へ進めます。

---

### 2-2. SSH で別の PC からリモート接続する

同じ LAN 内の別 PC (Mac / Windows / Linux) からサーバーを操作する方法です。

#### ステップ 1: サーバーの IP アドレスを調べる

**サーバー PC 上で実行:**

```bash
ip a
```

`eth0` または `enp3s0` などのインターフェースに表示される `192.168.x.x` や `10.x.x.x` 形式の IP アドレスがローカル IP です。

```
2: enp3s0: ...
    inet 192.168.1.100/24 brd ...   ← これがサーバーのIPアドレス
```

または以下のコマンドでも確認できます:

```bash
hostname -I
```

#### ステップ 2: SSH サーバーの確認とインストール

Ubuntu Server インストール時に OpenSSH Server を選択していれば既に動いています。
確認するには:

```bash
sudo systemctl status ssh
```

`active (running)` でなければインストールします:

```bash
sudo apt install -y openssh-server
sudo systemctl enable --now ssh
```

#### ステップ 3: 別 PC から SSH で接続する

**ローカルマシン (Mac/Linux) のターミナルで実行:**

```bash
ssh ユーザー名@サーバーのIPアドレス
```

**具体例:**

```bash
ssh myuser@192.168.1.100
```

初回接続時は以下のメッセージが出ます。`yes` と入力して続行します:

```
The authenticity of host '192.168.1.100' can't be established.
Are you sure you want to continue connecting (yes/no/[fingerprint])? yes
```

---

### 2-3. SSH 鍵認証で接続する (推奨・よりセキュア)

パスワードより安全な **公開鍵認証** を設定します。
一度設定すればパスワード入力なしで接続できます。

#### ステップ 1: ローカルで SSH 鍵ペアを生成する

**ローカルマシン (Mac/Linux) のターミナルで実行:**

```bash
ssh-keygen -t ed25519 -C "shortswing-bot"
```

以下のように聞かれます:

```
Enter file in which to save the key (~/.ssh/id_ed25519): [Enter キーでOK]
Enter passphrase (empty for no passphrase): [任意のパスフレーズを入力 or Enter]
Enter same passphrase again: [同じパスフレーズを入力 or Enter]
```

`~/.ssh/id_ed25519` (秘密鍵) と `~/.ssh/id_ed25519.pub` (公開鍵) が生成されます。

#### ステップ 2: 公開鍵をサーバーに転送する

```bash
ssh-copy-id -i ~/.ssh/id_ed25519.pub ユーザー名@サーバーのIPアドレス
```

**具体例:**

```bash
ssh-copy-id -i ~/.ssh/id_ed25519.pub myuser@192.168.1.100
```

#### ステップ 3: 鍵認証で接続できることを確認する

```bash
ssh -i ~/.ssh/id_ed25519 ユーザー名@サーバーのIPアドレス
```

パスワードなしでログインできれば成功です。

---

### 2-4. SSH Config で接続を楽にする (推奨)

毎回 IP アドレスや鍵ファイルを指定するのが面倒な場合、設定ファイルに登録しておくと
短いコマンドで接続できます。

**ローカルの `~/.ssh/config` を編集:**

```bash
nano ~/.ssh/config
```

以下を追記します:

```
Host shortswing
    HostName 192.168.1.100
    User myuser
    IdentityFile ~/.ssh/id_ed25519
    ServerAliveInterval 60
    ServerAliveCountMax 10
```

| 項目 | 説明 |
|------|------|
| `Host` | 接続時に使うニックネーム (自由に決める) |
| `HostName` | サーバーの IP アドレス |
| `User` | ログインユーザー名 |
| `IdentityFile` | 秘密鍵のパス |
| `ServerAliveInterval` | 接続が切れにくくなる設定 |

設定後は以下のコマンドだけで接続できます:

```bash
ssh shortswing
```

---

### 2-5. IP アドレスが変わる問題への対処

ルーターの DHCP により、サーバーの IP アドレスが再起動のたびに変わることがあります。

**対処法 1: ルーターで固定 IP を割り当てる**

ルーターの管理画面でサーバーの MAC アドレスに対して固定 IP を割り当てると毎回同じ IP になります。
(ルーターの機種によって操作方法は異なります)

**対処法 2: Ubuntu Server 側で静的 IP を設定する**

```bash
sudo nano /etc/netplan/00-installer-config.yaml
```

以下のように編集します (インターフェース名・IP は環境に合わせて変更):

```yaml
network:
  version: 2
  ethernets:
    enp3s0:
      dhcp4: no
      addresses:
        - 192.168.1.100/24
      routes:
        - to: default
          via: 192.168.1.1
      nameservers:
        addresses: [8.8.8.8, 8.8.4.4]
```

設定を適用:

```bash
sudo netplan apply
```

---

### 2-6. 接続が切れる問題の対処

長時間作業していると SSH 接続が自動切断されることがあります。
接続が切れても Bot は systemd で動き続けますが、作業中に切れると不便です。

**対処法: tmux を使う (推奨)**

`tmux` を使うと、SSH が切れてもサーバー上の作業セッションが維持されます:

```bash
# tmux のインストール
sudo apt install -y tmux

# セッション開始
tmux new -s bot

# 切断後に再接続して復元
tmux attach -t bot
```

---

## 3. Ubuntu Server の初期設定

### パッケージリストの更新とアップグレード

```bash
sudo apt update && sudo apt upgrade -y
```

### 必要なシステムパッケージのインストール

```bash
sudo apt install -y \
    python3 \
    python3-pip \
    python3-venv \
    python3-dev \
    git \
    curl \
    build-essential \
    libssl-dev \
    libffi-dev
```

### Python バージョンの確認

```bash
python3 --version
```

> Python 3.10 以上であることを確認してください。
> Ubuntu 22.04 のデフォルトは Python 3.10.x です。
> Ubuntu 20.04 の場合は後述の「Python バージョンが古い場合」を参照してください。

#### Python バージョンが古い場合 (Ubuntu 20.04 など)

```bash
sudo add-apt-repository ppa:deadsnakes/ppa -y
sudo apt update
sudo apt install -y python3.11 python3.11-venv python3.11-dev
```

インストール後、コマンド内の `python3` を `python3.11` に読み替えてください。

---

## 4. Python 環境のセットアップ

### 作業ディレクトリの作成

```bash
mkdir -p ~/bots
cd ~/bots
```

---

## 5. プロジェクトの配置

### 方法 A: Git でクローン (リポジトリがある場合)

```bash
cd ~/bots
git clone <リポジトリURL> ShortSwing_bot
cd ShortSwing_bot
```

### 方法 B: ローカル PC から scp で転送する

**Mac/Linux の場合 — ローカルのターミナルで実行:**

```bash
scp -r /path/to/ShortSwing_bot myuser@192.168.1.100:~/bots/
```

SSH Config を設定済みの場合:

```bash
scp -r /path/to/ShortSwing_bot shortswing:~/bots/
```

### 方法 C: USB メモリで直接コピーする

サーバー PC に USB メモリを接続してコピーする場合:

```bash
# USB メモリのマウントポイントを確認
lsblk

# マウント (例: /dev/sdb1 の場合)
sudo mount /dev/sdb1 /mnt/usb

# コピー
cp -r /mnt/usb/ShortSwing_bot ~/bots/

# アンマウント
sudo umount /mnt/usb
```

### ファイルが正しく配置されているか確認

```bash
ls -la ~/bots/ShortSwing_bot/
```

以下のファイルが存在することを確認します:

```
main.py
requirements.txt
.env.example
config/
data/
execution/
ml/
monitor/
strategy/
logs/
```

---

## 6. 依存ライブラリのインストール

### Python 仮想環境の作成と有効化

仮想環境を使うことで、システム全体に影響を与えずにライブラリを管理できます。

```bash
cd ~/bots/ShortSwing_bot
python3 -m venv .venv
source .venv/bin/activate
```

> プロンプトが `(.venv) user@server:~$` のように変われば有効化成功です。

### pip のアップグレード

```bash
pip install --upgrade pip
```

### 依存ライブラリのインストール

```bash
pip install -r requirements.txt
```

> インストールには数分かかる場合があります。
> `scikit-learn` や `optuna` のビルドに時間がかかることがあります。

### インストールの確認

```bash
pip list
```

`aiohttp`, `pandas`, `scikit-learn`, `optuna`, `discord-webhook` などが表示されれば OK です。

---

## 7. 環境変数の設定

### .env ファイルの作成

```bash
cp .env.example .env
```

### .env ファイルの編集

```bash
nano .env
```

以下の内容を自分のキーに書き換えます:

```
BIRDEYE_API_KEY=取得したBirdeyeAPIキーを貼り付ける
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/xxxxxxxxx/xxxxxxxxx
```

保存して閉じるには: `Ctrl + X` → `Y` → `Enter`

### 設定の確認

```bash
cat .env
```

> **重要**: `.env` ファイルには API キーが含まれます。
> パーミッションを制限しておくことを推奨します:
> ```bash
> chmod 600 .env
> ```

---

## 8. 動作確認

### 仮想環境が有効になっていることを確認

```bash
source .venv/bin/activate
which python
# → ~/bots/ShortSwing_bot/.venv/bin/python と表示されればOK
```

### テスト起動

```bash
python main.py
```

起動すると以下のようなログが流れ始めます:

```
[2026-02-27 10:00:00] Bot started
[2026-02-27 10:00:01] Screening candidates...
[2026-02-27 10:00:05] Found 15 candidates
...
```

Discord の指定チャンネルにも通知が届くことを確認してください。

動作を確認できたら `Ctrl + C` で停止します。

---

## 9. systemd サービス化 (常時稼働)

`systemd` を使うことで、サーバー再起動後も Bot が自動的に起動し、常時稼働させることができます。

### ユーザー名の確認

```bash
whoami
```

### サービスファイルの作成

```bash
sudo nano /etc/systemd/system/shortswing-bot.service
```

以下の内容を貼り付けます (`your_user` を実際のユーザー名に変更してください):

```ini
[Unit]
Description=ShortSwing Bot - Solana Paper Trading Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=your_user
WorkingDirectory=/home/your_user/bots/ShortSwing_bot
ExecStart=/home/your_user/bots/ShortSwing_bot/.venv/bin/python main.py
Restart=always
RestartSec=30
StandardOutput=journal
StandardError=journal
SyslogIdentifier=shortswing-bot
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

> **例**: ユーザー名が `myuser` の場合:
> ```
> User=myuser
> WorkingDirectory=/home/myuser/bots/ShortSwing_bot
> ExecStart=/home/myuser/bots/ShortSwing_bot/.venv/bin/python main.py
> ```

### サービスファイルの有効化と起動

```bash
# systemd にサービスファイルを認識させる
sudo systemctl daemon-reload

# サーバー起動時に自動起動するよう設定
sudo systemctl enable shortswing-bot

# Bot を起動
sudo systemctl start shortswing-bot
```

### 起動状態の確認

```bash
sudo systemctl status shortswing-bot
```

以下のように `active (running)` と表示されれば成功です:

```
● shortswing-bot.service - ShortSwing Bot - Solana Paper Trading Bot
     Loaded: loaded (/etc/systemd/system/shortswing-bot.service; enabled)
     Active: active (running) since Thu 2026-02-27 10:00:00 JST; 5s ago
   Main PID: 12345 (python)
```

---

## 10. ログの確認

### systemd ログをリアルタイムで見る

```bash
sudo journalctl -u shortswing-bot -f
```

> `-f` オプションで最新ログをリアルタイム追跡します。終了は `Ctrl + C`。

### 過去 100 行のログを確認

```bash
sudo journalctl -u shortswing-bot -n 100
```

### bot.log ファイルを直接確認

```bash
tail -f ~/bots/ShortSwing_bot/logs/bot.log
```

### トレード履歴の確認

```bash
cat ~/bots/ShortSwing_bot/logs/trades.json | python3 -m json.tool
```

### ML 最適化パラメーターの確認

```bash
cat ~/bots/ShortSwing_bot/logs/optimized_params.json | python3 -m json.tool
```

---

## 11. よく使うコマンド

| 操作 | コマンド |
|------|---------|
| Bot の起動 | `sudo systemctl start shortswing-bot` |
| Bot の停止 | `sudo systemctl stop shortswing-bot` |
| Bot の再起動 | `sudo systemctl restart shortswing-bot` |
| Bot の状態確認 | `sudo systemctl status shortswing-bot` |
| ログのリアルタイム確認 | `sudo journalctl -u shortswing-bot -f` |
| 自動起動の有効化 | `sudo systemctl enable shortswing-bot` |
| 自動起動の無効化 | `sudo systemctl disable shortswing-bot` |

---

## 12. トラブルシューティング

### Bot が起動しない

**ログを確認する:**

```bash
sudo journalctl -u shortswing-bot -n 50 --no-pager
```

**よくある原因:**

#### `.env` ファイルが見つからない

```
FileNotFoundError: .env not found
```

→ `.env` ファイルが `WorkingDirectory` に存在するか確認:

```bash
ls -la ~/bots/ShortSwing_bot/.env
```

#### Python が見つからない

```
ExecStart: No such file or directory
```

→ サービスファイル内の Python パスを確認:

```bash
# 仮想環境を有効化した状態で実行
source ~/bots/ShortSwing_bot/.venv/bin/activate
which python
```

出力されたパスを `/etc/systemd/system/shortswing-bot.service` の `ExecStart=` に設定し直してください。

#### 依存ライブラリがない

```
ModuleNotFoundError: No module named 'aiohttp'
```

→ 仮想環境で再インストール:

```bash
source ~/bots/ShortSwing_bot/.venv/bin/activate
pip install -r ~/bots/ShortSwing_bot/requirements.txt
sudo systemctl restart shortswing-bot
```

---

### API エラーが頻発する

#### Birdeye API レート制限

```
429 Too Many Requests
```

→ `config/settings.py` で以下を変更:

```python
"top_n_candidates": 10,  # 20 → 10 に下げる
LOOP_INTERVAL = 600      # 300 → 600 (10分) に変更
```

変更後:

```bash
sudo systemctl restart shortswing-bot
```

#### Discord Webhook エラー

→ `.env` の `DISCORD_WEBHOOK_URL` が正しいか確認してください。

---

### メモリ不足エラー

ML 学習時にメモリが不足する場合があります:

```bash
# メモリ使用量を確認
free -h

# スワップを追加する (1GB の例)
sudo fallocate -l 1G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile

# 再起動後も有効にする
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

---

### 設定変更後の反映方法

`config/settings.py` や `.env` を変更した場合は Bot の再起動が必要です:

```bash
sudo systemctl restart shortswing-bot
```

---

### サーバー再起動後に Bot が起動しない

自動起動が有効になっているか確認:

```bash
sudo systemctl is-enabled shortswing-bot
# → "enabled" と表示されれば OK
```

有効になっていない場合:

```bash
sudo systemctl enable shortswing-bot
```

---

## 補足: ファイアウォール設定

Bot は外部に向けて API リクエストを送るだけなので、インバウンドのポート開放は基本不要です。
SSH でリモート接続する場合は SSH ポート (22) を許可しておいてください:

```bash
sudo ufw allow ssh
sudo ufw enable
sudo ufw status
```

---

## 補足: コード更新時のファイル転送

ローカルで修正したファイルをサーバーに送る場合:

```bash
# ローカルのターミナルで実行
# 特定ファイルのみ更新
scp /path/to/ShortSwing_bot/config/settings.py myuser@192.168.1.100:~/bots/ShortSwing_bot/config/

# SSH Config 設定済みの場合
scp /path/to/ShortSwing_bot/config/settings.py shortswing:~/bots/ShortSwing_bot/config/

# プロジェクト全体を上書き更新 (rsync)
rsync -avz --exclude='.env' --exclude='logs/' --exclude='.venv/' \
    /path/to/ShortSwing_bot/ \
    shortswing:~/bots/ShortSwing_bot/
```

転送後にサーバーで Bot を再起動:

```bash
sudo systemctl restart shortswing-bot
```

---

## 補足: GitHub からアップデートする

プロジェクトを `git clone` で配置した場合、GitHub に push した最新コードをサーバーに反映する手順です。

### 通常のアップデート手順

```bash
# Bot を停止する
sudo systemctl stop shortswing-bot

# プロジェクトディレクトリへ移動
cd ~/bots/ShortSwing_bot

# 最新コードを取得
git pull

# 仮想環境を有効化
source .venv/bin/activate

# requirements.txt が変更されていた場合は依存ライブラリを更新
pip install -r requirements.txt

# Bot を再起動
sudo systemctl start shortswing-bot

# 正常に起動したか確認
sudo systemctl status shortswing-bot
```

---

### requirements.txt が変わったかどうか確認する

```bash
git diff HEAD@{1} requirements.txt
```

差分が表示された場合は `pip install -r requirements.txt` が必要です。
表示されなければスキップしてかまいません。

---

### アップデートを1コマンドで実行するスクリプト

毎回手順を踏むのが面倒な場合は更新スクリプトを作っておくと便利です。

```bash
nano ~/update-bot.sh
```

以下の内容を貼り付けます:

```bash
#!/bin/bash
set -e

BOT_DIR=~/bots/ShortSwing_bot

echo "=== ShortSwing Bot アップデート開始 ==="

sudo systemctl stop shortswing-bot

cd "$BOT_DIR"
git pull

source .venv/bin/activate
pip install -r requirements.txt

sudo systemctl start shortswing-bot
sudo systemctl status shortswing-bot --no-pager

echo "=== アップデート完了 ==="
```

実行権限を付与:

```bash
chmod +x ~/update-bot.sh
```

以降は以下のコマンド1つでアップデートできます:

```bash
~/update-bot.sh
```

---

### アップデート後に Bot が起動しない場合

コードの変更で問題が発生した場合は、直前のコミットに戻すことができます。

```bash
# 直前のコミットに戻す
sudo systemctl stop shortswing-bot
cd ~/bots/ShortSwing_bot
git log --oneline -5          # コミット履歴を確認
git revert HEAD               # 直前のコミットを打ち消す新コミットを作成
sudo systemctl start shortswing-bot
```

または特定のコミットに戻す場合:

```bash
git checkout <コミットハッシュ>
```
