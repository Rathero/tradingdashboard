"""
Base de datos SQLite para SaaS Multi-usuario
Almacena usuarios, configuraciones de brokers, señales y trades.
"""
import sqlite3
import json
import logging
from datetime import datetime
from config import DB_PATH, DEFAULT_RISK_CONFIG

logger = logging.getLogger(__name__)

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Inicializa el esquema de base de datos multi-usuario."""
    conn = get_db()
    cursor = conn.cursor()

    # ─── Tabla de Usuarios ──────────────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            webhook_secret TEXT UNIQUE NOT NULL,
            tg_token TEXT,
            tg_chat_id TEXT,
            broker_type TEXT DEFAULT 'ibkr', -- 'ibkr'
            broker_config TEXT,              -- JSON con host, port, api_key, etc.
            created_at TEXT NOT NULL
        )
    """)

    # ─── Tabla de señales recibidas ─────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            received_at TEXT NOT NULL,
            symbol TEXT NOT NULL,
            action TEXT NOT NULL,
            raw_payload TEXT,
            status TEXT DEFAULT 'pending',
            error_msg TEXT,
            order_id TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    # ─── Tabla de trades ejecutados ──────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            opened_at TEXT NOT NULL,
            closed_at TEXT,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            qty REAL NOT NULL,
            entry_price REAL,
            exit_price REAL,
            stop_loss REAL,
            take_profit REAL,
            realized_pnl REAL,
            status TEXT DEFAULT 'open',
            ibkr_order_id TEXT,
            notes TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    # ─── Tabla de P&L diario ────────────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS daily_pnl (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            realized_pnl REAL DEFAULT 0,
            unrealized_pnl REAL DEFAULT 0,
            total_trades INTEGER DEFAULT 0,
            winning_trades INTEGER DEFAULT 0,
            UNIQUE(user_id, date),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    # ─── Tabla de configuración de riesgo (por usuario) ─────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS risk_config (
            user_id INTEGER PRIMARY KEY,
            risk_per_trade_pct REAL DEFAULT 1.0,
            max_daily_loss_pct REAL DEFAULT 5.0,
            max_open_positions INTEGER DEFAULT 5,
            default_stop_loss_pct REAL DEFAULT 2.0,
            default_take_profit_pct REAL DEFAULT 4.0,
            max_position_size_pct REAL DEFAULT 20.0,
            updated_at TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    conn.commit()
    conn.close()
    logger.info("📦 Base de datos multi-usuario lista")

# ─── Gestión de Usuarios ──────────────────────────────────────────────────────

