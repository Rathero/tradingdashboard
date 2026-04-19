/**
 * app.js — Lógica principal del dashboard
 * Actualiza la UI, carga datos del backend, gestiona acciones del usuario
 */

const API = '';   // Relativo al mismo origen

// ─── Estado IBKR ─────────────────────────────────────────────────────────────

function updateIBKRStatus(connected) {
  const dot = document.getElementById('ibkr-dot');
  const txt = document.getElementById('ibkr-status-txt');
  if (!dot || !txt) return;
  dot.className = `status-dot ${connected ? 'connected' : 'disconnected'}`;
  txt.textContent = connected
    ? 'IBKR Conectado'
    : 'IBKR Desconectado';
}

// ─── Cuenta ───────────────────────────────────────────────────────────────────

function updateAccountStats(account) {
  const balance = account.net_liquidation || 0;
  const buyingPower = account.buying_power || 0;
  const unrealized = account.unrealized_pnl || 0;
  const realized = account.realized_pnl || 0;

  setElement('stat-balance', formatCurrency(balance));
  setElement('stat-buying-power', `Buying Power: ${formatCurrency(buyingPower)}`);
  setElement('stat-unrealized', `No realizado: ${formatCurrency(unrealized, true)}`);

  const dailyPnlEl = document.getElementById('stat-daily-pnl');
  if (dailyPnlEl) {
    dailyPnlEl.textContent = formatCurrency(realized, true);
    dailyPnlEl.className = `stat-value ${realized >= 0 ? 'positive' : 'negative'}`;
  }

  // Actualizar risk bar
  updateRiskBar(realized < 0 ? Math.abs(realized) : 0, balance);
}

// ─── Stats Diarios ────────────────────────────────────────────────────────────

function updateDailyStats(stats) {
  setElement('stat-winrate', `${stats.win_rate || 0}%`);
  setElement('stat-trades-today', `${stats.daily_trades || 0} trades hoy`);

  const botToggle = document.getElementById('bot-toggle-input');
  const botLabel  = document.getElementById('bot-status-label');
  if (botToggle) botToggle.checked = stats.bot_enabled;
  if (botLabel) {
    botLabel.textContent = stats.bot_enabled ? 'BOT ON' : 'BOT OFF';
    botLabel.style.color = stats.bot_enabled ? 'var(--accent-green)' : 'var(--accent-red)';
  }
}

// ─── Posiciones ───────────────────────────────────────────────────────────────

function updatePositionsTable(positions) {
  const tbody = document.getElementById('positions-body');
  const countEl = document.getElementById('stat-positions');
  if (!tbody) return;

  if (countEl) countEl.textContent = positions.length;

  if (!positions.length) {
    tbody.innerHTML = '<tr><td colspan="8" class="empty-row">No hay posiciones abiertas</td></tr>';
    return;
  }

  tbody.innerHTML = positions.map(pos => {
    const pnlClass = pos.unrealized_pnl >= 0 ? 'pnl-positive' : 'pnl-negative';
    const pnlPctClass = pos.pnl_pct >= 0 ? 'pnl-positive' : 'pnl-negative';
    return `
      <tr>
        <td class="symbol-cell">${escapeHtml(pos.symbol)}</td>
        <td class="${pos.side === 'LONG' ? 'side-long' : 'side-short'}">${pos.side}</td>
        <td class="price-cell">${pos.qty}</td>
        <td class="price-cell">${formatCurrency(pos.avg_cost)}</td>
        <td class="price-cell">${pos.market_price > 0 ? formatCurrency(pos.market_price) : '—'}</td>
        <td class="${pnlClass}">${formatCurrency(pos.unrealized_pnl, true)}</td>
        <td class="${pnlPctClass}">${pos.pnl_pct >= 0 ? '+' : ''}${pos.pnl_pct}%</td>
        <td>
          <button class="btn btn-sm btn-danger" onclick="closePosition('${escapeHtml(pos.symbol)}')">
            <i class="fas fa-times"></i> Cerrar
          </button>
        </td>
      </tr>`;
  }).join('');
}

