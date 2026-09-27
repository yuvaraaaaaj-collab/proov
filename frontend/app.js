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
      } else if (data.type === 'CROSS_ALERT') {
        // Notification push explicitly disabled for Session Momentum Breakout
        if (data.strategy_id === 'session_breakout' || String(data.strategy_name).toLowerCase().includes('breakout')) {
          return;
        }
        playAlarmSound();
        const stratName = data.strategy_name || data.strategy_id;
        const decision = data.evaluation?.decision || 'Trade Signal';
        triggerPushNotification(data.symbol, `${stratName}: ${decision}`, data.evaluation?.order_ticket);
        showCrossAlertToast(data);
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

// In-App Toast Banner for Background Multi-Strategy Alerts
function showCrossAlertToast(data) {
  const existing = document.getElementById('cross-alert-toast');
  if (existing) existing.remove();

  const stratName = data.strategy_name || data.strategy_id;
  const decision = data.evaluation?.decision || 'Trade Signal';
  const isBuy = String(decision).toLowerCase().includes('buy');
  const price = data.current_price;
  const ticket = data.evaluation?.order_ticket;

  const toast = document.createElement('div');
  toast.id = 'cross-alert-toast';
  toast.className = `fixed top-4 left-1/2 -translate-x-1/2 z-50 w-[92%] max-w-md p-4 rounded-xl border shadow-2xl backdrop-blur-md flex flex-col gap-2 transition-all ${
    isBuy ? 'bg-emerald-950/95 border-emerald-500/60 text-white' : 'bg-rose-950/95 border-rose-500/60 text-white'
  }`;

  toast.innerHTML = `
    <div class="flex items-center justify-between">
      <div class="flex items-center gap-2">
        <span class="text-xl">${isBuy ? '🟢' : '🔴'}</span>
        <div>
          <div class="text-xs font-black uppercase tracking-wider ${isBuy ? 'text-emerald-400' : 'text-rose-400'}">
            ⚡ ${data.symbol} • ${decision}
          </div>
          <div class="text-[11px] text-slate-300 font-semibold">${stratName}</div>
        </div>
      </div>
      <button onclick="document.getElementById('cross-alert-toast').remove()" class="text-slate-400 hover:text-white p-1 text-sm font-bold">✕</button>
    </div>
    <div class="text-xs text-slate-200 flex justify-between items-center bg-black/40 px-3 py-1.5 rounded-lg font-mono">
      <span>Price: <b>${price}</b></span>
      ${ticket ? `<span>SL: <b class="text-rose-400">${ticket['Stop Loss']}</b> | TP: <b class="text-emerald-400">${ticket['Take Profit']}</b></span>` : ''}
    </div>
    <div class="flex gap-2 mt-1">
      <button id="toast-switch-btn" class="flex-1 py-1.5 text-xs font-bold rounded-lg bg-cyan-600 hover:bg-cyan-500 text-white shadow transition-all">
        Switch to ${data.symbol} (${stratName})
      </button>
      <button onclick="document.getElementById('cross-alert-toast')?.remove()" class="px-3 py-1.5 text-xs font-semibold rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300">
        Dismiss
      </button>
    </div>
  `;

  document.body.appendChild(toast);

  const switchBtn = document.getElementById('toast-switch-btn');
  if (switchBtn) {
    switchBtn.addEventListener('click', () => {
      if (data.symbol) switchSymbol(data.symbol);
      if (data.strategy_id) {
        const select = document.getElementById('strategy-select');
        if (select) select.value = data.strategy_id;
        switchStrategy(data.strategy_id);
      }
      toast.remove();
    });
  }
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

  // 3. Session & Levels (Universal mapping for SMC, Praveen, SPEAN, Silver Bullet & Session Breakout)
  const sessionBadge = document.getElementById('session-badge');
  if (sessionBadge) {
    if (checklist['1. Kill Zone Active']) {
      const kzRaw = checklist['1. Kill Zone Active'];
      const match = kzRaw.match(/\((.*?)\)/);
      sessionBadge.textContent = match ? match[1].split(' [')[0].trim() : kzRaw;
    } else if (checklist['3. Session & Killzone']) {
      sessionBadge.textContent = checklist['3. Session & Killzone'].split(' (')[0].trim();
    } else if (checklist['3. Session Window (IST)']) {
      sessionBadge.textContent = checklist['3. Session Window (IST)'].split(' - ')[0].trim();
    } else if (checklist['Q ZONE']) {
      sessionBadge.textContent = checklist['Q ZONE'].split(' - ')[0].trim();
    } else if (checklist['Silver Bullet Window']) {
      sessionBadge.textContent = checklist['Silver Bullet Window'].split(' - ')[0].replace('Outside Window', 'Outside Window').trim();
    } else if (checklist['Session Timing']) {
      sessionBadge.textContent = checklist['Session Timing'].split('(')[0].trim();
    } else if (checklist['Breakout State']) {
      sessionBadge.textContent = checklist['Breakout State'];
    }
  }

  const lblPdh = document.getElementById('label-pdh');
  const lblPdl = document.getElementById('label-pdl');
  const pdhEl = document.getElementById('val-pdh');
  const pdlEl = document.getElementById('val-pdl');
  if (pdhEl && pdlEl) {
    if (checklist['4. 30min PD Array Tapped']) {
      if (lblPdh) lblPdh.textContent = '30M Array';
      if (lblPdl) lblPdl.textContent = 'DOL Target';
      pdhEl.textContent = checklist['4. 30min PD Array Tapped'].split(' (')[1]?.replace(')', '') || checklist['4. 30min PD Array Tapped'] || '---';
      pdlEl.textContent = checklist['3. Draw on Liquidity (DOL)']?.split(' @ ')[1]?.replace(')', '') || checklist['3. Draw on Liquidity (DOL)'] || '---';
    } else if (checklist['6. HTF PD Array']) {
      if (lblPdh) lblPdh.textContent = 'HTF PD Array';
      if (lblPdl) lblPdl.textContent = 'AMD Phase';
      pdhEl.textContent = checklist['6. HTF PD Array'] || '---';
      pdlEl.textContent = checklist['4. AMD Phase'] || '---';
    } else if (checklist['4. 30M PD Array']) {
      if (lblPdh) lblPdh.textContent = '30M Array';
      if (lblPdl) lblPdl.textContent = 'DOL Target';
      pdhEl.textContent = checklist['4. 30M PD Array'] || '---';
      pdlEl.textContent = checklist['2. Draw on Liquidity (DOL)']?.replace('Target @', '') || '---';
    } else if (checklist['15M LIQUIDITY']) {
      if (lblPdh) lblPdh.textContent = '15M BSL';
      if (lblPdl) lblPdl.textContent = '15M SSL';
      const parts = checklist['15M LIQUIDITY'].split('|');
      if (parts.length >= 2) {
        pdhEl.textContent = parts[0].replace('BSL:', '').trim();
        pdlEl.textContent = parts[1].replace('SSL:', '').trim();
      }
    } else if (checklist['1H Session Context']) {
      if (lblPdh) lblPdh.textContent = 'Day High (BSL)';
      if (lblPdl) lblPdl.textContent = 'Day Low (SSL)';
      const parts = checklist['1H Session Context'].split('|');
      if (parts.length >= 2) {
        pdhEl.textContent = parts[0].replace('Day High:', '').replace('PDH:', '').trim();
        pdlEl.textContent = parts[1].replace('Day Low:', '').replace('PDL:', '').trim();
      }
    } else if (checklist['Draw on Liquidity (DOL)']) {
      if (lblPdh) lblPdh.textContent = '15M BSL (Buy Pool)';
      if (lblPdl) lblPdl.textContent = '15M SSL (Sell Pool)';
      const parts = checklist['Draw on Liquidity (DOL)'].split('|');
      if (parts.length >= 2) {
        pdhEl.textContent = parts[0].replace('BSL:', '').trim();
        pdlEl.textContent = parts[1].replace('SSL:', '').trim();
      }
    } else if (checklist['Session Range High']) {
      if (lblPdh) lblPdh.textContent = 'Session High';
      if (lblPdl) lblPdl.textContent = 'Session Low';
      pdhEl.textContent = checklist['Session Range High'];
      pdlEl.textContent = checklist['Session Range Low'];
    }
  }

  // 4. Order Ticket Card (Persistent & Constant across updates, with auto-expiration)
  const orderCard = document.getElementById('order-card');
  let rawStoredTicket = (data.last_valid_ticket && data.last_valid_ticket.symbol === data.symbol ? data.last_valid_ticket : null) 
    || lastAlertTicket 
    || JSON.parse(localStorage.getItem('traderpro_last_ticket_' + data.symbol) || 'null');

  // If a fresh ticket just arrived from strategy evaluation
  let displayTicket = null;
  const isCurrentFresh = Boolean(ticket && (ticket['Entry Price'] || ticket['Entry']) && ticket['Stop Loss'] && ticket['Stop Loss'] !== '---');

  if (isCurrentFresh) {
    displayTicket = {
      ...ticket,
      strategy: ticket.strategy || evalData.strategy || data.strategy_name || data.strategy_id || 'Active Strategy',
      symbol: data.symbol,
      timestamp: ticket.timestamp || (Date.now() / 1000)
    };
  } else if (rawStoredTicket && rawStoredTicket.symbol === data.symbol) {
    displayTicket = rawStoredTicket;
  }

  // Validate freshness and price bounds:
  // Invalidate if older than 25 minutes, or price moved past SL/TP, or price is > 200 pts away (40 for GOLD)
  if (displayTicket) {
    let isStale = false;
    const nowSec = Date.now() / 1000;
    const ticketTime = displayTicket.timestamp || 0;
    const ageSeconds = nowSec - ticketTime;

    // If ticket has no timestamp (e.g. legacy stored ticket from prior session) or age > 25 mins (1500s)
    if (!ticketTime || ageSeconds > 1500) {
      isStale = true;
    }

    const tEntry = parseFloat(displayTicket['Entry Price'] || displayTicket['Entry'] || 0);
    const tSL = parseFloat(displayTicket['Stop Loss'] || 0);
    const tTP = parseFloat(displayTicket['Take Profit'] || 0);
    const isBuy = String(displayTicket['Order Type']).toUpperCase().includes('BUY');

    if (currentPrice > 0 && tSL > 0 && tTP > 0) {
      if (isBuy && (currentPrice <= tSL || currentPrice >= tTP)) {
        isStale = true; // Stop loss hit or target already reached
      } else if (!isBuy && (currentPrice >= tSL || currentPrice <= tTP)) {
        isStale = true; // Stop loss hit or target already reached
      }
      const maxDistance = (data.symbol === 'GOLD') ? 40.0 : 200.0;
      if (tEntry > 0 && Math.abs(currentPrice - tEntry) > maxDistance) {
        isStale = true; // Market drifted too far from the entry limit order
      }
    }

    if (isStale) {
      displayTicket = null;
      lastAlertTicket = null;
      localStorage.removeItem('traderpro_last_ticket_' + data.symbol);
    }
  }

  if (displayTicket) {
    lastAlertTicket = displayTicket;
    localStorage.setItem('traderpro_last_ticket_' + data.symbol, JSON.stringify(displayTicket));
    orderCard.classList.remove('hidden');

    const isBuy = String(displayTicket['Order Type']).includes('BUY');
    orderCard.className = `bg-slate-900 border-2 rounded-2xl p-4 shadow-2xl relative transition-all duration-300 ${
      isBuy ? 'border-emerald-500 alert-glow-green' : 'border-rose-500 alert-glow-red'
    }`;

    // Order Type Badge
    const actionBadge = document.getElementById('ticket-action-badge');
    if (actionBadge) {
      actionBadge.textContent = displayTicket['Order Type'] || (isBuy ? 'BUY LIMIT' : 'SELL LIMIT');
      actionBadge.className = `px-2.5 py-1 rounded-lg text-xs font-black tracking-wider uppercase border flex-shrink-0 ${
        isBuy ? 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30' : 'bg-rose-500/20 text-rose-400 border-rose-500/30'
      }`;
    }

    // Strategy Name Badge
    const stratNameEl = document.getElementById('ticket-strategy-name');
    if (stratNameEl) {
      const sName = displayTicket.strategy || displayTicket.Strategy || evalData.strategy || data.strategy_name || 'Active Strategy';
      stratNameEl.textContent = sName;
      stratNameEl.title = sName;
    }

    // Time / Status Badge
    const timeBadgeEl = document.getElementById('ticket-time-badge');
    if (timeBadgeEl) {
      if (isCurrentFresh) {
        timeBadgeEl.textContent = '● LIVE SIGNAL';
        timeBadgeEl.className = 'text-[10px] text-emerald-400 font-bold font-mono';
      } else {
        const ageMins = Math.max(1, Math.round((Date.now() / 1000 - (displayTicket.timestamp || Date.now() / 1000)) / 60));
        timeBadgeEl.textContent = `Active (${ageMins}m ago)`;
        timeBadgeEl.className = 'text-[10px] text-amber-400 font-mono';
      }
    }

    document.getElementById('ticket-entry').textContent = displayTicket['Entry Price'] || displayTicket['Entry'];
    document.getElementById('ticket-sl').textContent = displayTicket['Stop Loss'];
    document.getElementById('ticket-tp').textContent = displayTicket['Take Profit'];
    document.getElementById('ticket-risk').textContent = displayTicket['Risk Amount'] || '$2.50 (0.25%)';
    document.getElementById('ticket-gain').textContent = `${displayTicket['Projected Profit']} (${displayTicket['R:R']})`;
    document.getElementById('ticket-consistency').textContent = displayTicket['Consistency Impact'] || 'Safe (< 15% Cap)';
    document.getElementById('ticket-cancel').textContent = displayTicket['Cancel If'] || '---';

    // Play alarm and trigger mobile push notification ONLY when a fresh new signal is confirmed (not session breakout)
    if (data.is_alert && data.strategy_id !== 'session_breakout' && isCurrentFresh) {
      playAlarmSound();
      triggerPushNotification(data.symbol, evalData.decision, ticket);
    }
  } else {
    orderCard.classList.add('hidden');
  }

  // 5. Checklist Items
  const checklistContainer = document.getElementById('checklist-container');
  if (checklistContainer) {
    const entries = Object.entries(checklist);
    if (entries.length === 0) {
      checklistContainer.innerHTML = `
        <div class="py-3 text-center text-slate-500 text-xs italic">
          Scanning market data... Click <b>Refresh</b> to force update.
        </div>
      `;
    } else {
      let checklistHtml = '';
      for (const [key, val] of entries) {
        const valStr = String(val);
        const isPositive = valStr.startsWith('YES') || valStr.startsWith('BUY') || valStr.includes('Confirmed') || valStr.includes('ACTIVE') || valStr.includes('BREAKOUT');
        const isWaiting = valStr.startsWith('WAIT') || valStr === 'NO' || valStr === 'NONE' || valStr.startsWith('Outside') || valStr.includes('INSIDE');
        
        checklistHtml += `
          <div class="flex justify-between items-center py-1.5 border-b border-slate-800/60 last:border-none">
            <span class="text-slate-400 font-medium">${key}</span>
            <span class="font-medium font-mono text-[11px] ${
              isPositive ? 'text-emerald-400 font-bold' : isWaiting ? 'text-slate-400' : 'text-cyan-400'
            }">${val}</span>
          </div>
        `;
      }
      checklistContainer.innerHTML = checklistHtml;
    }
  }

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

// Dismiss active ticket manually
function dismissTicket() {
  lastAlertTicket = null;
  localStorage.removeItem('traderpro_last_ticket_' + currentSymbol);
  
  // Also instruct backend to clear server-side memory
  fetch('/api/alerts/dismiss', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ symbol: currentSymbol })
  }).catch(() => {});

  const orderCard = document.getElementById('order-card');
  if (orderCard) {
    orderCard.classList.add('hidden');
  }
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
  lastAlertTicket = JSON.parse(localStorage.getItem('traderpro_last_ticket_' + symbol) || 'null');
  const btnNas = document.getElementById('btn-nas100');
  const btnGold = document.getElementById('btn-gold');
  const cardSymbol = document.getElementById('card-symbol');
  const tvLink = document.getElementById('tv-open-link');

  if (symbol === 'NAS100') {
    btnNas.className = 'flex-1 py-1.5 text-xs font-semibold rounded-lg bg-cyan-600 text-white shadow transition-all';
    btnGold.className = 'flex-1 py-1.5 text-xs font-semibold rounded-lg text-slate-400 hover:text-white transition-all';
    cardSymbol.textContent = 'NAS100 (Capital.com)';
    if (tvLink) tvLink.href = 'https://www.tradingview.com/chart/?symbol=CAPITALCOM%3AUS100';
  } else {
    btnGold.className = 'flex-1 py-1.5 text-xs font-semibold rounded-lg bg-cyan-600 text-white shadow transition-all';
    btnNas.className = 'flex-1 py-1.5 text-xs font-semibold rounded-lg text-slate-400 hover:text-white transition-all';
    cardSymbol.textContent = 'GOLD (Capital.com)';
    if (tvLink) tvLink.href = 'https://www.tradingview.com/chart/?symbol=CAPITALCOM%3AGOLD';
  }

  loadTradingViewWidget(symbol);
  loadSingleQuoteWidget(symbol);

  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ switch_symbol: symbol }));
  }
  refreshStrategy();
}

