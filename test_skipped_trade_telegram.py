"""
Test script for verifying Telegram notification delivery on skipped trades due to minimum lot-size floor.
"""
import time
import logging
import sys

import config
from execution import risk_manager
import notifications

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("test_skipped_trade")

def test_telegram_skipped_trade():
    print("=" * 70)
    print("Testing Telegram Notification for Skipped Trade (Lot-Size Floor)")
    print("=" * 70)

    # Ensure notification manager is initialized
    mgr = notifications.init_notifications(config)
    
    # 1. Reset cooldown to simulate fresh event
    risk_manager.reset_lot_size_skip_cooldown()

    # 2. Simulate small balance ($50 USDT) causing calculated size (~0.00033 BTC) < 0.001 BTC minimum
    sim_balance = 50.0
    sim_price = 65000.0
    sim_atr = 1000.0
    sim_confidence = 85

    print(f"\nSimulating trade calculation:")
    print(f"  • Account Balance: ${sim_balance:.2f}")
    print(f"  • Entry Price: ${sim_price:.2f}")
    print(f"  • ATR: ${sim_atr:.2f}")
    print(f"  • Signal Confidence: {sim_confidence}%")

    res = risk_manager.calculate_derivative_position(
        balance_usdt=sim_balance,
        entry_price=sim_price,
        atr=sim_atr,
        direction="LONG",
        confidence=sim_confidence
    )

    print(f"\ncalculate_derivative_position() result: {res} (Expected: None)")
    assert res is None, "Expected None due to minimum lot size floor!"

    # Wait for background queue worker thread to process Telegram dispatch
    print("\nWaiting for background queue worker to dispatch to Telegram...")
    mgr._queue.join()
    time.sleep(1.0)

    history = notifications.get_history(limit=10)
    print(f"\nRecent Notification History ({len(history)} items):")
    target_event = None
    for item in history:
        print(f"  - [{item.get('notification_id')}] Type: {item.get('event_type')} | Status: {item.get('status')}")
        if item.get('event_type') == 'trade_skipped_lot_size':
            target_event = item

    if not target_event:
        print("\n❌ ERROR: Notification event not found in history!")
        sys.exit(1)

    print("\n" + "=" * 70)
    print("CONFIRMED NOTIFICATION DETAILS:")
    print("=" * 70)
    print(f"Notification ID: {target_event.get('notification_id')}")
    print(f"Status:          {target_event.get('status')}")
    print(f"Level:           {target_event.get('level')}")
    print(f"Category:        {target_event.get('category')}")
    print("\nMESSAGE CONTENT SENT TO TELEGRAM:")
    print("-" * 50)
    print(target_event.get('message'))
    print("-" * 50)

    # 3. Test Rate-Limiting (Immediate repeat call)
    print("\nTesting Rate-Limiting (calling calculate_derivative_position second time immediately)...")
    res2 = risk_manager.calculate_derivative_position(
        balance_usdt=sim_balance,
        entry_price=sim_price,
        atr=sim_atr,
        direction="LONG",
        confidence=sim_confidence
    )
    time.sleep(1.0)
    history_after = notifications.get_history(limit=10)
    skip_events = [item for item in history_after if item.get('event_type') == 'trade_skipped_lot_size']
    print(f"Skipped trade events recorded in history: {len(skip_events)} (Expected exactly 1 due to 1-hour rate limiting)")

    if target_event.get('status') == 'SUCCESSFUL' and len(skip_events) == 1:
        print("\n✅ TEST PASSED: Telegram message successfully sent to real Telegram API and rate-limited!")
    else:
        print(f"\n⚠️ Status check: status={target_event.get('status')}, count={len(skip_events)}")

if __name__ == "__main__":
    test_telegram_skipped_trade()
