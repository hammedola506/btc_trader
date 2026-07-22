import pandas as pd
import json
import logging

logging.basicConfig(level=logging.ERROR)

from strategies import strategy_test as strat

# Load historical data to test against
df = pd.read_csv("historical_data.csv")
# Convert types just in case
for col in ["open", "high", "low", "close", "volume"]:
    df[col] = pd.to_numeric(df[col])

print(f"Loaded {len(df)} rows.")

# We want to grab a slice that simulates the main branch being reached.
# Let's take the first 100 rows, then 101, etc., until tradeable is True.
for i in range(100, len(df), 50):
    slice_df = df.iloc[i-100:i].copy()
    res = strat.evaluate(slice_df)
    print(f"Row {i} - tradeable: {res['action'] != 'WAIT' or len(res['details'].get('candlestick_patterns') or '') > 0}")
    if res['action'] != 'WAIT' or (res['details'].get('candlestick_patterns') is not None):
        print(json.dumps(res, indent=2, default=str))
        break