async function refreshPositions() {
  try {
    const positions = await apiFetch('/positions');
    updatePositionsTable(positions);
  } catch (e) {
    showToast('Error actualizando posiciones', 'error');
  }
}

// ─── Trades ───────────────────────────────────────────────────────────────────

async function loadTrades() {
  const filter = document.getElementById('trades-filter')?.value || '';
  const url = `/trades?limit=50${filter ? '&status=' + filter : ''}`;
  try {
    const trades = await apiFetch(url);
    const tbody = document.getElementById('trades-body');
    if (!tbody) return;

    if (!trades.length) {
      tbody.innerHTML = '<tr><td colspan="8" class="empty-row">Sin trades en el historial</td></tr>';
      return;
    }

    tbody.innerHTML = trades.map(t => {
      const pnl = t.realized_pnl;
      const pnlText = pnl != null ? formatCurrency(pnl, true) : '—';
      const pnlClass = pnl != null ? (pnl >= 0 ? 'pnl-positive' : 'pnl-negative') : '';
      return `
        <tr>
          <td>${formatDate(t.opened_at)}</td>
          <td class="symbol-cell">${escapeHtml(t.symbol)}</td>
          <td class="${t.side === 'BUY' ? 'side-long' : 'side-short'}">${t.side}</td>
          <td class="price-cell">${t.qty}</td>
          <td class="price-cell">${t.entry_price ? formatCurrency(t.entry_price) : '—'}</td>
          <td class="price-cell">${t.exit_price ? formatCurrency(t.exit_price) : '—'}</td>
          <td class="${pnlClass}">${pnlText}</td>
          <td><span class="status-badge status-${t.status}">${t.status}</span></td>
        </tr>`;
    }).join('');
  } catch (e) {
    console.error('Error cargando trades:', e);
  }
}

async function syncTradesFromIBKR() {
  showToast('🔄 Sincronizando posiciones de IBKR...', '');
  try {
    const res = await apiFetch('/trades/sync', 'POST');
    if (res?.success) {
      const msg = res.imported > 0
        ? `✅ ${res.imported} posición(es) importada(s) desde IBKR`
        : 'ℹ️ Ya estaba todo sincronizado';
      showToast(msg, res.imported > 0 ? 'success' : '');
      await loadTrades();
    }
  } catch (e) {
    showToast(`❌ ${e.message || 'Error al sincronizar'}`, 'error');
  }
}

// ─── Señales ──────────────────────────────────────────────────────────────────

async function loadSignals() {
  try {
    const signals = await apiFetch('/signals?limit=20');
    const container = document.getElementById('signals-body');
    if (!container) return;

    if (!signals.length) {
      container.innerHTML = '<p class="empty-row">Esperando señales de TradingView...</p>';
      return;
    }
    container.innerHTML = signals.map(buildSignalHTML).join('');
  } catch (e) {
    console.error('Error cargando señales:', e);
  }
}

function prependSignalToLog(data) {
  const container = document.getElementById('signals-body');
  if (!container) return;

  const emptyMsg = container.querySelector('.empty-row');
  if (emptyMsg) emptyMsg.remove();

  const signal = {
    action: data.action,
    symbol: data.symbol,
    status: data.result?.success ? 'executed' : 'failed',
    error_msg: data.result?.message,
    received_at: data.timestamp,
  };

  container.insertAdjacentHTML('afterbegin', buildSignalHTML(signal));

  // Limitar a 20 items
  const items = container.querySelectorAll('.signal-item');
  if (items.length > 20) items[items.length - 1].remove();
}

function buildSignalHTML(signal) {
  const action = signal.action || '';
  const iconClass = action === 'buy' ? 'signal-buy fa-arrow-up'
    : action === 'sell' ? 'signal-sell fa-arrow-down'
    : 'signal-close fa-times';

  const actionLabel = action === 'buy' ? 'BUY'
    : action === 'sell' ? 'SELL'
    : action.toUpperCase();

  const statusBadge = `<span class="status-badge status-${signal.status}">${signal.status}</span>`;
  const msg = signal.error_msg ? `<p class="signal-msg">${escapeHtml(signal.error_msg)}</p>` : '';

  return `
    <div class="signal-item">
      <div class="signal-icon ${action === 'buy' ? 'signal-buy' : action === 'sell' ? 'signal-sell' : 'signal-close'}">
        <i class="fas fa-${action === 'buy' ? 'arrow-up' : action === 'sell' ? 'arrow-down' : 'times'}"></i>
      </div>
      <div class="signal-content">
        <div class="signal-title">
          <span>${actionLabel}</span>
          <span class="signal-symbol">${escapeHtml(signal.symbol || '')}</span>
          ${statusBadge}
        </div>
        <p class="signal-time">${formatDate(signal.received_at)}</p>
        ${msg}
      </div>
    </div>`;
}

