import sqlite3
import pandas as pd
from unittest.mock import MagicMock
import config
config.DRY_RUN = True
config.MIN_CONFIDENCE_TO_TRADE = 10

import main
from data import data_fetcher
from journal import trade_journal

# Count rows in journal before test
conn = sqlite3.connect(trade_journal.DB_FILE)
cursor = conn.cursor()
cursor.execute("SELECT COUNT(*) FROM journal")
count_before = cursor.fetchone()[0]

exchange = MagicMock()
data_fetcher.get_exchange = lambda: exchange
data_fetcher.get_account_balance = lambda ex, coin: 1000.0

df = pd.read_csv('historical_data.csv')
for col in ['open', 'high', 'low', 'close', 'volume']:
    df[col] = pd.to_numeric(df[col])

# Find a slice that produces a LONG signal
slice_df = df.iloc[0:150].copy()
data_fetcher.fetch_candles = lambda ex, **kwargs: slice_df

print("--- Test 1: Run with auto_trade_enabled=False ---")
res1 = main.run_once(exchange, open_position=None, auto_trade_enabled=False)
print(f"run_once result (auto_trade=False): {res1}")

cursor.execute("SELECT trade_id, timestamp, decision, symbol, entry_price FROM journal ORDER BY rowid DESC LIMIT 1")
latest_row1 = cursor.fetchone()
print(f"Latest DB Row after Test 1: {latest_row1}")

print("\n--- Test 2: Run with auto_trade_enabled=True ---")
res2 = main.run_once(exchange, open_position=None, auto_trade_enabled=True)
print(f"run_once result (auto_trade=True): {res2}")

cursor.execute("SELECT trade_id, timestamp, decision, symbol, entry_price FROM journal ORDER BY rowid DESC LIMIT 2")
latest_rows = cursor.fetchall()
print("Latest DB Rows after Test 2:")
for r in latest_rows:
    print("  ", r)

cursor.execute("SELECT COUNT(*) FROM journal")
count_after = cursor.fetchone()[0]
print(f"\nTotal new journal rows added across both tests: {count_after - count_before}")
conn.close()
