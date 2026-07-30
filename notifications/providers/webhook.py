"""
Generic Webhook Notification Provider Placeholder for NSFLUX.
"""
import logging
from notifications.providers.base import BaseNotificationProvider
from notifications.events import NotificationEvent

log = logging.getLogger("btc_trader.notifications.webhook")

class WebhookProvider(BaseNotificationProvider):
    def __init__(self, target_url: str = "", enabled: bool = False):
        super().__init__(name="Webhook", enabled=enabled)
        self.target_url = target_url

    def send(self, event: NotificationEvent) -> bool:
        if not self.enabled or not self.target_url:
            return False
        log.info(f"[Webhook Placeholder] Would send event: {event.title}")
        return True
