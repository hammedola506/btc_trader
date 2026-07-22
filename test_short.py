import pandas as pd
import json
import logging
from unittest.mock import MagicMock

logging.basicConfig(level=logging.INFO)

import config
config.DRY_RUN = True
config.MIN_CONFIDENCE_TO_TRADE = 5  # very low

import main
from data import data_fetcher
from strategies import strategy

exchange = MagicMock()
data_fetcher.get_exchange = lambda: exchange
data_fetcher.get_account_balance = lambda ex, coin: 1000.0

df = pd.read_csv('historical_data.csv')
for col in ['open', 'high', 'low', 'close', 'volume']: df[col] = pd.to_numeric(df[col])

slice_end = 0
for i in range(100, len(df), 50):
    slice_df = df.iloc[i-100:i].copy()
    res = strategy.evaluate(slice_df)
    if res['action'] == 'SHORT':
        slice_end = i
        break

print(f"Testing SHORT on slice ending at row {slice_end}...")
data_fetcher.fetch_candles = lambda ex, **kwargs: df.iloc[slice_end-100:slice_end].copy()

open_position = main.run_once(exchange, None)
print("--- RETURNED OPEN POSITION ---")
print(json.dumps(open_position, indent=2))
