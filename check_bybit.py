import config
from data import data_fetcher
import ccxt

def check():
    exchange = data_fetcher.get_exchange()
    print("Fetching positions...")
    try:
        positions = exchange.fetch_positions([config.SYMBOL])
        for p in positions:
            if p.get('contracts', 0) > 0:
                print(f"OPEN POSITION: {p['side']} | {p['contracts']} | Entry: {p['entryPrice']}")
    except Exception as e:
        print(f"Error fetching positions: {e}")
        
    print("Fetching recent orders...")
    try:
        orders = exchange.fetch_orders(symbol=config.SYMBOL, limit=20)
        for o in orders:
            print(f"ORDER: {o['id']} | {o['datetime']} | {o['side']} | {o['status']} | {o['amount']} | {o['price']}")
    except Exception as e:
        print(f"Error fetching orders: {e}")

if __name__ == '__main__':
    check()
