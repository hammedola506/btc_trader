"""
State Manager: Persists the bot's open position state to disk so it can survive
crashes, server reboots, and network disconnects. Without this, the bot assumes
it is flat upon restart and would double-enter or abandon existing trades.
"""
import json
import os

STATE_FILE = "logs/bot_state.json"

def save_state(open_position):
    """Save the open position dict to a JSON file."""
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(open_position, f, indent=4)

def load_state(exchange, symbol):
    """
    Load the open position from disk and verify it still exists on the exchange.
    If the bot crashed, the exchange is the source of truth.
    """
    if not os.path.exists(STATE_FILE):
        return None
        
    try:
        with open(STATE_FILE, "r") as f:
            state = json.load(f)
            
        if not state:
            return None
            
        print(f"[state_manager] Found saved state for {symbol}. Verifying with exchange...")
        
        # Verify against exchange open orders
        # If the TP or SL limit orders are still active, the position is still active.
        try:
            open_orders = exchange.fetch_open_orders(symbol)
            if not open_orders:
                print("[state_manager] Saved state exists, but no open orders found on exchange. Assuming position closed while bot was offline.")
                # We clear the state because the trade is over.
                clear_state()
                return None
                
            print("[state_manager] Exchange verification successful. Resuming trade monitoring.")
            return state
            
        except Exception as e:
            print(f"[state_manager] Warning: Could not verify orders with exchange: {e}")
            print("[state_manager] Resuming with saved state anyway to be safe.")
            return state
            
    except Exception as e:
        print(f"[state_manager] Failed to load state file: {e}")
        return None

def clear_state():
    """Clear the saved state when a position closes."""
    save_state(None)
