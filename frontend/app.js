let ws = null;
let currentSymbol = 'NAS100';
let audioEnabled = true;
let deferredPrompt = null;
let lastAlertTicket = null;

// PWA Installation handling
window.addEventListener('beforeinstallprompt', (e) => {
  e.preventDefault();
  deferredPrompt = e;
  const installBtn = document.getElementById('install-btn');
  if (installBtn) {
    installBtn.classList.remove('hidden');
    installBtn.addEventListener('click', async () => {
      if (deferredPrompt) {
        deferredPrompt.prompt();
        const { outcome } = await deferredPrompt.userChoice;
        if (outcome === 'accepted') {
          installBtn.classList.add('hidden');
        }
        deferredPrompt = null;
      }
    });
  }
});

// Register Service Worker
if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/sw.js').catch((err) => console.log('SW registration failed', err));
}

// Web Audio API Sound Synthesizer (Zero external audio file dependency)
function playAlarmSound() {
  if (!audioEnabled) return;
  try {
    const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    
    // Play two-tone alert chime
    const playTone = (freq, startTime, duration) => {
      const osc = audioCtx.createOscillator();
      const gain = audioCtx.createGain();
      osc.type = 'triangle';
      osc.frequency.setValueAtTime(freq, startTime);
      gain.gain.setValueAtTime(0.3, startTime);
      gain.gain.exponentialRampToValueAtTime(0.001, startTime + duration);
      osc.connect(gain);
      gain.connect(audioCtx.destination);
      osc.start(startTime);
      osc.stop(startTime + duration);
    };

    const now = audioCtx.currentTime;
    playTone(880, now, 0.2);        // A5
    playTone(1174.66, now + 0.22, 0.4); // D6
    playTone(1760, now + 0.45, 0.6);   // A6

    // Vibrate phone if supported
    if ('vibrate' in navigator) {
      navigator.vibrate([200, 100, 200, 100, 500]);
    }
  } catch (e) {
    console.log('Audio playback error', e);
  }
}

// Sound toggle button
document.getElementById('sound-btn').addEventListener('click', () => {
  audioEnabled = !audioEnabled;
  const icon = document.getElementById('sound-icon');
  if (audioEnabled) {
    icon.className = 'fa-solid fa-volume-high text-emerald-400';
    playAlarmSound(); // Test sound
  } else {
    icon.className = 'fa-solid fa-volume-xmark text-slate-500';
  }
});

// WebSocket Connection
function connectWebSocket() {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = `${protocol}//${window.location.host}/ws`;

  ws = new WebSocket(wsUrl);

  const connDot = document.getElementById('conn-dot');
  const connText = document.getElementById('conn-text');

  ws.onopen = () => {
    connDot.className = 'w-2 h-2 rounded-full bg-emerald-500';
    connText.textContent = 'ONLINE';
    connText.className = 'text-[10px] text-emerald-400 font-bold';
  };

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      if (data.type === 'MARKET_UPDATE') {
        renderMarketUpdate(data);
      }
    } catch (e) {
      console.error(e);
    }
  };

  ws.onclose = () => {
    connDot.className = 'w-2 h-2 rounded-full bg-rose-500 animate-ping';
    connText.textContent = 'RECONNECTING';
    connText.className = 'text-[10px] text-rose-400 font-bold';
    setTimeout(connectWebSocket, 2000);
  };
}

