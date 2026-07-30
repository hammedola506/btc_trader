"""
NSFLUX Production Notification System Top-Level Module.
"""
import os
import logging
from typing import Optional, Dict, Any, List

from notifications.events import NotificationEvent, NotificationLevel, EventCategory, generate_notification_id
from notifications.manager import NotificationManager
from notifications.providers.telegram import TelegramProvider
from notifications import templates

log = logging.getLogger("btc_trader.notifications")

_global_manager: Optional[NotificationManager] = None

def init_notifications(config_module=None) -> NotificationManager:
    global _global_manager
    if _global_manager is not None:
        return _global_manager

    enabled = getattr(config_module, "NOTIFICATION_ENABLED", True)
    min_level = getattr(config_module, "NOTIFICATION_MIN_LEVEL", "INFO")
    dedup_sec = getattr(config_module, "NOTIFICATION_DEDUP_COOLDOWN_SEC", 60)
    rate_limit = getattr(config_module, "NOTIFICATION_RATE_LIMIT", 30)
    history_size = getattr(config_module, "NOTIFICATION_HISTORY_SIZE", 500)

    manager = NotificationManager(
        enabled=enabled,
        min_level=min_level,
        dedup_cooldown_sec=dedup_sec,
        rate_limit_per_min=rate_limit,
        history_size=history_size
    )

    # Register Telegram Provider
    tg_enabled = getattr(config_module, "TELEGRAM_ENABLED", True)
    tg_token = getattr(config_module, "TELEGRAM_BOT_TOKEN", os.environ.get("TELEGRAM_BOT_TOKEN", ""))
    tg_chat_id = getattr(config_module, "TELEGRAM_CHAT_ID", os.environ.get("TELEGRAM_CHAT_ID", ""))
    
    telegram_provider = TelegramProvider(
        bot_token=tg_token,
        chat_id=tg_chat_id,
        enabled=tg_enabled
    )
    manager.register_provider(telegram_provider)

    manager.start()
    _global_manager = manager
    log.info(f"Initialized NSFLUX Notification System (min_level={min_level}, telegram_configured={telegram_provider.is_configured})")
    return manager

def get_manager() -> NotificationManager:
    global _global_manager
    if _global_manager is None:
        # Fallback initialization with default configuration
        import config
        return init_notifications(config)
    return _global_manager

def notify(event: NotificationEvent) -> bool:
    """Public top-level non-blocking notification call."""
    mgr = get_manager()
    return mgr.notify(event)

def stop_notifications():
    global _global_manager
    if _global_manager:
        _global_manager.stop()
        _global_manager = None

def get_history(limit: int = 50, level: str = None, category: str = None) -> List[Dict[str, Any]]:
    mgr = get_manager()
    return mgr.history.get_recent(limit=limit, level=level, category=category)

def get_statistics() -> Dict[str, Any]:
    mgr = get_manager()
    return mgr.statistics.get_summary()
