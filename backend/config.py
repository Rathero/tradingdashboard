"""
Configuración central del Trading Bot
Modifica estos valores o usa variables de entorno (.env)
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ─── IBKR Connection ───────────────────────────────────────────────────────────
IBKR_HOST = os.getenv("IBKR_HOST", "127.0.0.1")
IBKR_PORT = int(os.getenv("IBKR_PORT", 7497))   # 7497 = Paper | 7496 = Real
IBKR_CLIENT_ID = int(os.getenv("IBKR_CLIENT_ID", 1))
PAPER_TRADING = os.getenv("PAPER_TRADING", "true").lower() == "true"

# ─── Servidor ──────────────────────────────────────────────────────────────────
SERVER_HOST = os.getenv("SERVER_HOST", "0.0.0.0")
SERVER_PORT = int(os.getenv("SERVER_PORT", 8080))

# ─── Seguridad Webhook ─────────────────────────────────────────────────────────
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "CAMBIA_ESTA_CLAVE_SECRETA_123")

# ─── Gestión de Riesgo (valores por defecto) ───────────────────────────────────
RISK_PER_TRADE_PCT = float(os.getenv("RISK_PER_TRADE_PCT", 1.0))   # % del capital por trade
MAX_DAILY_LOSS_PCT = float(os.getenv("MAX_DAILY_LOSS_PCT", 5.0))   # % max pérdida diaria
MAX_OPEN_POSITIONS = int(os.getenv("MAX_OPEN_POSITIONS", 5))        # Max posiciones simultáneas
DEFAULT_STOP_LOSS_PCT = float(os.getenv("DEFAULT_STOP_LOSS_PCT", 2.0))   # Stop loss %
DEFAULT_TAKE_PROFIT_PCT = float(os.getenv("DEFAULT_TAKE_PROFIT_PCT", 4.0))  # Take profit %
MAX_POSITION_SIZE_PCT = float(os.getenv("MAX_POSITION_SIZE_PCT", 20.0))  # Max % del capital en 1 trade

# ─── Base de datos ─────────────────────────────────────────────────────────────
DB_PATH = os.getenv("DB_PATH", "trading_bot.db")

# ─── Telegram Notificaciones ──────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# ─── Google Gemini (Tips de trading) ──────────────────────────────────────────
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# ─── Logging ───────────────────────────────────────────────────────────────────
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
