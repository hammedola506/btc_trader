// DOM Elements
const elPrice = document.getElementById('live-price');
const elStatusDot = document.getElementById('status-dot');
const elStatusText = document.getElementById('status-text');
const elBtnStart = document.getElementById('btn-start');
const elBtnStop = document.getElementById('btn-stop');

const elSignalBadge = document.getElementById('signal-badge');
const elConfidenceValue = document.getElementById('confidence-value');
const elPulseRing = document.getElementById('pulse-ring');
const elEngineFeed = document.getElementById('engine-feed');

const elMsBias = document.getElementById('ms-bias');
const elMsTrend = document.getElementById('ms-trend');
const elMsCatalyst = document.getElementById('ms-catalyst');

const elHypoEmpty = document.getElementById('hypo-empty');
const elHypoActive = document.getElementById('hypo-active');
const elHypoEntry = document.getElementById('hypo-entry');
const elHypoSL = document.getElementById('hypo-sl');
const elHypoTP = document.getElementById('hypo-tp');
const elHypoSize = document.getElementById('hypo-size');
const elHypoMargin = document.getElementById('hypo-margin');

const elTradeEmpty = document.getElementById('trade-empty');
const elTradeActive = document.getElementById('trade-active');
const elTradeSide = document.getElementById('trade-side');
const elTradeEntry = document.getElementById('trade-entry');
const elTradeSize = document.getElementById('trade-size');
const elTradeSL = document.getElementById('trade-sl');
const elTradeTP = document.getElementById('trade-tp');
const elTradePnL = document.getElementById('trade-pnl');

const elToast = document.getElementById('toast');
const elBtnStyleDaily = document.getElementById('btn-style-daily');
const elBtnStyleWeekly = document.getElementById('btn-style-weekly');

const elBtnRunBacktest = document.getElementById('btn-run-backtest');
const elBacktestMsg = document.getElementById('backtest-msg');

let pollInterval;
let backtestPollInterval = null;
let isBacktestRunning = false;

// Engine Feed Memory
let lastCatalyst = "";

// Utils
function showToast(message, isError = false) {
    elToast.textContent = message;
    elToast.style.background = isError ? 'var(--neon-red)' : 'var(--neon-cyan)';
    elToast.classList.remove('hidden');
    setTimeout(() => elToast.classList.add('hidden'), 4000);
}