// ─── Risk Config ──────────────────────────────────────────────────────────────

async function loadRiskConfig() {
  try {
    const cfg = await apiFetch('/config/risk');
    if (!cfg) return;
    setInputValue('risk-per-trade', cfg.risk_per_trade_pct);
    setInputValue('max-daily-loss', cfg.max_daily_loss_pct);
    setInputValue('max-positions', cfg.max_open_positions);
    setInputValue('default-sl', cfg.default_stop_loss_pct);
    setInputValue('default-tp', cfg.default_take_profit_pct);
    setInputValue('max-pos-size', cfg.max_position_size_pct);

    const maxPosEl = document.getElementById('stat-max-positions');
    if (maxPosEl) maxPosEl.textContent = `Máx: ${cfg.max_open_positions}`;
  } catch (e) {
    console.error('Error cargando config de riesgo:', e);
  }
}

async function saveRiskConfig() {
  const config = {
    risk_per_trade_pct: parseFloat(getInputValue('risk-per-trade')),
    max_daily_loss_pct: parseFloat(getInputValue('max-daily-loss')),
    max_open_positions: parseInt(getInputValue('max-positions')),
    default_stop_loss_pct: parseFloat(getInputValue('default-sl')),
    default_take_profit_pct: parseFloat(getInputValue('default-tp')),
    max_position_size_pct: parseFloat(getInputValue('max-pos-size')),
  };

  // Validar
  if (Object.values(config).some(v => isNaN(v) || v <= 0)) {
    showToast('⚠️ Valores de riesgo inválidos', 'warning');
    return;
  }

  try {
    const res = await apiFetch('/config/risk', 'PUT', config);
    if (res?.success) {
      showToast('✅ Configuración de riesgo guardada', 'success');
      const maxPosEl = document.getElementById('stat-max-positions');
      if (maxPosEl) maxPosEl.textContent = `Máx: ${config.max_open_positions}`;
    }
  } catch (e) {
    showToast('❌ Error guardando configuración', 'error');
  }
}

function updateRiskBar(dailyLoss, accountValue) {
  const maxLossPct = parseFloat(getInputValue('max-daily-loss')) || 5;
  const maxLoss = accountValue * maxLossPct / 100;
  const pct = maxLoss > 0 ? Math.min((dailyLoss / maxLoss) * 100, 100) : 0;

  const bar = document.getElementById('risk-bar');
  const text = document.getElementById('risk-bar-text');
  if (bar) {
    bar.style.width = `${pct}%`;
    bar.className = `risk-bar-fill ${pct >= 70 ? 'danger' : ''}`;
  }
  if (text) {
    text.textContent = `$${dailyLoss.toFixed(2)} / Máx $${maxLoss.toFixed(2)} (${pct.toFixed(1)}%)`;
  }
}

// ─── Acciones de Bot ──────────────────────────────────────────────────────────

async function toggleBot(enabled) {
  try {
    const res = await apiFetch('/bot/toggle', 'POST', { enabled });
    showToast(res?.message || (enabled ? 'Bot activado' : 'Bot desactivado'),
      enabled ? 'success' : 'warning');
  } catch (e) {
    showToast('Error al cambiar estado del bot', 'error');
  }
}

async function reconnectIBKR() {
  showToast('🔄 Conectando a IBKR...', '');
  try {
    const res = await apiFetch('/bot/reconnect', 'POST');
    if (res?.connected) {
      showToast('✅ IBKR conectado', 'success');
      updateIBKRStatus(true);
    } else {
      showToast('❌ No se pudo conectar a IBKR. ¿Está TWS/IB Gateway corriendo?', 'error');
    }
  } catch (e) {
    showToast('❌ Error de conexión', 'error');
  }
}

