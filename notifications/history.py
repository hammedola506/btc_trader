"""
Rolling Notification History Manager for NSFLUX.
Stores recent notification records thread-safely for UI display and APIs.
"""
import threading
from collections import deque
from typing import List, Dict, Any, Optional

class NotificationHistory:
    def __init__(self, max_size: int = 500):
        self.max_size = max_size
        self._history = deque(maxlen=max_size)
        self._lock = threading.Lock()

    def add(self, record: Dict[str, Any]):
        with self._lock:
            self._history.appendleft(record)

    def get_recent(
        self,
        limit: int = 50,
        level: Optional[str] = None,
        category: Optional[str] = None,
        event_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        with self._lock:
            results = list(self._history)

        if level:
            results = [r for r in results if r.get("level", "").upper() == level.upper()]
        if category:
            results = [r for r in results if r.get("category", "").upper() == category.upper()]
        if event_type:
            results = [r for r in results if r.get("event_type", "").lower() == event_type.lower()]

        return results[:limit]

    def clear(self):
        with self._lock:
            self._history.clear()

    def count(self) -> int:
        with self._lock:
            return len(self._history)
