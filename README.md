# 🚀 NSLUX — Automated BTC/USDT Algorithmic Trading System

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![Exchange](https://img.shields.io/badge/Exchange-Bybit%20(V5)-yellow.svg)](https://www.bybit.com)
[![Architecture](https://img.shields.io/badge/Architecture-Modular%20%2F%20Event--Driven-brightgreen.svg)]()
[![Container](https://img.shields.io/badge/Docker-Ready-blue)](Dockerfile)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

**NSLUX** is an institutional-grade, multi-strategy algorithmic trading bot engineered for BTC/USDT. It mirrors the decision-making of discretionary technical traders by combining **17+ candlestick pattern recognition algorithms**, **multi-indicator trend & momentum signals**, **Fibonacci & support/resistance structure analysis**, **dynamic ATR risk controls**, **real-time Telegram alerts**, and an **interactive web dashboard**.

---

## 📋 Table of Contents

- [Key Features](#-key-features)
- [System Architecture](#-system-architecture)
- [Trading Mechanics & Styles](#-trading-mechanics--styles)
- [Web Dashboard](#-web-dashboard)
- [Quick Start Guide](#-quick-start-guide)
  - [Prerequisites](#1-prerequisites)
  - [Environment Setup](#2-environment-setup)
  - [CLI Mode Execution](#3-cli-mode-execution)
  - [Web Dashboard Execution](#4-web-dashboard-execution)
- [Docker & Containerized Deployment](#-docker--containerized-deployment)
- [Configuration Reference](#-configuration-reference)
- [Backtesting & Analytics Suite](#-backtesting--analytics-suite)
- [Telegram Notification Subsystem](#-telegram-notification-subsystem)
- [Risk Management & Safety Precautions](#-risk-management--safety-precautions)
- [License & Disclaimer](#-license--disclaimer)

---

## ✨ Key Features

- **Candlestick Pattern Engine (`strategies/candlestick_patterns.py`)**: Identifies 17 distinct candlestick patterns (Hammers, Shooting Stars, Engulfing patterns, Morning/Evening Stars, Three White Soldiers, Marubozu, Tweezer Tops/Bottoms) weighted by structural strength.
- **Confluence Technical Analysis (`strategies/strategy.py`)**: Combines EMA crossovers, RSI momentum, MACD histogram divergence, volume confirmation, and Fibonacci support/resistance levels into a unified 0–100 conviction score.
- **Dynamic Risk Sizing (`execution/risk_manager.py`)**:
  - Automatic ATR (Average True Range) stop-loss and take-profit calculation.
  - Capital preservation via strict risk percentage per trade (e.g., 1–2% total account balance).
  - Exchange minimum lot-size validation & trade skip guards.
- **Multi-Mode Execution (`execution/executor.py`)**:
  - **Live Trading**: Automated execution on Bybit V5 API.
  - **Dry Run**: Realistic order simulation using real-time order books.
  - **Signal-Only Mode (`AUTO_TRADE_ENABLED=False`)**: Market setup evaluation and journaling without order placement—ideal for cloud monitoring.
- **Institutional Web Dashboard (`web/`)**: Dark-themed, responsive Flask/Gunicorn UI with cookie authentication, live log stream, auto-trade safety toggle, and historical signal viewer.
- **Telegram Notification Manager (`notifications/`)**: Instant notifications for trade execution, order skips, balance updates, and exchange disconnect/reconnect events.
- **Persistent State Manager (`state_manager.py`)**: SQLite-backed state tracking to prevent duplicate orders and ensure seamless recovery across system restarts.
- **Backtesting & Diagnostics Engine (`backtest.py`, `analyze_confidence_inversion.py`)**: Realistic historical simulation with zero lookahead bias and statistical confidence inversion analysis.

---

## 🏗 System Architecture

```text
NSLUX/
├── config.py                         # Global system configurations & thresholds
├── main.py                           # Core CLI trading engine entry point
├── state_manager.py                  # SQLite database state persistence
├── backtest.py                       # Historical backtesting CLI tool
├── analyze_confidence_inversion.py   # Signal performance & threshold analyzer
├── Dockerfile                        # Production multi-stage Docker build
├── docker-compose.yml                # Multi-container orchestration config
│
├── strategies/                       # Algorithmic Trading Strategy Engine
│   ├── strategy.py                   # Master confluence scoring logic (0-100)
│   ├── candlestick_patterns.py       # 17 Candlestick pattern detection rules
│   ├── indicators.py                 # EMA, RSI, MACD, Volume calculations
│   ├── support_resistance.py         # Dynamic S/R pivot level extraction
│   ├── fibonacci.py                  # Auto Fibonacci retracement & extension
│   ├── market_structure.py           # Trend structure (HH/HL/LH/LL) analyzer
│   └── trading_style.py              # Daily (15m) vs. Weekly (4h) presets
│
├── execution/                        # Order Placement & Risk Management
│   ├── executor.py                   # Exchange connector (Bybit V5 integration)
│   └── risk_manager.py               # ATR stops, position sizing & safety checks
│
├── web/                              # Institutional Dashboard Subsystem
│   ├── app.py                        # Flask WSGI web application server
│   ├── controller.py                 # Live bot control & safety toggles
│   ├── static/                       # Custom CSS, JS, and brand assets
│   └── templates/                    # Dashboard HTML UI templates
│
├── notifications/                    # Multi-Channel Alert Subsystem
│   ├── manager.py                    # Async notification dispatch controller
│   ├── events.py                     # Trade, Disconnect, Skip event models
│   ├── templates.py                  # Markdown alert template formatters
│   └── providers/                    # Telegram bot provider integration
│
├── journal/                          # Execution logs & trade journals
├── logs/                             # System operation logs
└── data/                             # SQLite DB & historical datasets
```

---

## 📈 Trading Mechanics & Styles

NSLUX supports two optimized operational profiles out of the box:

| Parameter | Daily Style ☀️ | Weekly Style 📅 |
| :--- | :--- | :--- |
| **Candle Timeframe** | 15 Minutes (`15m`) | 4 Hours (`4h`) |
| **Execution Check** | Every 60 seconds | Every 60 minutes |
| **Trade Frequency** | High (Intraday momentum) | Moderate/Low (Swing focus) |
| **Min Confidence** | 65 / 100 | 75 / 100 |
| **Stop Loss / TP** | Tighter ATR Multipliers | Wider ATR Multipliers |

To switch styles via CLI, launch `python3 main.py` and select option **1** (Daily) or **2** (Weekly).

---

## 🖥 Web Dashboard

The NSLUX Web Dashboard provides real-time oversight of the bot's operation:

- **Live Control Switch**: Toggle between `AUTO_TRADE_ENABLED` (Live order placement) and `SIGNAL_ONLY` (Observation mode) on the fly.
- **Real-Time Logs**: View color-coded execution logs directly in the browser.
- **Account Summary**: Monitor active portfolio balances, active trade positions, and daily profit/loss metrics.
- **Trade History & Journal**: Complete audit log of generated signals, confidence scores, and order execution statuses.

---

## 🚀 Quick Start Guide

### 1. Prerequisites

- **Python**: 3.10 or higher
- **Exchange Account**: Bybit (Mainnet or Testnet) with API Key permissions enabled for Read & Trade (Withdrawal rights **NOT** required).
- **Git**: Installed on system.

### 2. Environment Setup

Clone the repository and install requirements:

```bash
# Clone repository
git clone https://github.com/your-username/nslux.git
cd nslux

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Copy example environment configuration
cp .env.example .env
```

Edit your `.env` file with your credentials:

```env
# Exchange Configuration
EXCHANGE_ID=bybit
EXCHANGE_API_KEY=your_bybit_api_key
EXCHANGE_API_SECRET=your_bybit_api_secret

# Trading Engine Safety Settings
DRY_RUN=True
AUTO_TRADE_ENABLED=False

# Telegram Alerts (Optional)
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_telegram_chat_id

# Web Dashboard Security
SECRET_KEY=generate_a_secure_random_key_here
DASHBOARD_PASSWORD=admin_password_here
```

### 3. CLI Mode Execution

Run the trading engine directly via terminal:

```bash
python3 main.py
```

### 4. Web Dashboard Execution

Launch the Flask web server:

```bash
# Direct Python execution
python3 web/app.py

# Or run via Gunicorn WSGI server (Production mode)
gunicorn --bind 0.0.0.0:5000 web.app:app
```

Open your browser at `http://localhost:5000` to access the NSLUX Institutional Control Panel.

---

## 🐳 Docker & Containerized Deployment

NSLUX is containerized with a production multi-stage Docker build, featuring non-root container security, HEALTHCHECK support, and SQLite state persistence.

### Run with Docker Compose

```bash
# Build and start NSLUX in detached mode
docker-compose up -d --build

# View container logs
docker-compose logs -f

# Stop NSLUX container
docker-compose down
```

### Direct Docker Execution

```bash
# Build Docker image
docker build -t nslux:latest .

# Run container with environment file and data volume
docker run -d \
  --name nslux_bot \
  --env-file .env \
  -p 5000:5000 \
  -v nslux_data:/app/data \
  nslux:latest
```

---

## ⚙️ Configuration Reference

Key variables inside `config.py` and `.env`:

| Parameter | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `EXCHANGE_ID` | String | `bybit` | Target cryptocurrency exchange platform |
| `SYMBOL` | String | `BTC/USDT` | Trading pair symbol |
| `DRY_RUN` | Boolean | `True` | Set `False` for real money order placement |
| `AUTO_TRADE_ENABLED` | Boolean | `False` | Safety switch for signal-only vs live auto execution |
| `RISK_PER_TRADE_PCT` | Float | `0.01` (1%) | Account percentage risked per trade setup |
| `MIN_CONFIDENCE_TO_TRADE` | Int | `65` | Minimum conviction score required to enter trade |
| `TELEGRAM_NOTIFICATIONS_ENABLED` | Boolean | `True` | Master toggle for Telegram alert system |

---

## 📊 Backtesting & Analytics Suite

Before running live capital, backtest your strategy against historical Bybit candlestick data:

```bash
# Download 90 days of historical data from Bybit and execute backtest
python3 backtest.py --fetch --days 90 --style daily

# Run backtest against saved CSV dataset
python3 backtest.py --csv historical_data.csv --style weekly

# Analyze signal confidence threshold distribution
python3 analyze_confidence_inversion.py
```

The backtesting report generates:
- Win Rate (%) & Profit Factor
- Total Net Return & Maximum Drawdown
- Average Risk/Reward Ratio per trade
- Detailed trade log exported to `backtest_trades.csv`

---

## 📱 Telegram Notification Subsystem

NSLUX dispatches real-time structured markdown alerts directly to your Telegram chat:

- 🟢 **Trade Entry**: Executed orders with entry price, stop-loss, take-profit, and confidence breakdown.
- 🔴 **Trade Exit / Stop Trigger**: Execution results with net profit/loss.
- ⚠️ **Skipped Trade Alert**: Notifications when position sizing is constrained by lot-size minimums.
- 🔌 **Exchange Status**: Disconnect / reconnect warnings for webhooks & API feeds.

---

## 🛡️ Risk Management & Safety Precautions

> [!CAUTION]
> Cryptocurrency trading involves substantial risk of financial loss. NSLUX is designed for technical evaluation and automated assistance. Always observe strict risk practices:

1. **Testnet First**: Always run NSLUX on Bybit Testnet (`DRY_RUN=True`) before deploying real capital.
2. **API Permission Safety**: Ensure API keys have **NO Withdrawal Permissions**.
3. **Signal-Only Cloud Deployment**: When running on public cloud servers, set `AUTO_TRADE_ENABLED=False` to observe signals safely prior to authorizing live trade execution.
4. **Never Risk Critical Capital**: Set `RISK_PER_TRADE_PCT` conservative (1% - 2%).

---

## 📄 License & Disclaimer

Distributed under the **MIT License**. See `LICENSE` for details.

*Disclaimer: This software is provided for educational and research purposes only. Nothing contained in this codebase or documentation constitutes financial or investment advice. Users assume full responsibility for financial risk and exchange order outcomes.*