// Render incoming market updates
function renderMarketUpdate(data) {
  const evalData = data.evaluation || {};
  const currentPrice = data.current_price;
  const decision = evalData.decision || 'Wait / No trade';
  const checklist = evalData.checklist || {};
  const ticket = evalData.order_ticket;

  // 1. Live Price (if static element exists)
  const priceEl = document.getElementById('live-price');
  if (priceEl && currentPrice) {
    priceEl.textContent = currentPrice.toFixed(currentSymbol === 'GOLD' ? 2 : 1);
  }

  // 2. Decision Badge
  const decBadge = document.getElementById('decision-badge');
  if (decision.toLowerCase().includes('wait') || decision.toLowerCase().includes('no trade')) {
    decBadge.className = 'mt-1 px-3 py-1 rounded-full text-xs font-bold tracking-wide uppercase bg-slate-800 text-slate-300 border border-slate-700 inline-block';
    decBadge.textContent = 'WAIT / NO TRADE';
  } else if (decision.toLowerCase().includes('buy')) {
    decBadge.className = 'mt-1 px-3 py-1 rounded-full text-xs font-bold tracking-wide uppercase bg-emerald-950 text-emerald-400 border border-emerald-500 alert-glow-green inline-block';
    decBadge.textContent = decision;
  } else if (decision.toLowerCase().includes('sell')) {
    decBadge.className = 'mt-1 px-3 py-1 rounded-full text-xs font-bold tracking-wide uppercase bg-rose-950 text-rose-400 border border-rose-500 alert-glow-red inline-block';
    decBadge.textContent = decision;
  }

  // 3. Session & Levels
  if (checklist['Session Timing']) {
    document.getElementById('session-badge').textContent = checklist['Session Timing'].split('(')[0].trim();
  }
  if (checklist['1H Session Context']) {
    const parts = checklist['1H Session Context'].split('|');
    if (parts.length >= 2) {
      document.getElementById('val-pdh').textContent = parts[0].replace('PDH:', '').trim();
      document.getElementById('val-pdl').textContent = parts[1].replace('PDL:', '').trim();
    }
  }

  // 4. Order Ticket Card
  const orderCard = document.getElementById('order-card');
  if (ticket) {
    lastAlertTicket = ticket;
    orderCard.classList.remove('hidden');
    const isBuy = ticket['Order Type'].includes('BUY');
    orderCard.className = `bg-slate-900 border-2 rounded-2xl p-4 shadow-2xl relative transition-all duration-300 ${
      isBuy ? 'border-emerald-500 alert-glow-green' : 'border-rose-500 alert-glow-red'
    }`;

    const actionBadge = document.getElementById('ticket-action-badge');
    actionBadge.textContent = ticket['Order Type'];
    actionBadge.className = `px-2.5 py-1 rounded-lg text-xs font-black tracking-wider uppercase border ${
      isBuy ? 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30' : 'bg-rose-500/20 text-rose-400 border-rose-500/30'
    }`;

    document.getElementById('ticket-entry').textContent = ticket['Entry Price'] || ticket['Entry'];
    document.getElementById('ticket-sl').textContent = ticket['Stop Loss'];
    document.getElementById('ticket-tp').textContent = ticket['Take Profit'];
    document.getElementById('ticket-risk').textContent = ticket['Risk Amount'] || '$2.50 (0.25%)';
    document.getElementById('ticket-gain').textContent = `${ticket['Projected Profit']} (${ticket['R:R']})`;
    document.getElementById('ticket-consistency').textContent = ticket['Consistency Impact'] || 'Safe (< 15% Cap)';
    document.getElementById('ticket-cancel').textContent = ticket['Cancel If'] || '---';

    // Play alarm if new alert
    if (data.is_alert) {
      playAlarmSound();
    }
  } else {
    orderCard.classList.add('hidden');
  }

  // 5. Checklist Items
  const checklistContainer = document.getElementById('checklist-container');
  let checklistHtml = '';
  for (const [key, val] of Object.entries(checklist)) {
    const isPositive = String(val).startsWith('YES') || String(val).startsWith('BUY') || String(val).includes('Confirmed');
    const isWaiting = String(val).startsWith('WAIT') || String(val) === 'NO' || String(val) === 'NONE';
    
    checklistHtml += `
      <div class="flex justify-between items-center py-1.5 border-b border-slate-800/60 last:border-none">
        <span class="text-slate-400">${key}</span>
        <span class="font-medium font-mono text-[11px] ${
          isPositive ? 'text-emerald-400' : isWaiting ? 'text-slate-400' : 'text-cyan-400'
        }">${val}</span>
      </div>
    `;
  }
  checklistContainer.innerHTML = checklistHtml;

  const strategyNameBadge = document.getElementById('strategy-name-badge');
  if (strategyNameBadge && evalData.strategy) {
    strategyNameBadge.textContent = evalData.strategy;
  }
}

// Copy Ticket for Phone Entry
function copyTicket() {
  if (!lastAlertTicket) return;
  const text = `
🎯 TRADERPRO ORDER TICKET
---------------------------
Order: ${lastAlertTicket['Order Type']}
Instrument: ${lastAlertTicket['Instrument']}
Entry: ${lastAlertTicket['Entry Price'] || lastAlertTicket['Entry']}
Stop Loss: ${lastAlertTicket['Stop Loss']}
Take Profit: ${lastAlertTicket['Take Profit']}
Risk: ${lastAlertTicket['Risk Amount']}
Target: ${lastAlertTicket['Projected Profit']}
Cancel If: ${lastAlertTicket['Cancel If']}
---------------------------
  `.trim();

  navigator.clipboard.writeText(text).then(() => {
    alert('Order ticket copied to clipboard! You can paste it into notes or MT5 on your phone.');
  });
}