async function closeAllPositions() {
  if (!confirm('¿Cerrar TODAS las posiciones abiertas? Esta acción no se puede deshacer.')) return;
  try {
    const res = await apiFetch('/bot/close_all', 'POST');
    showToast(res?.message || 'Posiciones cerradas', res?.success ? 'success' : 'error');
    await refreshPositions();
  } catch (e) {
    showToast('Error al cerrar posiciones', 'error');
  }
}

async function cancelAllOrders() {
  if (!confirm('¿Cancelar todas las órdenes pendientes?')) return;
  try {
    const res = await apiFetch('/bot/cancel_all', 'POST');
    showToast(res?.message || 'Órdenes canceladas', res?.success ? 'success' : 'error');
  } catch (e) {
    showToast('Error al cancelar órdenes', 'error');
  }
}

async function closePosition(symbol) {
  if (!confirm(`¿Cerrar posición de ${symbol}?`)) return;
  try {
    const res = await apiFetch('/webhook', 'POST', {
      secret: '__internal__',
      action: 'close',
      symbol: symbol
    });
    showToast(res?.message || `Posición ${symbol} cerrada`, 'success');
    await refreshPositions();
  } catch (e) {
    showToast(`Error cerrando ${symbol}`, 'error');
  }
}

// ─── Webhook URL ──────────────────────────────────────────────────────────────

function copyWebhook() {
  const url = document.getElementById('webhook-url')?.textContent || '';
  navigator.clipboard.writeText(url).then(() => {
    showToast('📋 URL copiada al portapapeles', 'success');
  });
}

function setWebhookUrl() {
  const el = document.getElementById('webhook-url');
  if (el) el.textContent = `http://${window.location.host}/webhook`;
}

// ─── Utilidades ───────────────────────────────────────────────────────────────

async function apiFetch(url, method = 'GET', body = null) {
  const opts = {
    method,
    headers: { 'Content-Type': 'application/json' },
  };
  if (body) opts.body = JSON.stringify(body);
  const res = await fetch(API + url, opts);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

function formatCurrency(value, signed = false) {
  if (value == null) return '—';
  const formatted = new Intl.NumberFormat('en-US', {
    style: 'currency', currency: 'USD', minimumFractionDigits: 2
  }).format(Math.abs(value));
  if (signed && value < 0) return `-${formatted}`;
  if (signed && value > 0) return `+${formatted}`;
  return formatted;
}

function formatDate(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  return d.toLocaleString('es-ES', {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'
  });
}

function setElement(id, text) {
  const el = document.getElementById(id);
  if (el) el.textContent = text;
}

function setInputValue(id, val) {
  const el = document.getElementById(id);
  if (el && val != null) el.value = val;
}

function getInputValue(id) {
  return document.getElementById(id)?.value || '';
}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

let toastTimer = null;
function showToast(msg, type = '') {
  const toast = document.getElementById('toast');
  if (!toast) return;
  clearTimeout(toastTimer);
  toast.textContent = msg;
  toast.className = `toast show ${type ? 'toast-' + type : ''}`;
  toastTimer = setTimeout(() => {
    toast.className = 'toast';
  }, 4000);
}

// ─── Init ─────────────────────────────────────────────────────────────────────

window.addEventListener('DOMContentLoaded', async () => {
  setWebhookUrl();
  await loadRiskConfig();
  await loadSignals();
  await loadTrades();

  // Cargar estado inicial si WS tarda
  setTimeout(async () => {
    try {
      const status = await apiFetch('/status');
      updateIBKRStatus(status.ibkr_connected);
      if (status.daily_stats) updateDailyStats(status.daily_stats);

      const account = await apiFetch('/account').catch(() => null);
      if (account) updateAccountStats(account);

      const positions = await apiFetch('/positions').catch(() => []);
      updatePositionsTable(positions);
    } catch (e) {
      console.log('Backend no disponible todavía');
    }
  }, 500);
});
