"""
Live verification test for Exchange Disconnected and Reconnected Telegram alerts.
"""
import time
import logging
import sys
import ccxt

import config
from data import data_fetcher
import notifications

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("test_exchange_disconnect")


def test_disconnect_reconnect_alerts():
    print("=" * 70)
    print("Live Test: Exchange Disconnection & Reconnection Telegram Alerts")
    print("=" * 70)

    mgr = notifications.init_notifications(config)
    data_fetcher.reset_connection_state()

    print("\n1. Simulating 2 consecutive exchange network failures (ccxt.NetworkError)...")

    def failing_fn():
        raise ccxt.NetworkError("HTTPSConnectionPool(host='api-demo.bybit.com', port=443): Max retries exceeded with url: /v5/market/tickers (Caused by NameResolutionError)")

    # Attempt 1 (Consecutive failures = 1, threshold = 2)
    try:
        data_fetcher.retry_api_call(failing_fn, func_name="fetch_ticker", max_retries=1, initial_delay=0.1)
    except ccxt.NetworkError:
        print("  • Failure 1 recorded.")

    # Attempt 2 (Consecutive failures = 2 -> Triggers exchange_disconnected notification!)
    try:
        data_fetcher.retry_api_call(failing_fn, func_name="fetch_ticker", max_retries=1, initial_delay=0.1)
    except ccxt.NetworkError:
        print("  • Failure 2 recorded (Threshold crossed -> Disconnect notification dispatched).")

    # Give worker thread time to process and deliver notification
    print("\nWaiting for disconnect alert worker dispatch...")
    mgr._queue.join()
    time.sleep(2.0)

    history = notifications.get_history(limit=10)
    disconn_evt = next((item for item in history if item.get("event_type") == "exchange_disconnected"), None)

    if not disconn_evt:
        print("❌ ERROR: exchange_disconnected notification not found in history!")
        sys.exit(1)

    print("\n" + "=" * 70)
    print("DISCONNECTED ALERT CONFIRMED:")
    print("=" * 70)
    print(f"Notification ID: {disconn_evt.get('notification_id')}")
    print(f"Status:          {disconn_evt.get('status')}")
    print("\nMESSAGE DELIVERED TO TELEGRAM:")
    print("-" * 50)
    print(disconn_evt.get("message"))
    print("-" * 50)

    # 2. Now simulate API recovery (successful call)
    print("\n2. Simulating API recovery (successful API call)...")
    time.sleep(1.5)  # Simulate short downtime duration

    def successful_fn():
        return {"symbol": "BTC/USDT", "last": 70000.0}

    res = data_fetcher.retry_api_call(successful_fn, func_name="fetch_ticker", max_retries=1)
    print(f"  • Successful API call result: {res}")

    print("\nWaiting for reconnected alert worker dispatch...")
    mgr._queue.join()
    time.sleep(2.0)

    history_after = notifications.get_history(limit=10)
    reconn_evt = next((item for item in history_after if item.get("event_type") == "exchange_reconnected"), None)

    if not reconn_evt:
        print("❌ ERROR: exchange_reconnected notification not found in history!")
        sys.exit(1)

    print("\n" + "=" * 70)
    print("RECONNECTED ALERT CONFIRMED:")
    print("=" * 70)
    print(f"Notification ID: {reconn_evt.get('notification_id')}")
    print(f"Status:          {reconn_evt.get('status')}")
    print("\nMESSAGE DELIVERED TO TELEGRAM:")
    print("-" * 50)
    print(reconn_evt.get("message"))
    print("-" * 50)

    if disconn_evt.get("status") == "SUCCESSFUL" and reconn_evt.get("status") == "SUCCESSFUL":
        print("\n✅ LIVE TEST PASSED: Both Disconnect and Reconnect alerts delivered successfully to Telegram!")
    else:
        print(f"\n⚠️ Status check: disconn={disconn_evt.get('status')}, reconn={reconn_evt.get('status')}")


if __name__ == "__main__":
    test_disconnect_reconnect_alerts()
