"""
Notification Template Builders for NSFLUX.
Formats notification titles and messages cleanly for Telegram and Dashboard.
"""
from typing import Dict, Any, Optional
from notifications.events import NotificationEvent, NotificationLevel, EventCategory

def _severity_emoji(level: NotificationLevel) -> str:
    if level == NotificationLevel.CRITICAL:
        return "🚨"
    elif level == NotificationLevel.WARNING:
        return "⚠️"
    return "ℹ️"

def build_startup_summary(
    bot_version: str,
    environment: str,
    exchange: str,
    symbol: str,
    wallet_balance: float,
    risk_pct: float,
    strategy: str,
    hostname: str
) -> NotificationEvent:
    msg = (
        f"<b>🚀 NSFLUX System Online</b>\n"
        f"• <b>Version:</b> {bot_version}\n"
        f"• <b>Environment:</b> {environment}\n"
        f"• <b>Exchange:</b> {exchange.upper()}\n"
        f"• <b>Pair:</b> {symbol}\n"
        f"• <b>Wallet Balance:</b> ${wallet_balance:,.2f} USDT\n"
        f"• <b>Risk / Trade:</b> {risk_pct}%\n"
        f"• <b>Strategy Style:</b> {strategy}\n"
        f"• <b>Host:</b> {hostname}"
    )
    return NotificationEvent(
        event_type="bot_started",
        category=EventCategory.BOT_LIFECYCLE,
        level=NotificationLevel.INFO,
        title="NSFLUX Trading Engine Started",
        message=msg,
        details={
            "bot_version": bot_version,
            "environment": environment,
            "exchange": exchange,
            "symbol": symbol,
            "wallet_balance": wallet_balance,
            "risk_pct": risk_pct,
            "strategy": strategy,
            "hostname": hostname
        }
    )

def build_trade_opened(
    side: str,
    entry_price: float,
    amount_btc: float,
    wallet_balance: float,
    risk_pct: float,
    leverage: int,
    stop_loss: float,
    take_profit: float,
    confidence: int,
    reasons: list,
    indicators: dict,
    trade_id: str
) -> NotificationEvent:
    emoji = "🟢" if side.upper() in ("LONG", "BUY") else "🔴"
    reasons_str = "\n".join([f"  • {r}" for r in reasons[:3]]) if reasons else "  • Quantitative signal match"
    
    msg = (
        f"<b>{emoji} TRADE EXECUTION: {side.upper()} BTC/USDT</b>\n"
        f"• <b>Trade ID:</b> <code>{trade_id}</code>\n"
        f"• <b>Entry Price:</b> ${entry_price:,.2f}\n"
        f"• <b>Position Size:</b> {amount_btc:.6f} BTC\n"
        f"• <b>Leverage:</b> {leverage}x\n"
        f"• <b>Stop Loss:</b> ${stop_loss:,.2f}\n"
        f"• <b>Take Profit:</b> ${take_profit:,.2f}\n"
        f"• <b>Confidence:</b> {confidence}%\n"
        f"• <b>Account Balance:</b> ${wallet_balance:,.2f}\n"
        f"• <b>Key Signal Drivers:</b>\n{reasons_str}"
    )
    return NotificationEvent(
        event_type=f"{side.lower()}_opened",
        category=EventCategory.TRADING,
        level=NotificationLevel.INFO,
        title=f"{side.upper()} Position Opened",
        message=msg,
        details={
            "trade_id": trade_id,
            "side": side.upper(),
            "entry_price": entry_price,
            "amount_btc": amount_btc,
            "leverage": leverage,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "confidence": confidence,
            "indicators": indicators
        }
    )

def build_position_closed(
    trade_id: str,
    side: str,
    entry_price: float,
    exit_price: float,
    amount_btc: float,
    pnl_usdt: float,
    outcome: str,
    duration_min: float,
    exit_reason: str
) -> NotificationEvent:
    is_win = pnl_usdt >= 0
    emoji = "💰" if is_win else "🛑"
    outcome_tag = "WIN" if is_win else "LOSS"
    level = NotificationLevel.INFO if is_win else NotificationLevel.WARNING

    msg = (
        f"<b>{emoji} POSITION CLOSED: {side.upper()} ({outcome_tag})</b>\n"
        f"• <b>Trade ID:</b> <code>{trade_id}</code>\n"
        f"• <b>Entry Price:</b> ${entry_price:,.2f}\n"
        f"• <b>Exit Price:</b> ${exit_price:,.2f}\n"
        f"• <b>Size:</b> {amount_btc:.6f} BTC\n"
        f"• <b>Realized PnL:</b> <b>{'+' if is_win else ''}${pnl_usdt:,.2f} USDT</b>\n"
        f"• <b>Duration:</b> {duration_min:.1f} mins\n"
        f"• <b>Exit Trigger:</b> {exit_reason}"
    )
    
    event_type = "take_profit_hit" if "profit" in exit_reason.lower() else "stop_loss_hit" if "stop" in exit_reason.lower() else "position_closed"
    
    return NotificationEvent(
        event_type=event_type,
        category=EventCategory.TRADING,
        level=level,
        title=f"Position Closed: {outcome_tag} (${pnl_usdt:,.2f})",
        message=msg,
        details={
            "trade_id": trade_id,
            "side": side,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "pnl_usdt": pnl_usdt,
            "outcome": outcome,
            "exit_reason": exit_reason
        }
    )

