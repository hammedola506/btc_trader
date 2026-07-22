import csv

trades = []
with open('backtest_trades.csv') as f:
    for row in csv.DictReader(f):
        trades.append(row)

print('='*72)
print('POSITION SIZING & FEE MECHANICS PER TRADE')
print('='*72)
print()
print('Backtest fee model: 0.1% per side (entry + exit) = 0.2% round-trip')
print()

for t in trades:
    entry  = float(t['entry'])
    exit_  = float(t['exit'])
    gross  = float(t['gross_pnl'])
    fees   = float(t['fees'])
    net    = float(t['pnl_usdt'])
    bal_before = float(t['balance_after']) - net

    if t['side'] == 'LONG':
        pnl_per_coin = exit_ - entry
    else:
        pnl_per_coin = entry - exit_

    amount = gross / pnl_per_coin if abs(pnl_per_coin) > 0.001 else 0
    entry_value    = amount * entry
    exit_value     = amount * exit_
    expected_fees  = (entry_value + exit_value) * 0.001
    fee_vs_risk    = fees / (bal_before * 0.01) * 100

    print(f'  {t["entry_time"][:16]}  {t["side"]:5}')
    print(f'    Balance before : ${bal_before:>10,.2f}')
    print(f'    1% risk budget : ${bal_before*0.01:>10.2f}')
    print(f'    Amount (BTC)   : {amount:>10.6f}')
    print(f'    Trade value    : ${entry_value:>10.2f}  (entry notional)')
    print(f'    Fees           : ${fees:>10.2f}  (expected: ${expected_fees:.2f})')
    print(f'    Fees / risk    : {fee_vs_risk:>10.1f}%  <- fees as share of the 1% risk budget')
    print(f'    Gross PnL      : ${gross:>+10.2f}')
    print(f'    Net PnL        : ${net:>+10.2f}  [{t["outcome"]}]')
    print()

print('='*72)
print('GROSS:FEE RATIO — WHERE IS WIN/LOSS PARITY COMING FROM?')
print('='*72)
for t in trades:
    gross = float(t['gross_pnl'])
    fees  = float(t['fees'])
    ratio = abs(gross) / fees if fees > 0 else 0
    if fees > abs(gross):
        note = '  <- FEES EXCEED GROSS'
    elif fees / abs(gross) > 0.20:
        note = '  <- fees >20% of gross'
    else:
        note = ''
    print(f'  {t["entry_time"][:16]}  gross={gross:+.2f}  fees={fees:.2f}  '
          f'gross/fees={ratio:.2f}x{note}  [{t["outcome"]}]')

wins   = [t for t in trades if t['outcome'] == 'win']
losses = [t for t in trades if t['outcome'] == 'loss']
avg_w  = sum(float(t['pnl_usdt']) for t in wins)  / len(wins)
avg_l  = sum(float(t['pnl_usdt']) for t in losses) / len(losses)
print()
print(f'  Avg net win  = ${avg_w:.2f}')
print(f'  Avg net loss = ${avg_l:.2f}')
print(f'  R-ratio (net): {abs(avg_w/avg_l):.2f}x')
print()

# Duration analysis
from datetime import datetime
for t in trades:
    entry_dt = datetime.fromisoformat(t['entry_time'])
    exit_dt  = datetime.fromisoformat(t['exit_time'])
    duration = exit_dt - entry_dt
    hours = duration.total_seconds() / 3600
    gross = float(t['gross_pnl'])
    fees  = float(t['fees'])
    print(f'  {t["entry_time"][:16]}  hold={hours:.1f}h  gross={gross:+.2f}  fees={fees:.2f}  [{t["outcome"]}]')
