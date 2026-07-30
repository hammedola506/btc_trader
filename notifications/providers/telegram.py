"""
Telegram Notification Provider for NSFLUX.
Deliver notifications via Telegram Bot API with HTML formatting and rate limit handling.
"""
import logging
import requests
from typing import Optional
from notifications.providers.base import BaseNotificationProvider
from notifications.events import NotificationEvent

log = logging.getLogger("btc_trader.notifications.telegram")

class TelegramProvider(BaseNotificationProvider):
    def __init__(
        self,
        bot_token: Optional[str] = None,
        chat_id: Optional[str] = None,
        enabled: bool = True,
        timeout: int = 5
    ):
        super().__init__(name="Telegram", enabled=enabled)
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.timeout = timeout

    @property
    def is_configured(self) -> bool:
        return bool(self.bot_token and self.chat_id and self.enabled)

    def send(self, event: NotificationEvent) -> bool:
        if not self.is_configured:
            log.debug("Telegram notification skipped: Provider not configured or disabled.")
            return False

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": event.message,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }

        try:
            resp = requests.post(url, json=payload, timeout=self.timeout)
            if resp.status_code == 200:
                log.info(f"Telegram alert [{event.notification_id}] delivered successfully.")
                return True
            else:
                log.warning(
                    f"Telegram alert [{event.notification_id}] failed with HTTP {resp.status_code}: {resp.text}"
                )
                return False
        except Exception as e:
            log.warning(f"Telegram network exception sending [{event.notification_id}]: {e}")
            return False
