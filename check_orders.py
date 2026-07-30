import config
from data import data_fetcher
import json

def check_orders():
    print(f"Checking orders on {config.EXCHANGE_ID} (testnet: {config.USE_TESTNET})...")
    exchange = data_fetcher.get_exchange()
    
    try:
        # Fetch recent orders
        orders = exchange.fetch_orders(symbol=config.SYMBOL, limit=10)
        print("\n--- Recent Orders ---")
        for o in orders:
            print(f"[{o['datetime']}] ID: {o['id']} | Side: {o['side']} | Status: {o['status']} | Amount: {o['amount']} | Price: {o.get('price') or o.get('average')}")
        
        # Fetch current positions
        positions = exchange.fetch_positions([config.SYMBOL])
        print("\n--- Current Positions ---")
        for p in positions:
            if p['contracts'] > 0:
                print(f"Position: {p['side']} | Contracts: {p['contracts']} | Entry Price: {p['entryPrice']}")
    except Exception as e:
        print(f"Error checking orders: {e}")

if __name__ == '__main__':
    check_orders()
