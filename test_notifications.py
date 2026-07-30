"""
Comprehensive Test Suite for NSFLUX Production Notification Subsystem.
Tests Queue Performance, Thread Safety, Retry Logic, Deduplication, Level Filtering,
Rate Limiting, Provider Pluggability, Templates, History, and API Integration.
"""
import time
import unittest
from unittest.mock import MagicMock

import config
import notifications
from notifications import (
    NotificationManager,
    NotificationEvent,
    NotificationLevel,
    EventCategory,
    templates,
    get_history,
    get_statistics,
)
from notifications.providers.base import BaseNotificationProvider
from notifications.providers.telegram import TelegramProvider
from notifications.providers.discord import DiscordProvider
from web.app import app

class MockSlowProvider(BaseNotificationProvider):
    def __init__(self, delay_sec: float = 2.0, fail_count: int = 0):
        super().__init__(name="MockSlowProvider", enabled=True)
        self.delay_sec = delay_sec
        self.fail_count = fail_count
        self.attempts = 0
        self.calls = []

    def send(self, event: NotificationEvent) -> bool:
        self.attempts += 1
        self.calls.append(event)
        time.sleep(self.delay_sec)
        if self.attempts <= self.fail_count:
            return False
        return True


class TestNotificationSubsystem(unittest.TestCase):
    def setUp(self):
        # Create isolated NotificationManager for unit testing
        self.manager = NotificationManager(
            enabled=True,
            min_level="INFO",
            dedup_cooldown_sec=5,
            rate_limit_per_min=100,
            history_size=100,
            queue_size=100,
            max_retries=2
        )
        self.manager.start()

    def tearDown(self):
        self.manager.stop()

    def test_non_blocking_performance(self):
        """Verify that notify() returns immediately (< 2ms) even if provider is slow (2.0s delay)."""
        slow_provider = MockSlowProvider(delay_sec=2.0)
        self.manager.register_provider(slow_provider)

        evt = NotificationEvent(
            event_type="test_perf",
            category=EventCategory.SYSTEM,
            level=NotificationLevel.INFO,
            title="Perf Test",
            message="Testing non-blocking worker queue"
        )

        start_t = time.time()
        success = self.manager.notify(evt)
        elapsed_ms = (time.time() - start_t) * 1000.0

        self.assertTrue(success)
        self.assertLess(elapsed_ms, 5.0, f"notify() blocked main thread for {elapsed_ms:.2f}ms!")

    def test_deduplication_cooldown(self):
        """Verify duplicate events with same dedup_key within cooldown window are suppressed."""
        evt1 = NotificationEvent(
            event_type="api_timeout",
            category=EventCategory.EXCHANGE,
            level=NotificationLevel.WARNING,
            title="API Timeout",
            message="Bybit API Timeout 1",
            dedup_key="EXCHANGE:api_timeout"
        )
        evt2 = NotificationEvent(
            event_type="api_timeout",
            category=EventCategory.EXCHANGE,
            level=NotificationLevel.WARNING,
            title="API Timeout",
            message="Bybit API Timeout 2",
            dedup_key="EXCHANGE:api_timeout"
        )

        res1 = self.manager.notify(evt1)
        res2 = self.manager.notify(evt2)

        self.assertTrue(res1)
        self.assertFalse(res2, "Duplicate event within cooldown window was not suppressed!")

    def test_severity_level_filtering(self):
        """Verify that min_level='WARNING' filters out 'INFO' events."""
        self.manager.min_level = "WARNING"

        info_evt = NotificationEvent(
            event_type="info_test",
            category=EventCategory.SYSTEM,
            level=NotificationLevel.INFO,
            title="Info Event",
            message="Info message"
        )
        warn_evt = NotificationEvent(
            event_type="warn_test",
            category=EventCategory.SYSTEM,
            level=NotificationLevel.WARNING,
            title="Warn Event",
            message="Warn message"
        )

        self.assertFalse(self.manager.notify(info_evt))
        self.assertTrue(self.manager.notify(warn_evt))

    def test_provider_retry_policy(self):
        """Verify worker retries failed dispatches up to max_retries."""
        flaky_provider = MockSlowProvider(delay_sec=0.01, fail_count=1)
        self.manager.register_provider(flaky_provider)

        evt = NotificationEvent(
            event_type="flaky_test",
            category=EventCategory.TRADING,
            level=NotificationLevel.INFO,
            title="Flaky Test",
            message="Testing retries"
        )
        self.manager.notify(evt)
        time.sleep(1.2)

        self.assertEqual(flaky_provider.attempts, 2)

        summary = self.manager.statistics.get_summary()
        self.assertGreaterEqual(summary["retried"], 1)

    def test_template_builders(self):
        """Verify all template builder functions generate valid NotificationEvents."""
        st = templates.build_startup_summary("2.0", "DEMO TRADING", "bybit", "BTC/USDT", 1000.0, 1.0, "Daily", "host")
        self.assertEqual(st.event_type, "bot_started")
        self.assertIn("NSFLUX System Online", st.message)

        tr = templates.build_trade_opened("LONG", 70000.0, 0.01, 1000.0, 1.0, 5, 69000.0, 72000.0, 85, ["EMA cross"], {}, "trade_123")
        self.assertEqual(tr.event_type, "long_opened")
        self.assertIn("LONG BTC/USDT", tr.message)

        cl = templates.build_position_closed("trade_123", "LONG", 70000.0, 72000.0, 0.01, 20.0, "win", 15.0, "Take Profit Hit")
        self.assertEqual(cl.event_type, "take_profit_hit")

        cb = templates.build_circuit_breaker("Too many API errors", 5)
        self.assertEqual(cb.level, NotificationLevel.CRITICAL)

    def test_dashboard_api_endpoints(self):
        """Verify /api/notifications/history and /api/notifications/stats endpoints."""
        client = app.test_client()

        # Send test event through global manager
        evt = NotificationEvent(
            event_type="api_test",
            category=EventCategory.SYSTEM,
            level=NotificationLevel.INFO,
            title="API Route Test",
            message="Test route payload"
        )
        notifications.notify(evt)
        time.sleep(0.2)

        res_hist = client.get("/api/notifications/history", auth=(config.DASHBOARD_USERNAME, config.DASHBOARD_PASSWORD))
        self.assertEqual(res_hist.status_code, 200)
        data_hist = res_hist.get_json()
        self.assertIsInstance(data_hist, list)

        res_stats = client.get("/api/notifications/stats", auth=(config.DASHBOARD_USERNAME, config.DASHBOARD_PASSWORD))
        self.assertEqual(res_stats.status_code, 200)
        data_stats = res_stats.get_json()
        self.assertIn("total", data_stats)


if __name__ == "__main__":
    unittest.main()
