/**
 * Lógica principal del Dashboard SaaS
 */

// Variables de estado
let API_TOKEN = localStorage.getItem("trading_sas_token");
let CURRENT_USER = null;

// Inicialización
document.addEventListener("DOMContentLoaded", () => {
    if (!API_TOKEN) {
        showAuthOverlay();
    } else {
        initDashboard();
    }
});

// ─── Autenticación ────────────────────────────────────────────────────────────

function showAuthOverlay() {
    document.getElementById("auth-overlay").style.display = "flex";
    document.getElementById("main-content").style.display = "none";
}

function showRegister() {
    document.getElementById("login-form").style.display = "none";
    document.getElementById("register-form").style.display = "block";
    document.getElementById("auth-subtitle").innerText = "Crea tu cuenta de trading";
}

function showLogin() {
    document.getElementById("register-form").style.display = "none";
    document.getElementById("login-form").style.display = "block";
    document.getElementById("auth-subtitle").innerText = "Inicia sesión para gestionar tu trading";
}

async function login() {
    const user = document.getElementById("login-username").value;
    const pass = document.getElementById("login-password").value;
    
    try {
        const formData = new FormData();
        formData.append("username", user);
        formData.append("password", pass);

        const resp = await fetch("/auth/login", {
            method: "POST",
            body: formData
        });
        
        if (!resp.ok) throw new Error("Credenciales inválidas");
        
        const data = await resp.json();
        API_TOKEN = data.access_token;
        localStorage.setItem("trading_sas_token", API_TOKEN);
        
        initDashboard();
    } catch (e) {
        showToast(e.message, "error");
    }
}

async function register() {
    const user = document.getElementById("reg-username").value;
    const pass = document.getElementById("reg-password").value;
    
    try {
        const resp = await fetch("/auth/register", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ username: user, password: pass })
        });
        
        if (!resp.ok) throw new Error("Error en el registro");
        
        showToast("¡Cuenta creada! Ahora inicia sesión", "success");
        showLogin();
    } catch (e) {
        showToast(e.message, "error");
    }
}

function logout() {
    localStorage.removeItem("trading_sas_token");
    location.reload();
}

// ─── Dashboard Logic ─────────────────────────────────────────────────────────

async function initDashboard() {
    document.getElementById("auth-overlay").style.display = "none";
    document.getElementById("main-content").style.display = "block";
    
    // Cargar info de usuario
    try {
        const resp = await fetch("/auth/me", {
            headers: { "Authorization": `Bearer ${API_TOKEN}` }
        });
        if (!resp.ok) throw new Error("Token expirado");
        CURRENT_USER = await resp.json();
        
        updateUserInfo();
        loadRiskConfig();
        loadTrades();
        loadSignals();
        // Conectar WebSocket (se pasará a websocket.js)
        connectWS(API_TOKEN);
    } catch (e) {
        logout();
    }
}

function updateUserInfo() {
    document.getElementById("webhook-url").innerText = `${window.location.origin}/webhook`;
    // Aquí podrías añadir un botón de logout o mostrar el username
    console.log("Logged as", CURRENT_USER.username);
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
        // En el backend actual, guardamos el broker_config en el perfil del usuario
        // Podríamos tener un endpoint específico o un PUT /auth/me
        // Por consistencia temporal, asumiremos un endpoint PUT /config/broker
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
            "Authorization": `Bearer ${API_TOKEN}`,
            "Content-Type": "application/json"
        }
    };
    if (body) options.body = JSON.stringify(body);
    
    const resp = await fetch(endpoint, options);
    if (resp.status === 401) logout();
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