// Strategy Switcher
async function switchStrategy(strategyId) {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ switch_strategy: strategyId }));
  }
  try {
    await fetch('/api/strategies/select', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ strategy_id: strategyId })
    });
  } catch (e) {
    console.error('Error selecting strategy:', e);
  }
  refreshStrategy();
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

    // 2. Fetch directly via REST for immediate re-evaluation and instant checklist render
    const res = await fetch(`/api/refresh?symbol=${encodeURIComponent(currentSymbol)}&strategy_id=${encodeURIComponent(stratId)}&t=${Date.now()}`);
    if (res.ok) {
      const data = await res.json();
      if (data && (data.type === 'MARKET_UPDATE' || data.evaluation)) {
        renderMarketUpdate(data);
      }
    }
  } catch (err) {
    console.error('Strategy refresh error:', err);
  } finally {
    setTimeout(() => {
      if (icon) icon.classList.remove('fa-spin');
      if (btn) btn.disabled = false;
    }, 600);
  }
}

// -------------------------------------------------------------
// VIP Access Passcode Security (For User & Friends Only)
// -------------------------------------------------------------
function checkVipAuth() {
  const isAuth = localStorage.getItem('traderpro_vip_auth');
  const overlay = document.getElementById('vip-gate-overlay');
  if (isAuth === '1') {
    if (overlay) overlay.classList.add('hidden');
  } else {
    if (overlay) overlay.classList.remove('hidden');
    const input = document.getElementById('vip-pin-input');
    if (input) input.focus();
  }
}

