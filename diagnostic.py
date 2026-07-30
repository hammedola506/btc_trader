import re
import os
from dotenv import load_dotenv
import sys

# Need to add current dir to path to import config if needed, but we'll use ccxt directly
sys.path.append(os.getcwd())

load_dotenv()
log_path = 'logs/trading_bot.log'

try:
    with open(log_path, 'r') as f:
        lines = f.readlines()
except Exception as e:
    print(f"Error reading log: {e}")
    lines = []

errors = []
confidences = []
blocks = []
dates = []

for line in lines:
    if '|' in line:
        parts = line.split('|')
        if len(parts) > 0:
            date_str = parts[0].strip()
            # Simple assumption that first part is date if it looks like one
            if date_str.startswith('202'):
                dates.append(date_str)

print("=== 1. TIMESTAMPS / UPTIME ===")
if dates:
    print(f"First log entry: {dates[0]}")
    print(f"Last log entry: {dates[-1]}")
    print(f"Total log lines: {len(lines)}")
else:
    print("No timestamps found.")

print("\n=== 3. LAST 30 LINES ===")
for line in lines[-30:]:
    print(line.strip())

print("\n=== 2. ERRORS ===")
for line in lines:
    if 'Traceback' in line or 'Error' in line or 'Exception' in line or 'Failed' in line or 'CRITICAL' in line or 'Timeout' in line or 'Network' in line:
        errors.append(line.strip())
if errors:
    for e in errors[-20:]:  # show up to last 20
        print(e)
else:
    print("No errors found.")

print("\n=== 4. CONFIDENCE SCORES ===")
for line in lines:
    match = re.search(r'Confidence=(\d+)', line)
    if match:
        confidences.append(int(match.group(1)))
    
    if 'BLOCKED' in line:
        blocks.append(line.strip())

if confidences:
    print(f"Max confidence: {max(confidences)}")
    print(f"Recent confidences: {confidences[-10:]}")
else:
    print("No confidence scores found.")

print("\n=== 5. BLOCKED TRADES ===")
if blocks:
    for b in blocks[-20:]:
        print(b)
else:
    print("No blocked trades found.")

print("\n=== 6. EXCHANGE BALANCE CHECK ===")
try:
    import ccxt
    exchange = ccxt.bybit({
        'apiKey': os.environ.get("EXCHANGE_API_KEY", ""),
        'secret': os.environ.get("EXCHANGE_API_SECRET", ""),
        'enableRateLimit': True,
    })
    exchange.set_sandbox_mode(True)
    bal = exchange.fetch_balance()
    usdt = bal.get('USDT', {}).get('total', 0)
    print(f"Testnet Connection OK. USDT Balance: {usdt}")
except Exception as e:
    print(f"Exchange connection failed: {e}")