// Load Embedded TradingView Live Chart Widget (Direct Capital.com Stream)
function loadTradingViewWidget(symbol) {
  const container = document.getElementById('tradingview_chart_container');
  if (!container) return;
  container.innerHTML = '';
  
  const tvSymbol = (symbol === 'GOLD') ? 'CAPITALCOM:GOLD' : 'CAPITALCOM:US100';
  const titleEl = document.getElementById('chart-broker-title');
  if (titleEl) {
    titleEl.textContent = (symbol === 'GOLD') ? 'Capital.com Gold Live Chart (1M)' : 'Capital.com US 100 Live Chart (1M)';
  }

  if (typeof TradingView !== 'undefined') {
    new TradingView.widget({
      "autosize": true,
      "symbol": tvSymbol,
      "interval": "1",
      "timezone": "Etc/UTC",
      "theme": "dark",
      "style": "1",
      "locale": "en",
      "toolbar_bg": "#0f172a",
      "enable_publishing": false,
      "hide_top_toolbar": false,
      "hide_legend": false,
      "save_image": false,
      "container_id": "tradingview_chart_container"
    });
  }
}

// Load Embedded TradingView Single Quote Ticker Widget (Direct Capital.com Real-Time Stream)
function loadSingleQuoteWidget(symbol) {
  const container = document.getElementById('tradingview-quote-box');
  if (!container) return;
  container.innerHTML = '';

  const tvSymbol = (symbol === 'GOLD') ? 'CAPITALCOM:GOLD' : 'CAPITALCOM:US100';

  const widgetWrapper = document.createElement('div');
  widgetWrapper.className = 'tradingview-widget-container';
  
  const widgetDiv = document.createElement('div');
  widgetDiv.className = 'tradingview-widget-container__widget';
  widgetWrapper.appendChild(widgetDiv);

  const script = document.createElement('script');
  script.type = 'text/javascript';
  script.src = 'https://s3.tradingview.com/external-embedding/embed-widget-single-quote.js';
  script.async = true;
  script.innerHTML = JSON.stringify({
    "symbol": tvSymbol,
    "width": "100%",
    "colorTheme": "dark",
    "isTransparent": true,
    "locale": "en"
  });

  widgetWrapper.appendChild(script);
  container.appendChild(widgetWrapper);
}

// Asset Switcher
function switchSymbol(symbol) {
  currentSymbol = symbol;
  const btnNas = document.getElementById('btn-nas100');
  const btnGold = document.getElementById('btn-gold');
  const cardSymbol = document.getElementById('card-symbol');

  if (symbol === 'NAS100') {
    btnNas.className = 'flex-1 py-1.5 text-xs font-semibold rounded-lg bg-cyan-600 text-white shadow transition-all';
    btnGold.className = 'flex-1 py-1.5 text-xs font-semibold rounded-lg text-slate-400 hover:text-white transition-all';
    cardSymbol.textContent = 'NAS100 (Capital.com)';
  } else {
    btnGold.className = 'flex-1 py-1.5 text-xs font-semibold rounded-lg bg-cyan-600 text-white shadow transition-all';
    btnNas.className = 'flex-1 py-1.5 text-xs font-semibold rounded-lg text-slate-400 hover:text-white transition-all';
    cardSymbol.textContent = 'GOLD (Capital.com)';
  }

  loadTradingViewWidget(symbol);
  loadSingleQuoteWidget(symbol);

  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ switch_symbol: symbol }));
  }
}

// Strategy Switcher
function switchStrategy(strategyId) {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ switch_strategy: strategyId }));
  }
}

// Manual Strategy Refresh button handler
async function refreshStrategy() {
  const icon = document.getElementById('refresh-icon');
  const btn = document.getElementById('refresh-strategy-btn');
  if (icon) icon.classList.add('fa-spin');
  if (btn) btn.disabled = true;

  try {
    const stratId = document.getElementById('strategy-select')?.value || '';

    // 1. Send immediate request via WebSocket if open
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ 
        refresh: true, 
        symbol: currentSymbol,
        strategy_id: stratId 
      }));
    }

    // 2. Also fetch directly via REST for immediate re-evaluation and checklist render
    const res = await fetch(`/api/refresh?symbol=${encodeURIComponent(currentSymbol)}&strategy_id=${encodeURIComponent(stratId)}&t=${Date.now()}`);
    if (res.ok) {
      const data = await res.json();
      if (data && data.type === 'MARKET_UPDATE') {
        renderMarketUpdate(data);
      }
    }
  } catch (err) {
    console.error('Strategy refresh error:', err);
  } finally {
    setTimeout(() => {
      if (icon) icon.classList.remove('fa-spin');
      if (btn) btn.disabled = false;
    }, 700);
  }
}

// Initialize on Load
window.addEventListener('DOMContentLoaded', () => {
  connectWebSocket();
  setTimeout(() => {
    loadTradingViewWidget('NAS100');
    loadSingleQuoteWidget('NAS100');
  }, 300);
});