async function submitVipPin() {
  const pinInput = document.getElementById('vip-pin-input');
  const errEl = document.getElementById('vip-pin-error');
  const pin = pinInput?.value || '';
  
  if (!pin) return;
  
  try {
    const res = await fetch('/api/auth/verify', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ pin: pin })
    });
    const data = await res.json();
    if (data.valid) {
      localStorage.setItem('traderpro_vip_auth', '1');
      const overlay = document.getElementById('vip-gate-overlay');
      if (overlay) overlay.classList.add('hidden');
      if (errEl) errEl.classList.add('hidden');
    } else {
      if (errEl) errEl.classList.remove('hidden');
      if (pinInput) {
        pinInput.value = '';
        pinInput.focus();
      }
    }
  } catch (e) {
    console.error('PIN verification error:', e);
  }
}

// -------------------------------------------------------------
// Mobile Push Notifications
// -------------------------------------------------------------
function triggerPushNotification(symbol, decision, ticket) {
  if (!('Notification' in window)) return;
  // Strictly prevent empty notifications without valid Stop Loss and Take Profit
  if (!ticket || !ticket['Stop Loss'] || ticket['Stop Loss'] === '---' || !ticket['Take Profit'] || ticket['Take Profit'] === '---') {
    console.warn('Skipping push notification: ticket has no valid SL/TP values', ticket);
    return;
  }

  if (Notification.permission === 'granted') {
    const isBuy = String(decision).toLowerCase().includes('buy');
    const title = `🚨 TRADERPRO VIP: ${decision.toUpperCase()} on ${symbol}`;
    const entry = ticket['Entry Price'] || ticket['Entry'] || 'Market';
    const sl = ticket['Stop Loss'];
    const tp = ticket['Take Profit'];
    const rr = ticket['R:R'] || '1:2+';
    const risk = ticket['Risk Amount'] || '$2.50 (Goat Safe)';
    const gain = ticket['Projected Profit'] || '---';
    const body = `🎯 Entry: ${entry} | 🛑 SL: ${sl} | 💰 TP: ${tp} (R:R ${rr}) | 🛡️ Risk: ${risk} | 💵 Target: ${gain}`;
    
    const notifOptions = {
      body: body,
      icon: '/manifest.json',
      badge: '/manifest.json',
      vibrate: [300, 150, 300, 150, 600],
      tag: `traderpro-vip-${symbol}`,
      renotify: true,
      requireInteraction: true // Stays pinned in notification drawer / on screen until dismissed
    };

    if (navigator.serviceWorker && navigator.serviceWorker.controller) {
      navigator.serviceWorker.ready.then(reg => {
        reg.showNotification(title, notifOptions);
      });
    } else {
      try {
        new Notification(title, notifOptions);
      } catch (_) {
        new Notification(title, { body: body });
      }
    }
  }
}

