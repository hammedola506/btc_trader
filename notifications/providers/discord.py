"""
Discord Notification Provider Placeholder for NSFLUX.
"""
import logging
from notifications.providers.base import BaseNotificationProvider
from notifications.events import NotificationEvent

log = logging.getLogger("btc_trader.notifications.discord")

class DiscordProvider(BaseNotificationProvider):
    def __init__(self, webhook_url: str = "", enabled: bool = False):
        super().__init__(name="Discord", enabled=enabled)
        self.webhook_url = webhook_url

    def send(self, event: NotificationEvent) -> bool:
        if not self.enabled or not self.webhook_url:
            return False
        log.info(f"[Discord Placeholder] Would send event: {event.title}")
        return True
