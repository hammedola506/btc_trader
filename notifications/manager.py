"""
Production Notification Manager and Dispatcher for NSFLUX.
Handles non-blocking queuing, rate limiting, deduplication, exponential backoff retries,
and distribution to registered providers.
"""
import time
import queue
import threading
import logging
from typing import List, Dict, Optional, Any

from notifications.events import NotificationEvent, NotificationLevel, EventCategory
from notifications.history import NotificationHistory
from notifications.statistics import NotificationStatistics
from notifications.providers.base import BaseNotificationProvider

log = logging.getLogger("btc_trader.notifications.manager")

class NotificationManager:
    def __init__(
        self,
        enabled: bool = True,
        min_level: str = "INFO",
        dedup_cooldown_sec: int = 60,
        rate_limit_per_min: int = 30,
        history_size: int = 500,
        queue_size: int = 500,
        max_retries: int = 3
    ):
        self.enabled = enabled
        self.min_level = min_level.upper()
        self.dedup_cooldown_sec = dedup_cooldown_sec
        self.rate_limit_per_min = rate_limit_per_min
        self.max_retries = max_retries

        self.history = NotificationHistory(max_size=history_size)
        self.statistics = NotificationStatistics()

        self._providers: List[BaseNotificationProvider] = []
        self._queue: queue.Queue = queue.Queue(maxsize=queue_size)
        
        self._dedup_cache: Dict[str, float] = {}
        self._dedup_lock = threading.Lock()

        self._rate_timestamps: List[float] = []
        self._rate_lock = threading.Lock()

        self._stop_event = threading.Event()
        self._worker_thread: Optional[threading.Thread] = None

    def register_provider(self, provider: BaseNotificationProvider):
        """Register a notification provider plugin."""
        self._providers.append(provider)
        log.info(f"Registered notification provider: {provider.name} (enabled={provider.enabled})")

    def start(self):
        """Start the background worker thread."""
        if self._worker_thread and self._worker_thread.is_alive():
            return
        self._stop_event.clear()
        self._worker_thread = threading.Thread(target=self._worker_loop, daemon=True, name="NotificationWorker")
        self._worker_thread.start()
        log.info("Notification Manager background worker started.")

    def stop(self, timeout: float = 3.0):
        """Signal background worker to stop gracefully."""
        self._stop_event.set()
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=timeout)
        log.info("Notification Manager stopped.")

    def notify(self, event: NotificationEvent) -> bool:
        """
        Public non-blocking entry point.
        Enqueues event for background delivery. NEVER blocks trading execution.
        """
        if not self.enabled:
            return False

        # Level filtering check
        if NotificationLevel.priority(event.level) < NotificationLevel.priority(self.min_level):
            log.debug(f"Event [{event.notification_id}] filtered out by min_level={self.min_level}")
            return False

        # Deduplication check
        now = time.time()
        with self._dedup_lock:
            last_sent = self._dedup_cache.get(event.dedup_key, 0)
            if now - last_sent < self.dedup_cooldown_sec:
                log.debug(f"Event [{event.notification_id}] suppressed as duplicate (dedup_key={event.dedup_key})")
                return False
            self._dedup_cache[event.dedup_key] = now

        try:
            self._queue.put_nowait(event)
            return True
        except queue.Full:
            log.warning(f"Notification queue FULL ({self._queue.maxsize}). Dropped event [{event.notification_id}].")
            return False
        except Exception as e:
            log.error(f"Error enqueuing notification event: {e}")
            return False

    def _check_rate_limit(self):
        """Rate limit helper: pauses worker thread if dispatch rate exceeds limit."""
        with self._rate_lock:
            now = time.time()
            # Prune timestamps older than 60 seconds
            self._rate_timestamps = [t for t in self._rate_timestamps if now - t < 60]
            if len(self._rate_timestamps) >= self.rate_limit_per_min:
                sleep_needed = 60.0 - (now - self._rate_timestamps[0])
                if sleep_needed > 0:
                    log.warning(f"Notification rate limit reached ({self.rate_limit_per_min}/min). Pausing {sleep_needed:.1f}s.")
                    time.sleep(sleep_needed)
            self._rate_timestamps.append(time.time())

    def _dispatch_to_providers(self, event: NotificationEvent) -> bool:
        """Attempt to deliver event across all enabled active providers with retries."""
        self.statistics.record_attempt(event.level, event.category)
        
        active_providers = [p for p in self._providers if p.enabled and getattr(p, "is_configured", True)]
        if not active_providers:
            # If no external provider configured/enabled, still log to history & stats as success
            rec = event.to_dict()
            rec["status"] = "SUCCESSFUL (INTERNAL)"
            self.history.add(rec)
            self.statistics.record_success()
            return True


        overall_success = False

        for provider in active_providers:
            success = False
            for attempt in range(1, self.max_retries + 1):
                self._check_rate_limit()
                
                try:
                    success = provider.send(event)
                except Exception as e:
                    log.error(f"Provider {provider.name} exception on attempt {attempt}: {e}")
                    success = False

                if success:
                    if attempt > 1:
                        self.statistics.record_retry()
                    break
                else:
                    if attempt < self.max_retries:
                        backoff = 2 ** (attempt - 1)  # 1s, 2s, 4s...
                        log.info(f"Retrying delivery for [{event.notification_id}] via {provider.name} in {backoff}s...")
                        time.sleep(backoff)

            if success:
                overall_success = True

        rec = event.to_dict()
        rec["status"] = "SUCCESSFUL" if overall_success else "FAILED"
        self.history.add(rec)

        if overall_success:
            self.statistics.record_success()
        else:
            self.statistics.record_failure()

        return overall_success

    def _worker_loop(self):
        """Background thread loop processing queued events."""
        while not self._stop_event.is_set() or not self._queue.empty():
            try:
                event: NotificationEvent = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue

            try:
                self._dispatch_to_providers(event)
            except Exception as e:
                log.error(f"Unhandled error in notification worker dispatch: {e}")
            finally:
                self._queue.task_done()