async function requestNotificationAccess() {
  if (!('Notification' in window)) {
    alert('Notifications are not supported on this browser.');
    return;
  }
  const perm = await Notification.requestPermission();
  const btn = document.getElementById('enable-push-btn');
  if (perm === 'granted') {
    if (btn) {
      btn.textContent = 'Active ✅';
      btn.className = 'px-2.5 py-1 text-[11px] font-bold rounded-lg bg-emerald-600 text-white';
    }
    // Test notification immediately with accurate symbol values
    const isGold = currentSymbol === 'GOLD';
    const sampleTicket = isGold ? {
      'Order Type': 'BUY LIMIT (TEST)',
      'Entry Price': '4306.50',
      'Stop Loss': '4298.00',
      'Take Profit': '4322.00',
      'R:R': '1:2.2',
      'Risk Amount': '$2.50 (Goat Safe)',
      'Projected Profit': '+$5.50'
    } : {
      'Order Type': 'BUY LIMIT (TEST)',
      'Entry Price': '30650.0',
      'Stop Loss': '30620.0',
      'Take Profit': '30720.0',
      'R:R': '1:2.3',
      'Risk Amount': '$2.50 (Goat Safe)',
      'Projected Profit': '+$5.75'
    };
    triggerPushNotification(currentSymbol, 'TEST ENTRY ALERT (ACTIVE)', sampleTicket);
  } else {
    if (btn) btn.textContent = 'Blocked ❌';
  }
}

