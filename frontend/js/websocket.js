/**
 * WebSocket client — conexión en tiempo real al backend
 */

const WS_URL = `ws://${window.location.host}/ws`;
let ws = null;
let wsReconnectTimer = null;

function connectWebSocket() {
  if (ws && ws.readyState === WebSocket.OPEN) return;

  ws = new WebSocket(WS_URL);

  ws.onopen = () => {
    console.log('✅ WebSocket conectado');
    setWSStatus(true);
    clearTimeout(wsReconnectTimer);
  };

  ws.onclose = () => {
    console.warn('⚠️ WebSocket desconectado, reintentando en 3s...');
    setWSStatus(false);
    wsReconnectTimer = setTimeout(connectWebSocket, 3000);
  };

  ws.onerror = (err) => {
    console.error('❌ WebSocket error:', err);
    setWSStatus(false);
  };

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      handleWSMessage(data);
    } catch (e) {
      console.error('Error parseando mensaje WS:', e);
    }
  };
}

function handleWSMessage(data) {
  switch (data.type) {
    case 'init':
    case 'live_update':
      updateIBKRStatus(data.ibkr_connected);
      if (data.account) updateAccountStats(data.account);
      if (data.positions) updatePositionsTable(data.positions);
      if (data.daily_stats) updateDailyStats(data.daily_stats);
      break;

    case 'new_signal':
      prependSignalToLog(data);
      if (data.result?.success) {
        showToast(`✅ ${data.action.toUpperCase()} ${data.symbol} ejecutado`, 'success');
      } else {
        showToast(`❌ ${data.result?.message || 'Error en señal'}`, 'error');
      }
      loadTrades();
      break;

    case 'bot_toggle':
      const toggleInput = document.getElementById('bot-toggle-input');
      const label = document.getElementById('bot-status-label');
      if (toggleInput) toggleInput.checked = data.enabled;
      if (label) label.textContent = data.enabled ? 'BOT ON' : 'BOT OFF';
      label.style.color = data.enabled ? 'var(--accent-green)' : 'var(--accent-red)';
      break;

    case 'close_all':
      showToast(data.result?.message || 'Posiciones cerradas', 'warning');
      loadTrades();
      break;
  }
}

function setWSStatus(connected) {
  const dot = document.getElementById('ws-dot');
  const txt = document.getElementById('ws-status-txt');
  if (!dot || !txt) return;
  dot.className = `status-dot status-dot--ws ${connected ? 'connected' : 'disconnected'}`;
  txt.textContent = connected ? 'WebSocket ●' : 'WebSocket ○';
}

// Arrancar cuando la página cargue
window.addEventListener('DOMContentLoaded', connectWebSocket);
