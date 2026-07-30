"""
Email Notification Provider Placeholder for NSFLUX.
"""
import logging
from notifications.providers.base import BaseNotificationProvider
from notifications.events import NotificationEvent

log = logging.getLogger("btc_trader.notifications.email")

class EmailProvider(BaseNotificationProvider):
    def __init__(self, smtp_host: str = "", enabled: bool = False):
        super().__init__(name="Email", enabled=enabled)
        self.smtp_host = smtp_host

    def send(self, event: NotificationEvent) -> bool:
        if not self.enabled or not self.smtp_host:
            return False
        log.info(f"[Email Placeholder] Would send event: {event.title}")
        return True