// -------------------------------------------------------------
// Alerts & Notification Dispatcher Modal
// -------------------------------------------------------------
async function openAlertsModal() {
  const modal = document.getElementById('alerts-modal');
  if (modal) modal.classList.remove('hidden');
  
  const pushBtn = document.getElementById('enable-push-btn');
  if (pushBtn && 'Notification' in window && Notification.permission === 'granted') {
    pushBtn.textContent = 'Active ✅';
    pushBtn.className = 'px-2.5 py-1 text-[11px] font-bold rounded-lg bg-emerald-600 text-white';
  }

  try {
    const res = await fetch('/api/alerts/settings');
    if (res.ok) {
      const cfg = await res.json();
      document.getElementById('cfg-tg-enabled').checked = !!cfg.telegram_enabled;
      document.getElementById('cfg-tg-token').value = cfg.telegram_bot_token || '';
      document.getElementById('cfg-tg-chats').value = (cfg.telegram_chat_ids || []).join(', ');
      
      document.getElementById('cfg-wa-enabled').checked = !!cfg.whatsapp_enabled;
      document.getElementById('cfg-wa-apikey').value = cfg.whatsapp_apikey || '';
      document.getElementById('cfg-wa-phones').value = (cfg.whatsapp_phones || []).join(', ');
      
      document.getElementById('cfg-vip-pin').value = cfg.vip_pin || '7788';
    }
  } catch (e) {
    console.error('Error loading alert settings:', e);
  }
}