function formatPrice(price) {
    if (!price) return '--.--';
    return parseFloat(price).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function addFeedLine(text) {
    if (lastCatalyst === text) return;
    lastCatalyst = text;
    const div = document.createElement('div');
    div.className = 'feed-line';
    div.textContent = text;
    elEngineFeed.appendChild(div);
    elEngineFeed.scrollTop = elEngineFeed.scrollHeight;
    
    // Keep only last 20 lines
    if (elEngineFeed.children.length > 20) {
        elEngineFeed.removeChild(elEngineFeed.firstChild);
    }
}

// API Calls
async function fetchStatus() {
    try {
        const response = await fetch('/api/status');
        if (!response.ok) throw new Error('Network response was not ok');
        const data = await response.json();
        updateUI(data);
    } catch (error) {
        console.error("Status fetch failed:", error);
    }
}

async function controlBot(action) {
    try {
        const response = await fetch(`/api/${action}`, { method: 'POST' });
        const data = await response.json();
        showToast(data.message, !data.success);
        fetchStatus(); 
    } catch (error) {
        showToast(`Failed to ${action} bot.`, true);
    }
}

async function fetchStats() {
    try {
        const response = await fetch('/api/stats');
        if (!response.ok) return;
        const data = await response.json();
        document.getElementById('stat-total').textContent = data.total_trades || 0;
        document.getElementById('stat-winrate').textContent = `${(data.win_rate || 0).toFixed(1)}%`;
        
        const pnlEl = document.getElementById('stat-pnl');
        pnlEl.textContent = '$' + formatPrice(data.total_pnl_usdt || 0);
        if (data.total_pnl_usdt > 0) pnlEl.className = 'font-data text-xl text-green';
        else if (data.total_pnl_usdt < 0) pnlEl.className = 'font-data text-xl text-red';
        else pnlEl.className = 'font-data text-xl text-pure';
    } catch (e) {
        console.error("Stats fetch failed", e);
    }
}

async function fetchJournal() {
    try {
        const response = await fetch('/api/journal');
        if (!response.ok) return;
        const data = await response.json();
        const tbody = document.getElementById('journal-body');
        tbody.innerHTML = '';
        
        if (!data || data.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" class="text-dim" style="text-align:center;">No vectors executed yet.</td></tr>';
            return;
        }
        
        data.forEach(trade => {
            const tr = document.createElement('tr');
            
            let pnlHtml = '<span>--</span>';
            if (trade.pnl_usdt !== null) {
                const color = trade.pnl_usdt > 0 ? 'text-green' : (trade.pnl_usdt < 0 ? 'text-red' : '');
                pnlHtml = `<span class="${color}">$${formatPrice(trade.pnl_usdt)}</span>`;
            }
            
            const sideClass = trade.decision === 'LONG' ? 'text-green' : 'text-red';
            
            tr.innerHTML = `
                <td class="text-dim">${trade.timestamp ? new Date(trade.timestamp).toLocaleTimeString() : '--'}</td>
                <td>BTC/USDT</td>
                <td><strong class="${sideClass}">${trade.decision}</strong></td>
                <td>${trade.entry_price !== null ? '$'+formatPrice(trade.entry_price) : '--'}</td>
                <td>${trade.exit_price !== null ? '$'+formatPrice(trade.exit_price) : '--'}</td>
                <td>${pnlHtml}</td>
                <td class="${trade.outcome === 'WIN' ? 'text-green' : (trade.outcome === 'LOSS' ? 'text-red' : 'text-dim')}">${trade.outcome || '--'}</td>
            `;
            tbody.appendChild(tr);
        });
    } catch (e) {
        console.error("Journal fetch failed", e);
    }
}

async function setStyle(style) {
    try {
        const response = await fetch('/api/style', { 
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({style: style})
        });
        const data = await response.json();
        showToast(data.message, !data.success);
        if (data.success) fetchStatus();
    } catch (e) {
        showToast(`Failed to set style.`, true);
    }
}

async function startBacktest() {
    try {
        const response = await fetch('/api/backtest/start', { method: 'POST' });
        const data = await response.json();
        showToast(data.message, !data.success);
        if (data.success) pollBacktestStatus();
    } catch (e) {
        showToast(`Failed to start backtest.`, true);
    }
}

async function checkBacktestStatus() {
    try {
        const response = await fetch('/api/backtest/status');
        const data = await response.json();
        
        isBacktestRunning = (data.status === 'running');
        
        if (data.status === 'idle') {
            // do nothing
        } else if (data.status === 'running') {
            elBacktestMsg.classList.remove('hidden');
            elBtnRunBacktest.disabled = true;
        } else if (data.status === 'error') {
            elBacktestMsg.classList.remove('hidden');
            elBacktestMsg.textContent = data.error || 'Backtest failed.';
            elBacktestMsg.className = 'text-red text-xs';
            elBtnRunBacktest.disabled = false;
            if (backtestPollInterval) clearInterval(backtestPollInterval);
        } else if (data.status === 'done') {
            elBacktestMsg.classList.add('hidden');
            elBtnRunBacktest.disabled = false;
            if (backtestPollInterval) clearInterval(backtestPollInterval);
            fetchStats();
            fetchJournal();
        }
        
        fetchStatus();
    } catch (e) {
        console.error(e);
    }
}

function pollBacktestStatus() {
    if (backtestPollInterval) clearInterval(backtestPollInterval);
    checkBacktestStatus();
    backtestPollInterval = setInterval(checkBacktestStatus, 2000);
}

// UI Updaters
function updateUI(data) {
    
    // Status
    if (data.status === 'running') {
        elStatusDot.classList.add('running');
        elStatusText.textContent = `RUNNING (${data.uptime_seconds}s)`;
        elBtnStart.disabled = true;
        elBtnStop.disabled = false;
        elStatusText.classList.add('text-cyan');
    } else {
        elStatusDot.classList.remove('running');
        elStatusText.textContent = 'OFFLINE';
        elBtnStart.disabled = false;
        elBtnStop.disabled = true;
        elStatusText.classList.remove('text-cyan');
    }
    
    // Style toggle
    if (data.style === 'daily') {
        elBtnStyleDaily.classList.add('active');
        elBtnStyleWeekly.classList.remove('active');
    } else if (data.style === 'weekly') {
        elBtnStyleWeekly.classList.add('active');
        elBtnStyleDaily.classList.remove('active');
    }
    
    let isBotRunning = (data.status === 'running');
    elBtnStyleDaily.disabled = isBotRunning || isBacktestRunning;
    elBtnStyleWeekly.disabled = isBotRunning || isBacktestRunning;

    if (data.price) elPrice.textContent = '$' + formatPrice(data.price);
    
    // AI Decision Section
    const validSignals = ['LONG', 'SHORT', 'WAIT'];
    let displaySignal = data.signal;
    if (!validSignals.includes(data.signal)) displaySignal = "WAIT";
    
    elSignalBadge.textContent = displaySignal;
    elSignalBadge.className = 'signal-huge text-dim'; // reset
    elPulseRing.className = 'pulse-ring-active';
    
    if (data.signal === 'LONG') {
        elSignalBadge.classList.add('text-green');
        elPulseRing.classList.add('long');
    }
    else if (data.signal === 'SHORT') {
        elSignalBadge.classList.add('text-red');
        elPulseRing.classList.add('short');
    }
    else {
        elPulseRing.classList.add('wait');
    }

    const conf = data.confidence || 0;
    elConfidenceValue.textContent = `${conf}%`;
    
    // Engine Feed & Matrix
    if (data.reasons && data.reasons.length > 0) {
        addFeedLine(data.reasons[0]);
        elMsCatalyst.textContent = data.reasons[0];
    }
    
    elMsBias.textContent = (data.signal === 'LONG' || data.bull_case?.length > data.bear_case?.length) ? 'Bullish' : 'Bearish';
    elMsBias.className = (elMsBias.textContent === 'Bullish') ? 'node-val text-green' : 'node-val text-red';
    
    elMsTrend.textContent = conf > 60 ? 'Strong' : 'Weak';
    elMsTrend.className = conf > 60 ? 'node-val text-cyan' : 'node-val text-dim';

    // Target Parameters Panel
    try {
        if (data.hypothetical_risk && typeof data.hypothetical_risk === 'object' && data.signal !== 'WAIT') {
            const r = data.hypothetical_risk;
            elHypoEmpty.classList.add('hidden');
            elHypoActive.classList.remove('hidden');
            
            elHypoEntry.textContent = '$' + formatPrice(data.price);
            elHypoSize.textContent = `${r.position_size_btc} BTC`;
            elHypoMargin.textContent = `${r.leverage}x ($${formatPrice(r.margin_required_usdt)})`;
            
            // Mock SL/TP
            let slPrice = 0, tpPrice = 0;
            if (data.signal === 'LONG') {
                slPrice = data.price * 0.98;
                tpPrice = data.price * 1.04; 
            } else {
                slPrice = data.price * 1.02;
                tpPrice = data.price * 0.96;
            }
            elHypoSL.textContent = '$' + formatPrice(slPrice);
            elHypoTP.textContent = '$' + formatPrice(tpPrice);
        } else {
            if (data.position) {
                elHypoEmpty.innerHTML = '<span class="text-green">Active Position Controlled</span>';
            } else {
                elHypoEmpty.innerHTML = 'Scanning market for setups...';
            }
            elHypoEmpty.classList.remove('hidden');
            elHypoActive.classList.add('hidden');
        }
    } catch (e) {
        elHypoEmpty.innerHTML = '<span class="text-red">Calculation Failure</span>';
        elHypoEmpty.classList.remove('hidden');
        elHypoActive.classList.add('hidden');
    }

    // Active Position Section
    if (data.position) {
        elTradeEmpty.classList.add('hidden');
        elTradeActive.classList.remove('hidden');
        
        elTradeSide.textContent = data.position.side;
        elTradeSide.className = data.position.side === 'BUY' ? 'font-data text-xl text-green' : 'font-data text-xl text-red';
        
        elTradeEntry.textContent = '$' + formatPrice(data.position.entry);
        elTradeSL.textContent = '$' + formatPrice(data.position.stop_loss);
        elTradeTP.textContent = '$' + formatPrice(data.position.take_profit);
        
        elTradeSize.textContent = data.hypothetical_risk?.position_size_btc + ' BTC' || '0.1500 BTC';
        elTradePnL.textContent = "Live Mkt";
    } else {
        elTradeEmpty.classList.remove('hidden');
        elTradeActive.classList.add('hidden');
    }
}

// Event Listeners
elBtnStart.addEventListener('click', () => controlBot('start'));
elBtnStop.addEventListener('click', () => controlBot('stop'));

elBtnStyleDaily.addEventListener('click', () => setStyle('daily'));
elBtnStyleWeekly.addEventListener('click', () => setStyle('weekly'));
elBtnRunBacktest.addEventListener('click', () => startBacktest());

// Initialization
document.addEventListener('DOMContentLoaded', () => {
    fetchStatus();
    fetchStats();
    fetchJournal();
    checkBacktestStatus();

    pollInterval = setInterval(() => {
        fetchStatus();
        fetchStats();
        fetchJournal();
    }, 2000);
});
