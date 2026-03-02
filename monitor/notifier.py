"""
Discord Webhook による通知モジュール。
購入・売却・エラー・日次サマリーを送信する。
"""
import logging
from datetime import datetime, timezone

from discord_webhook import DiscordWebhook, DiscordEmbed

from config.settings import DISCORD_WEBHOOK_URL

logger = logging.getLogger(__name__)

SOLSCAN_URL = "https://solscan.io/token/"

# Discord 色コード
COLOR_BUY    = 0x00FF7F  # 緑
COLOR_SELL_WIN  = 0x1E90FF  # 青 (利益)
COLOR_SELL_LOSS = 0xFF4500  # 赤 (損失)
COLOR_INFO   = 0xFFD700  # 黄
COLOR_ERROR  = 0xFF0000  # 赤


def _send(embed: DiscordEmbed):
    if not DISCORD_WEBHOOK_URL:
        logger.warning("DISCORD_WEBHOOK_URL が設定されていません。通知をスキップ。")
        return
    try:
        wh = DiscordWebhook(url=DISCORD_WEBHOOK_URL)
        wh.add_embed(embed)
        resp = wh.execute()
        if resp and resp.status_code not in (200, 204):
            logger.error(f"Discord 通知失敗: status={resp.status_code}")
    except Exception as e:
        logger.error(f"Discord 通知エラー: {e}")