function closeAlertsModal() {
  const modal = document.getElementById('alerts-modal');
  if (modal) modal.classList.add('hidden');
}

async function saveNotificationSettings() {
  const statusEl = document.getElementById('alert-settings-status');
  const tgChats = document.getElementById('cfg-tg-chats').value.split(',').map(s => s.trim()).filter(Boolean);
  const waPhones = document.getElementById('cfg-wa-phones').value.split(',').map(s => s.trim()).filter(Boolean);
  
  const payload = {
    telegram_enabled: document.getElementById('cfg-tg-enabled').checked,
    telegram_bot_token: document.getElementById('cfg-tg-token').value.trim(),
    telegram_chat_ids: tgChats,
    whatsapp_enabled: document.getElementById('cfg-wa-enabled').checked,
    whatsapp_apikey: document.getElementById('cfg-wa-apikey').value.trim(),
    whatsapp_phones: waPhones,
    vip_pin: document.getElementById('cfg-vip-pin').value.trim() || '7788'
  };

  try {
    const res = await fetch('/api/alerts/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    if (res.ok) {
      if (statusEl) {
        statusEl.className = 'text-xs text-center font-bold text-emerald-400';
        statusEl.textContent = 'Settings Saved Successfully!';
        statusEl.classList.remove('hidden');
        setTimeout(() => statusEl.classList.add('hidden'), 3000);
      }
    }
  } catch (e) {
    if (statusEl) {
      statusEl.className = 'text-xs text-center font-bold text-rose-400';
      statusEl.textContent = 'Failed to save settings.';
      statusEl.classList.remove('hidden');
    }
  }
}

