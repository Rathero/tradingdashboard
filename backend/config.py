"""
Configuración central del Trading Bot SaaS
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ─── Seguridad y Autenticación ────────────────────────────────────────────────
# Secreto para firmar tokens JWT (Cambiar en producción)
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "CAMBIA_ESTO_POR_ALGO_SEGURO_S44S_B0T")
JWT_ALGORITHM = "HS256"
JWT_ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 1 semana

# ─── Servidor ──────────────────────────────────────────────────────────────────
SERVER_HOST = os.getenv("SERVER_HOST", "0.0.0.0")
SERVER_PORT = int(os.getenv("SERVER_PORT", 8080))

# ─── Base de Datos ─────────────────────────────────────────────────────────────
DB_PATH = os.getenv("DB_PATH", "trading_bot.db")

# ─── Telegram Notificaciones ──────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# ─── Google Gemini (Tips de trading) ──────────────────────────────────────────
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# ─── Logging ───────────────────────────────────────────────────────────────────
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# ─── Valores por Defecto para Nuevos Usuarios ─────────────────────────────────
DEFAULT_RISK_CONFIG = {
    "risk_per_trade_pct": 1.0,
    "max_daily_loss_pct": 5.0,
    "max_open_positions": 5,
    "default_stop_loss_pct": 2.0,
    "default_take_profit_pct": 4.0,
    "max_position_size_pct": 20.0
}

# ─── IBKR System Defaults ─────────────────────────────────────────────────────
# Estos valores se pueden sobreescribir por usuario en la BD
IBKR_HOST_DEFAULT = "127.0.0.1"
IBKR_PORT_DEFAULT = 7497
IBKR_CLIENT_ID_DEFAULT = 1