def create_user(username, password_hash, webhook_secret, broker_type='ibkr', broker_config=None):
    conn = get_db()
    try:
        now = datetime.utcnow().isoformat()
        cursor = conn.execute("""
            INSERT INTO users (username, password_hash, webhook_secret, broker_type, broker_config, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (username, password_hash, webhook_secret, broker_type, json.dumps(broker_config or {}), now))
        user_id = cursor.lastrowid
        
        # Inicializar config de riesgo por defecto para el nuevo usuario
        rc = DEFAULT_RISK_CONFIG
        conn.execute("""
            INSERT INTO risk_config (user_id, risk_per_trade_pct, max_daily_loss_pct, max_open_positions, 
                                     default_stop_loss_pct, default_take_profit_pct, max_position_size_pct, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (user_id, rc['risk_per_trade_pct'], rc['max_daily_loss_pct'], rc['max_open_positions'],
              rc['default_stop_loss_pct'], rc['default_take_profit_pct'], rc['max_position_size_pct'], now))
        
        conn.commit()
        return user_id
    except sqlite3.IntegrityError:
        return None
    finally:
        conn.close()

def get_user_by_username(username):
    conn = get_db()
    row = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    conn.close()
    return dict(row) if row else None

def get_user_by_secret(secret):
    conn = get_db()
    row = conn.execute("SELECT * FROM users WHERE webhook_secret=?", (secret,)).fetchone()
    conn.close()
    return dict(row) if row else None

def get_active_users():
    conn = get_db()
    rows = conn.execute("SELECT * FROM users").fetchall()
    conn.close()
    return [dict(r) for r in rows]

# ─── Señales ──────────────────────────────────────────────────────────────────

def save_signal(user_id: int, symbol: str, action: str, payload: dict, status: str = "pending", error: str = None, order_id: str = None) -> int:
    conn = get_db()
    cursor = conn.execute("""
        INSERT INTO signals (user_id, received_at, symbol, action, raw_payload, status, error_msg, order_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (user_id, datetime.utcnow().isoformat(), symbol, action, json.dumps(payload), status, error, order_id))
    signal_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return signal_id

def get_signals(user_id: int, limit: int = 50):
    conn = get_db()
    rows = conn.execute("""
        SELECT * FROM signals WHERE user_id=? ORDER BY received_at DESC LIMIT ?
    """, (user_id, limit)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_signal_by_id(user_id: int, signal_id: int):
    conn = get_db()
    row = conn.execute("SELECT * FROM signals WHERE id=? AND user_id=?", (signal_id, user_id)).fetchone()
    conn.close()
    return dict(row) if row else None

def update_signal_status(signal_id: int, status: str, error: str = None, order_id: str = None):
    conn = get_db()
    conn.execute("""
        UPDATE signals SET status=?, error_msg=?, order_id=? WHERE id=?
    """, (status, error, order_id, signal_id))
    conn.commit()
    conn.close()

# ─── Trades ──────────────────────────────────────────────────────────────────

def save_trade(user_id: int, symbol: str, side: str, qty: float, entry_price: float,
               stop_loss: float = None, take_profit: float = None,
               ibkr_order_id: str = None) -> int:
    conn = get_db()
    cursor = conn.execute("""
        INSERT INTO trades (user_id, opened_at, symbol, side, qty, entry_price, stop_loss, take_profit, ibkr_order_id, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'open')
    """, (user_id, datetime.utcnow().isoformat(), symbol, side, qty, entry_price, stop_loss, take_profit, ibkr_order_id))
    trade_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return trade_id

def close_trade(user_id: int, trade_id: int, exit_price: float, realized_pnl: float):
    conn = get_db()
    conn.execute("""
        UPDATE trades SET closed_at=?, exit_price=?, realized_pnl=?, status='closed'
        WHERE id=? AND user_id=?
    """, (datetime.utcnow().isoformat(), exit_price, realized_pnl, trade_id, user_id))
    conn.commit()
    conn.close()

def get_trades(user_id: int, limit: int = 100, status: str = None):
    conn = get_db()
    if status:
        rows = conn.execute("SELECT * FROM trades WHERE user_id=? AND status=? ORDER BY opened_at DESC LIMIT ?", (user_id, status, limit)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM trades WHERE user_id=? ORDER BY opened_at DESC LIMIT ?", (user_id, limit)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

# ─── P&L Diario ────────────────────────────────────────────────────────────────

def upsert_daily_pnl(user_id: int, date: str, realized_pnl: float, unrealized_pnl: float, total: int, winning: int):
    conn = get_db()
    conn.execute("""
        INSERT INTO daily_pnl (user_id, date, realized_pnl, unrealized_pnl, total_trades, winning_trades)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id, date) DO UPDATE SET
            realized_pnl=excluded.realized_pnl,
            unrealized_pnl=excluded.unrealized_pnl,
            total_trades=excluded.total_trades,
            winning_trades=excluded.winning_trades
    """, (user_id, date, realized_pnl, unrealized_pnl, total, winning))
    conn.commit()
    conn.close()

def get_pnl_history(user_id: int, days: int = 30):
    conn = get_db()
    rows = conn.execute("""
        SELECT * FROM daily_pnl WHERE user_id=? ORDER BY date DESC LIMIT ?
    """, (user_id, days)).fetchall()
    conn.close()
    return [dict(r) for r in reversed(rows)]

# ─── Configuración de Riesgo ───────────────────────────────────────────────────

def get_risk_config(user_id: int):
    conn = get_db()
    row = conn.execute("SELECT * FROM risk_config WHERE user_id=?", (user_id,)).fetchone()
    conn.close()
    return dict(row) if row else {}

def update_risk_config(user_id: int, config: dict):
    conn = get_db()
    config["updated_at"] = datetime.utcnow().isoformat()
    fields = ", ".join([f"{k}=?" for k in config.keys() if k != "user_id"])
    values = [v for k, v in config.items() if k != "user_id"] + [user_id]
    conn.execute(f"UPDATE risk_config SET {fields} WHERE user_id=?", values)
    conn.commit()
    conn.close()