async function testNotificationAlert() {
  const statusEl = document.getElementById('alert-settings-status');
  if (statusEl) {
    statusEl.className = 'text-xs text-center font-bold text-cyan-400';
    statusEl.textContent = `Sending Test Alert for ${currentSymbol} to Phone & Telegram...`;
    statusEl.classList.remove('hidden');
  }

  const isGold = currentSymbol === 'GOLD';
  const sampleTicket = isGold ? {
    'Order Type': 'BUY LIMIT (TEST)',
    'Entry Price': '4306.50',
    'Stop Loss': '4298.00',
    'Take Profit': '4322.00',
    'R:R': '1:2.2',
    'Risk Amount': '$2.50 (Goat Safe)',
    'Projected Profit': '+$5.50'
  } : {
    'Order Type': 'BUY LIMIT (TEST)',
    'Entry Price': '30650.0',
    'Stop Loss': '30620.0',
    'Take Profit': '30720.0',
    'R:R': '1:2.3',
    'Risk Amount': '$2.50 (Goat Safe)',
    'Projected Profit': '+$5.75'
  };

  // Trigger local alarm and browser push
  playAlarmSound();
  triggerPushNotification(currentSymbol, 'BUY LIMIT (TEST)', sampleTicket);

  try {
    const res = await fetch('/api/alerts/test', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ symbol: currentSymbol })
    });
    const data = await res.json();
    if (statusEl) {
      statusEl.className = 'text-xs text-center font-bold text-emerald-400';
      statusEl.textContent = `Test Alert Dispatched for ${data.symbol || currentSymbol}! Check your Phone & Telegram.`;
      setTimeout(() => statusEl.classList.add('hidden'), 4000);
    }
  } catch (e) {
    if (statusEl) {
      statusEl.className = 'text-xs text-center font-bold text-rose-400';
      statusEl.textContent = 'Error sending test alert.';
    }
  }
}

// Initialize on Load
window.addEventListener('DOMContentLoaded', () => {
  // 0. Check VIP Authentication
  checkVipAuth();
  const pinInput = document.getElementById('vip-pin-input');
  if (pinInput) {
    pinInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') submitVipPin();
    });
  }

  // 1. Fetch current status immediately so checklist renders on the very first frame
  fetch('/api/status?t=' + Date.now())
    .then(res => res.json())
    .then(data => {
      if (data && (data.type === 'MARKET_UPDATE' || data.evaluation)) {
        renderMarketUpdate(data);
      }
    })
    .catch(err => console.log('Initial status fetch error:', err));

  // 2. Connect WebSocket
  connectWebSocket();

  // 3. Mount TradingView chart widget and Single Quote ticker box
  setTimeout(() => {
    loadTradingViewWidget('NAS100');
    loadSingleQuoteWidget('NAS100');
  }, 200);
});
