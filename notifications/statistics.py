"""
Runtime Notification Statistics Counter for NSFLUX.
"""
import threading
from datetime import datetime, timezone
from typing import Dict, Any

class NotificationStatistics:
    def __init__(self):
        self._lock = threading.Lock()
        self._today_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        self._stats = self._default_stats()

    def _default_stats(self) -> Dict[str, int]:
        return {
            "total": 0,
            "successful": 0,
            "failed": 0,
            "retried": 0,
            "INFO": 0,
            "WARNING": 0,
            "CRITICAL": 0,
            "BOT_LIFECYCLE": 0,
            "TRADING": 0,
            "EXCHANGE": 0,
            "RISK": 0,
            "SYSTEM": 0,
        }

    def _check_day_rollover(self):
        current_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if current_date != self._today_date:
            self._today_date = current_date
            self._stats = self._default_stats()

    def record_attempt(self, level: str, category: str):
        with self._lock:
            self._check_day_rollover()
            self._stats["total"] += 1
            lvl_key = (level.value if hasattr(level, "value") else str(level)).upper()
            if lvl_key in self._stats:
                self._stats[lvl_key] += 1
            cat_key = (category.value if hasattr(category, "value") else str(category)).upper()
            if cat_key in self._stats:
                self._stats[cat_key] += 1


    def record_success(self):
        with self._lock:
            self._check_day_rollover()
            self._stats["successful"] += 1

    def record_failure(self):
        with self._lock:
            self._check_day_rollover()
            self._stats["failed"] += 1

    def record_retry(self):
        with self._lock:
            self._check_day_rollover()
            self._stats["retried"] += 1

    def get_summary(self) -> Dict[str, Any]:
        with self._lock:
            self._check_day_rollover()
            res = dict(self._stats)
            res["date_utc"] = self._today_date
            return res
