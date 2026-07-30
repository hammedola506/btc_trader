"""
Abstract Base Notification Provider for NSFLUX.
"""
from abc import ABC, abstractmethod
from notifications.events import NotificationEvent

class BaseNotificationProvider(ABC):
    def __init__(self, name: str, enabled: bool = True):
        self._name = name
        self._enabled = enabled

    @property
    def name(self) -> str:
        return self._name

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool):
        self._enabled = bool(value)

    @abstractmethod
    def send(self, event: NotificationEvent) -> bool:
        """
        Send the notification event.
        Must return True if delivered successfully, False otherwise.
        Should catch network/provider exceptions internally and return False.
        """
        pass