def notify_buy(
    symbol: str,
    address: str,
    entry_price: float,
    size: float,
    stop_loss: float,
    take_profit: float,
    capital_remaining: float,
):
    """購入通知を送信する。"""
    embed = DiscordEmbed(
        title=f"🟢 BUY  {symbol}",
        color=COLOR_BUY,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
    embed.add_embed_field(name="価格",      value=f"${entry_price:.6f}", inline=True)
    embed.add_embed_field(name="数量",      value=f"{size:.4f}",         inline=True)
    embed.add_embed_field(name="投資額",    value=f"${entry_price * size:.2f}", inline=True)
    embed.add_embed_field(name="SL",        value=f"${stop_loss:.6f}",   inline=True)
    embed.add_embed_field(name="TP",        value=f"${take_profit:.6f}", inline=True)
    embed.add_embed_field(name="残高",      value=f"${capital_remaining:.2f}", inline=True)
    embed.add_embed_field(
        name="Solscan",
        value=f"[{address[:8]}...]({SOLSCAN_URL}{address})",
        inline=False,
    )
    embed.set_footer(text="ShortSwing Bot | Paper Trade")
    _send(embed)


def notify_sell(
    symbol: str,
    address: str,
    entry_price: float,
    exit_price: float,
    pnl_usd: float,
    pnl_pct: float,
    reason: str,
    capital_remaining: float,
):
    """売却通知を送信する。"""
    color = COLOR_SELL_WIN if pnl_usd >= 0 else COLOR_SELL_LOSS
    emoji = "🔵" if pnl_usd >= 0 else "🔴"
    sign  = "+" if pnl_usd >= 0 else ""

    embed = DiscordEmbed(
        title=f"{emoji} SELL {symbol}  [{reason}]",
        color=color,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
    embed.add_embed_field(name="エントリー", value=f"${entry_price:.6f}", inline=True)
    embed.add_embed_field(name="エグジット", value=f"${exit_price:.6f}",  inline=True)
    embed.add_embed_field(name="PnL",        value=f"{sign}${pnl_usd:.2f} ({sign}{pnl_pct:.1f}%)", inline=True)
    embed.add_embed_field(name="残高",       value=f"${capital_remaining:.2f}", inline=False)
    embed.add_embed_field(
        name="Solscan",
        value=f"[{address[:8]}...]({SOLSCAN_URL}{address})",
        inline=False,
    )
    embed.set_footer(text="ShortSwing Bot | Paper Trade")
    _send(embed)


def notify_daily_summary(stats: dict, portfolio_value: float):
    """日次サマリーを送信する。"""
    embed = DiscordEmbed(
        title="📊 日次サマリー",
        color=COLOR_INFO,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
    embed.add_embed_field(name="総資産",       value=f"${portfolio_value:.2f}",              inline=True)
    embed.add_embed_field(name="累計 PnL",     value=f"${stats['total_pnl_usd']:+.2f}",     inline=True)
    embed.add_embed_field(name="トレード数",   value=str(stats["total_trades"]),             inline=True)
    embed.add_embed_field(name="勝率",         value=f"{stats['win_rate'] * 100:.1f}%",      inline=True)
    embed.add_embed_field(name="平均 PnL%",   value=f"{stats['avg_pnl_pct']:+.1f}%",        inline=True)
    embed.add_embed_field(name="Sharpe",       value=f"{stats['sharpe']:.2f}",               inline=True)
    embed.set_footer(text="ShortSwing Bot | Paper Trade")
    _send(embed)


def notify_ml_update(updated_params: dict):
    """ML パラメーター更新通知を送信する。"""
    embed = DiscordEmbed(
        title="🤖 ML パラメーター更新",
        color=COLOR_INFO,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
    key_params = [
        "rsi_oversold", "rsi_overbought",
        "atr_sl_multiplier", "atr_tp_multiplier",
        "weight_price_change", "weight_volume", "weight_mc",
    ]
    for k in key_params:
        if k in updated_params:
            embed.add_embed_field(name=k, value=str(round(updated_params[k], 3)), inline=True)
    embed.set_footer(text="ShortSwing Bot | Optuna Optimization")
    _send(embed)


def notify_current_status(
    stats: dict,
    portfolio_value: float,
    initial_capital: float,
    cash: float,
    open_positions: list[dict],  # [{"symbol", "address", "entry_price", "current_price", "size"}]
    params: dict,
):
    """
    現在の運用状況を通知する。
    定期的 (status_interval_hours ごと) に送信する。
    """
    total_return_pct = (portfolio_value - initial_capital) / initial_capital * 100
    unrealized_pnl = sum(
        (p["current_price"] - p["entry_price"]) * p["size"]
        for p in open_positions
    )

    color = COLOR_SELL_WIN if total_return_pct >= 0 else COLOR_SELL_LOSS
    sign  = "+" if total_return_pct >= 0 else ""

    embed = DiscordEmbed(
        title="📈 現在の運用状況",
        color=color,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

    # --- 資産状況 ---
    embed.add_embed_field(
        name="💰 総資産",
        value=f"${portfolio_value:.2f}  ({sign}{total_return_pct:.1f}%)",
        inline=True,
    )
    embed.add_embed_field(name="💵 現金",        value=f"${cash:.2f}",          inline=True)
    embed.add_embed_field(
        name="📊 未実現 PnL",
        value=f"${unrealized_pnl:+.2f}",
        inline=True,
    )

    # --- 成績 ---
    embed.add_embed_field(name="\u200b", value="**― 成績 ―**", inline=False)
    embed.add_embed_field(name="トレード数", value=str(stats["total_trades"]),             inline=True)
    embed.add_embed_field(name="勝率",       value=f"{stats['win_rate'] * 100:.1f}%",      inline=True)
    embed.add_embed_field(name="累計 PnL",   value=f"${stats['total_pnl_usd']:+.2f}",     inline=True)
    embed.add_embed_field(name="平均 PnL%",  value=f"{stats['avg_pnl_pct']:+.1f}%",       inline=True)
    embed.add_embed_field(name="Sharpe",     value=f"{stats['sharpe']:.2f}",               inline=True)
    embed.add_embed_field(name="\u200b",     value="\u200b",                               inline=True)

    # --- オープンポジション ---
    if open_positions:
        lines = []
        for p in open_positions:
            pnl_pct = (p["current_price"] - p["entry_price"]) / p["entry_price"] * 100
            arrow = "▲" if pnl_pct >= 0 else "▼"
            lines.append(
                f"`{p['symbol']:<8}` ${p['entry_price']:.6f} → ${p['current_price']:.6f}"
                f"  **{pnl_pct:+.1f}%** {arrow}"
            )
        embed.add_embed_field(
            name=f"\u200b\n📌 オープンポジション ({len(open_positions)}件)",
            value="\n".join(lines),
            inline=False,
        )
    else:
        embed.add_embed_field(
            name="📌 オープンポジション",
            value="なし",
            inline=False,
        )

    # --- 現在のパラメーター ---
    rsi_buy  = int(params.get("rsi_oversold", 30))
    rsi_sell = int(params.get("rsi_overbought", 70))
    sl_mult  = params.get("atr_sl_multiplier", 2.0)
    tp_mult  = params.get("atr_tp_multiplier", 3.0)
    w_chg    = params.get("weight_price_change", 0.4) * 100
    w_vol    = params.get("weight_volume", 0.3) * 100
    w_mc     = params.get("weight_mc", 0.3) * 100

    embed.add_embed_field(
        name="\u200b\n⚙️ 現在のパラメーター",
        value=(
            f"RSI 買い: **{rsi_buy}**  |  RSI 売り: **{rsi_sell}**\n"
            f"SL: **{sl_mult:.1f}x** ATR  |  TP: **{tp_mult:.1f}x** ATR\n"
            f"重み — 変動率: **{w_chg:.0f}%** / 出来高: **{w_vol:.0f}%** / MC: **{w_mc:.0f}%**"
        ),
        inline=False,
    )

    embed.set_footer(text="ShortSwing Bot | Paper Trade")
    _send(embed)


def notify_error(message: str):
    """エラー通知を送信する。"""
    embed = DiscordEmbed(title="⚠️ エラー", description=message, color=COLOR_ERROR)
    embed.set_footer(text="ShortSwing Bot")
    _send(embed)