def build_daily_summary(
    total_trades: int,
    wins: int,
    losses: int,
    win_rate: float,
    pnl_usdt: float,
    wallet_balance: float,
    uptime_str: str,
    open_positions: int,
    notif_stats: dict
) -> NotificationEvent:
    pnl_emoji = "📈" if pnl_usdt >= 0 else "📉"
    msg = (
        f"<b>📊 NSFLUX Daily Trading Summary</b>\n"
        f"• <b>Total Trades Today:</b> {total_trades}\n"
        f"• <b>Record:</b> {wins} W / {losses} L ({win_rate:.1f}% Win Rate)\n"
        f"• <b>Daily PnL:</b> {pnl_emoji} <b>{'+' if pnl_usdt >= 0 else ''}${pnl_usdt:,.2f} USDT</b>\n"
        f"• <b>Current Balance:</b> ${wallet_balance:,.2f} USDT\n"
        f"• <b>Active Positions:</b> {open_positions}\n"
        f"• <b>Bot Uptime:</b> {uptime_str}\n"
        f"• <b>Notifications Sent Today:</b> {notif_stats.get('successful', 0)} (Failed: {notif_stats.get('failed', 0)})"
    )
    return NotificationEvent(
        event_type="daily_summary",
        category=EventCategory.SYSTEM,
        level=NotificationLevel.INFO,
        title="Daily Performance Summary",
        message=msg,
        details={
            "total_trades": total_trades,
            "win_rate": win_rate,
            "pnl_usdt": pnl_usdt,
            "wallet_balance": wallet_balance
        }
    )

def build_heartbeat(
    status: str,
    wallet_balance: float,
    current_price: float,
    open_positions: int,
    cpu_pct: float,
    mem_pct: float,
    api_latency_ms: int,
    queue_len: int,
    last_notif_time: str
) -> NotificationEvent:
    msg = (
        f"<b>💓 NSFLUX System Heartbeat</b>\n"
        f"• <b>Status:</b> {status.upper()}\n"
        f"• <b>BTC Mark Price:</b> ${current_price:,.2f}\n"
        f"• <b>Wallet Balance:</b> ${wallet_balance:,.2f}\n"
        f"• <b>Open Positions:</b> {open_positions}\n"
        f"• <b>API Latency:</b> {api_latency_ms} ms\n"
        f"• <b>System Load:</b> CPU {cpu_pct:.1f}% | RAM {mem_pct:.1f}%\n"
        f"• <b>Notification Queue:</b> {queue_len} pending\n"
        f"• <b>Last Sent:</b> {last_notif_time or 'N/A'}"
    )
    return NotificationEvent(
        event_type="heartbeat",
        category=EventCategory.SYSTEM,
        level=NotificationLevel.INFO,
        title="NSFLUX 6-Hour Heartbeat",
        message=msg,
        details={
            "status": status,
            "current_price": current_price,
            "wallet_balance": wallet_balance,
            "api_latency_ms": api_latency_ms
        }
    )

def build_circuit_breaker(reason: str, errors_count: int) -> NotificationEvent:
    msg = (
        f"<b>🚨 CIRCUIT BREAKER TRIP TRIGGERED</b>\n"
        f"• <b>Severity:</b> CRITICAL\n"
        f"• <b>Consecutive Failures:</b> {errors_count}\n"
        f"• <b>Reason:</b> {reason}\n"
        f"• <b>Action:</b> Automated trading loop halted safely to protect capital. Manual intervention required."
    )
    return NotificationEvent(
        event_type="circuit_breaker_tripped",
        category=EventCategory.RISK,
        level=NotificationLevel.CRITICAL,
        title="Circuit Breaker Tripped",
        message=msg,
        details={"reason": reason, "errors_count": errors_count}
    )
