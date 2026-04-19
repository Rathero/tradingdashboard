"""
Base de datos SQLite para historial de trades, señales y P&L
"""
import sqlite3
import json
from datetime import datetime
from config import DB_PATH
import logging

logger = logging.getLogger(__name__)


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Inicializa las tablas de la base de datos."""
    conn = get_db()
    cursor = conn.cursor()

    # Tabla de señales recibidas
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            received_at TEXT NOT NULL,
            symbol TEXT NOT NULL,
            action TEXT NOT NULL,
            raw_payload TEXT,
            status TEXT DEFAULT 'pending',
            error_msg TEXT,
            order_id TEXT
        )
    """)

    # Tabla de trades ejecutados
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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
            notes TEXT
        )
    """)

    # Tabla de P&L diario (snapshot)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS daily_pnl (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT UNIQUE NOT NULL,
            realized_pnl REAL DEFAULT 0,
            unrealized_pnl REAL DEFAULT 0,
            total_trades INTEGER DEFAULT 0,
            winning_trades INTEGER DEFAULT 0
        )
    """)

    # Tabla de configuración de riesgo (persistente)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS risk_config (
            id INTEGER PRIMARY KEY DEFAULT 1,
            risk_per_trade_pct REAL DEFAULT 1.0,
            max_daily_loss_pct REAL DEFAULT 5.0,
            max_open_positions INTEGER DEFAULT 5,
            default_stop_loss_pct REAL DEFAULT 2.0,
            default_take_profit_pct REAL DEFAULT 4.0,
            max_position_size_pct REAL DEFAULT 20.0,
            updated_at TEXT
        )
    """)

    # Insertar config por defecto si no existe
    cursor.execute("""
        INSERT OR IGNORE INTO risk_config (id, updated_at) VALUES (1, ?)
    """, (datetime.utcnow().isoformat(),))

    conn.commit()
    conn.close()
    logger.info("📦 Base de datos inicializada correctamente")


# ─── Señales ───────────────────────────────────────────────────────────────────

def save_signal(symbol: str, action: str, payload: dict, status: str = "pending", error: str = None, order_id: str = None) -> int:
    conn = get_db()
    cursor = conn.execute("""
        INSERT INTO signals (received_at, symbol, action, raw_payload, status, error_msg, order_id)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (datetime.utcnow().isoformat(), symbol, action, json.dumps(payload), status, error, order_id))
    signal_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return signal_id


def get_signals(limit: int = 50):
    conn = get_db()
    rows = conn.execute("""
        SELECT * FROM signals ORDER BY received_at DESC LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_signal_by_id(signal_id: int):
    conn = get_db()
    row = conn.execute("SELECT * FROM signals WHERE id=?", (signal_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def update_signal_status(signal_id: int, status: str, error: str = None, order_id: str = None):
    conn = get_db()
    conn.execute("""
        UPDATE signals SET status=?, error_msg=?, order_id=? WHERE id=?
    """, (status, error, order_id, signal_id))
    conn.commit()
    conn.close()


# ─── Trades ────────────────────────────────────────────────────────────────────

def save_trade(symbol: str, side: str, qty: float, entry_price: float,
               stop_loss: float = None, take_profit: float = None,
               ibkr_order_id: str = None) -> int:
    conn = get_db()
    cursor = conn.execute("""
        INSERT INTO trades (opened_at, symbol, side, qty, entry_price, stop_loss, take_profit, ibkr_order_id, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'open')
    """, (datetime.utcnow().isoformat(), symbol, side, qty, entry_price, stop_loss, take_profit, ibkr_order_id))
    trade_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return trade_id


def close_trade(trade_id: int, exit_price: float, realized_pnl: float):
    conn = get_db()
    conn.execute("""
        UPDATE trades SET closed_at=?, exit_price=?, realized_pnl=?, status='closed'
        WHERE id=?
    """, (datetime.utcnow().isoformat(), exit_price, realized_pnl, trade_id))
    conn.commit()
    conn.close()


def get_trades(limit: int = 100, status: str = None):
    conn = get_db()
    if status:
        rows = conn.execute("SELECT * FROM trades WHERE status=? ORDER BY opened_at DESC LIMIT ?", (status, limit)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM trades ORDER BY opened_at DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ─── P&L Diario ────────────────────────────────────────────────────────────────

def upsert_daily_pnl(date: str, realized_pnl: float, unrealized_pnl: float, total: int, winning: int):
    conn = get_db()
    conn.execute("""
        INSERT INTO daily_pnl (date, realized_pnl, unrealized_pnl, total_trades, winning_trades)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(date) DO UPDATE SET
            realized_pnl=excluded.realized_pnl,
            unrealized_pnl=excluded.unrealized_pnl,
            total_trades=excluded.total_trades,
            winning_trades=excluded.winning_trades
    """, (date, realized_pnl, unrealized_pnl, total, winning))
    conn.commit()
    conn.close()


def get_pnl_history(days: int = 30):
    conn = get_db()
    rows = conn.execute("""
        SELECT * FROM daily_pnl ORDER BY date DESC LIMIT ?
    """, (days,)).fetchall()
    conn.close()
    return [dict(r) for r in reversed(rows)]


# ─── Configuración de Riesgo ───────────────────────────────────────────────────

def get_risk_config():
    conn = get_db()
    row = conn.execute("SELECT * FROM risk_config WHERE id=1").fetchone()
    conn.close()
    return dict(row) if row else {}


def update_risk_config(config: dict):
    conn = get_db()
    config["updated_at"] = datetime.utcnow().isoformat()
    fields = ", ".join([f"{k}=?" for k in config.keys()])
    values = list(config.values()) + [1]
    conn.execute(f"UPDATE risk_config SET {fields} WHERE id=?", values)
    conn.commit()
    conn.close()
