"""
Notification Events and Enums for NSFLUX Trading Bot.
"""
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timezone
from typing import Any, Optional
import uuid

import itertools

_id_counter = itertools.count(1)

class NotificationLevel(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"

    @classmethod
    def priority(cls, level: Any) -> int:
        val = level.value if hasattr(level, "value") else str(level)
        levels = {"INFO": 1, "WARNING": 2, "CRITICAL": 3}
        return levels.get(str(val).upper(), 1)



class EventCategory(str, Enum):
    BOT_LIFECYCLE = "BOT_LIFECYCLE"
    TRADING = "TRADING"
    EXCHANGE = "EXCHANGE"
    RISK = "RISK"
    SYSTEM = "SYSTEM"


def generate_notification_id() -> str:
    """Generate a readable unique ID like NSF-20260730-000001."""
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    seq = next(_id_counter) % 1000000
    return f"NSF-{date_str}-{seq:06d}"


@dataclass
class NotificationEvent:
    event_type: str
    category: EventCategory
    level: NotificationLevel
    title: str
    message: str
    details: dict = field(default_factory=dict)
    notification_id: str = field(default_factory=generate_notification_id)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    dedup_key: str = field(default="")
    cooldown_sec: Optional[int] = field(default=None)

    def __post_init__(self):
        if not self.dedup_key:
            self.dedup_key = f"{self.category}:{self.event_type}"

    def to_dict(self) -> dict:
        return {
            "notification_id": self.notification_id,
            "timestamp": self.timestamp,
            "level": str(self.level),
            "category": str(self.category),
            "event_type": self.event_type,
            "title": self.title,
            "message": self.message,
            "details": self.details,
            "dedup_key": self.dedup_key,
        }
