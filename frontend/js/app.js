/**
 * Lógica principal del Dashboard (anónimo)
 */

// Inicialización — directo al dashboard
document.addEventListener("DOMContentLoaded", () => {
    initDashboard();
});

// ─── Dashboard Logic ─────────────────────────────────────────────────────────

async function initDashboard() {
    document.getElementById("main-content").style.display = "block";
    
    try {
        loadRiskConfig();
        loadTrades();
        loadSignals();
        updateWebhookUrl();
    } catch (e) {
        console.error("Error inicializando dashboard:", e);
        showToast("Error cargando el dashboard", "error");
    }
}

function updateWebhookUrl() {
    document.getElementById("webhook-url").innerText = `${window.location.origin}/webhook`;
}

// ─── Broker Config ───────────────────────────────────────────────────────────

function toggleBrokerFields() {
    const type = document.getElementById("broker-type").value;
    document.getElementById("fields-ibkr").style.display = type === "ibkr" ? "block" : "none";
}

async function saveBrokerConfig() {
    const type = document.getElementById("broker-type").value;
    let config = {
        host: document.getElementById("ibkr-host").value,
        port: parseInt(document.getElementById("ibkr-port").value)
    };

    try {
        await apiFetch("/config/broker", "PUT", { broker_type: type, broker_config: config });
        showToast("Configuración de broker actualizada", "success");
    } catch (e) {
        showToast("Error guardando config", "error");
    }
}

async function apiFetch(endpoint, method = "GET", body = null) {
    const options = {
        method,
        headers: {
            "Content-Type": "application/json"
        }
    };
    if (body) options.body = JSON.stringify(body);
    
    const resp = await fetch(endpoint, options);
    return resp.json();
}

// Métodos de la UI (Refactorizados)
async function loadRiskConfig() {
    const cfg = await apiFetch("/config/risk");
    document.getElementById("risk-per-trade").value = cfg.risk_per_trade_pct;
    document.getElementById("max-daily-loss").value = cfg.max_daily_loss_pct;
    document.getElementById("max-positions").value = cfg.max_open_positions;
}

async function saveRiskConfig() {
    const config = {
        risk_per_trade_pct: parseFloat(document.getElementById("risk-per-trade").value),
        max_daily_loss_pct: parseFloat(document.getElementById("max-daily-loss").value),
        max_open_positions: parseInt(document.getElementById("max-positions").value)
    };
    await apiFetch("/config/risk", "PUT", config);
    showToast("Configuración guardada", "success");
}

async function loadTrades() {
    const trades = await apiFetch("/trades");
    const container = document.getElementById("trades-body");
    // Lógica de renderizado de tabla (similar a la original)
    // ...
}

function showToast(msg, type = "info") {
    const toast = document.getElementById("toast");
    toast.innerText = msg;
    toast.className = `toast show ${type}`;
    setTimeout(() => toast.className = "toast", 3000);
}
