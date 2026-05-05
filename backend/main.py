import asyncio
import sys


try:
    loop = asyncio.get_event_loop()
except RuntimeError:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

import json
import logging
import os

from contextlib import asynccontextmanager
from datetime import datetime, date, timedelta
from typing import List, Dict, Any, Optional

import uvicorn
import httpx
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import config
import database as db
from core.session_manager import session_manager
from signal_processor import parse_signal
from order_manager import OrderManager
from risk_manager import RiskManager
from gemini_client import generate_trading_tip

# ─── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger(__name__)
logging.getLogger("ib_insync").setLevel(logging.WARNING)

# ─── ID fijo (anónimo, sin login) ──────────────────────────────────────────────
USER_ID = 1

def ensure_anonymous_user():
    """Crea la fila anónima en BD si no existe (id=1)."""
    import uuid as _uuid
    conn = db.get_db()
    row = conn.execute("SELECT id FROM users WHERE id=1").fetchone()
    if not row:
        now = __import__('datetime').datetime.utcnow().isoformat()
        conn.execute(
            "INSERT INTO users (id, username, password_hash, webhook_secret, broker_type, broker_config, created_at) VALUES (?,?,?,?,?,?,?)",
            (1, "anon", "-", str(_uuid.uuid4())[:18], "ibkr", "{}", now)
        )
        # Inicializar config de riesgo
        rc = config.DEFAULT_RISK_CONFIG
        conn.execute(
            "INSERT OR IGNORE INTO risk_config (user_id, risk_per_trade_pct, max_daily_loss_pct, max_open_positions, default_stop_loss_pct, default_take_profit_pct, max_position_size_pct, updated_at) VALUES (?,?,?,?,?,?,?,?)",
            (1, rc['risk_per_trade_pct'], rc['max_daily_loss_pct'], rc['max_open_positions'], rc['default_stop_loss_pct'], rc['default_take_profit_pct'], rc['max_position_size_pct'], now)
        )
        conn.commit()
        logger.info("🟢 Usuario anónimo creado (id=1)")
    conn.close()

# ─── WebSocket Manager ─────────────────────────────────────────────────────────
class ConnectionManager:
    def __init__(self):
        # user_id -> List[WebSocket]
        self.active_connections: Dict[int, List[WebSocket]] = {}

    async def connect(self, user_id: int, websocket: WebSocket):
        await websocket.accept()
        if user_id not in self.active_connections:
            self.active_connections[user_id] = []
        self.active_connections[user_id].append(websocket)

    def disconnect(self, user_id: int, websocket: WebSocket):
        if user_id in self.active_connections:
            if websocket in self.active_connections[user_id]:
                self.active_connections[user_id].remove(websocket)

    async def send_to_user(self, user_id: int, data: dict):
        if user_id not in self.active_connections:
            return
        msg = json.dumps(data)
        for ws in self.active_connections[user_id]:
            try:
                await ws.send_text(msg)
            except:
                pass

manager = ConnectionManager()

# ─── Background Tasks ──────────────────────────────────────────────────────────
async def push_live_updates():
    """Actualiza datos cada 5 segundos."""
    while True:
        await asyncio.sleep(5)
        try:
            broker = await session_manager.get_broker(USER_ID)
            if not broker or not broker.is_connected(): continue

            acc = await broker.get_account_summary()
            pos = await broker.get_positions()
            
            today = date.today().isoformat()
            db.upsert_daily_pnl(USER_ID, today, acc.get("realized_pnl", 0), acc.get("unrealized_pnl", 0), 0, 0)

            await manager.send_to_user(USER_ID, {
                "type": "live_update",
                "account": acc,
                "positions": pos,
                "timestamp": datetime.utcnow().isoformat()
            })
        except Exception as e:
            logger.debug(f"Error update: {e}")

# ─── Lifecycle ─────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    loop = asyncio.get_running_loop()
    asyncio.set_event_loop(loop)
    import eventkit.util
    eventkit.util.main_event_loop = loop
    
    logger.info("🚀 Iniciando Trading Bot...")
    db.init_db()
    ensure_anonymous_user()
    task = asyncio.create_task(push_live_updates())
    yield
    task.cancel()
    await session_manager.close_all()

app = FastAPI(title="Trading Bot API", version="2.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ─── Info ──────────────────────────────────────────────────────────────────────
@app.get("/info")
async def get_info():
    conn = db.get_db()
    row = conn.execute("SELECT webhook_secret FROM users WHERE id=1").fetchone()
    conn.close()
    return {"webhook_secret": row["webhook_secret"] if row else ""}

# ─── Webhook ───────────────────────────────────────────────────────────────────
@app.post("/webhook")
async def receive_webhook(request: Request):
    payload = await request.json()

    valid, msg, signal = parse_signal(payload)
    if not valid:
        db.save_signal(USER_ID, "UNKNOWN", "REJECTED", payload, status="error", error=msg)
        raise HTTPException(status_code=400, detail=msg)

    broker = await session_manager.get_broker(USER_ID)
    notifier = await session_manager.get_notifier(USER_ID)
    risk = RiskManager(USER_ID)
    
    om = OrderManager(USER_ID, broker, notifier, risk)
    async def process_and_notify():
        result = await om.process_signal(signal)
        
        tip = await generate_trading_tip(signal.get('symbol', ''), signal.get('action', ''))
        telegram_msg = (
            f"📨 <b>Señal recibida</b>\n"
            f"Símbolo: {signal.get('symbol', '')}\n"
            f"Acción: {signal.get('action', '').upper()}\n"
            f"Precio: {signal.get('price', 'Mercado')}"
        )
        if tip:
            telegram_msg += f"\n\n💡 <b>Tip del Portfolio Manager:</b>\n{tip}"
        await notifier.send_message(telegram_msg)

        await manager.send_to_user(USER_ID, {
            "type": "new_signal",
            "symbol": signal.get("symbol", ""),
            "action": signal.get("action", ""),
            "result": result,
            "timestamp": datetime.utcnow().isoformat()
        })

    asyncio.create_task(process_and_notify())
    return {"status": "processing"}


# ─── Estado del Bot ────────────────────────────────────────────────────────────
@app.get("/status")
async def get_status():
    """Estado general: conexión IBKR, modo (paper/real), bot activo, etc."""
    return {
        "ibkr_connected": ibkr.is_connected(),
        "paper_trading": config.PAPER_TRADING,
        "ibkr_port": config.IBKR_PORT,
        "bot_enabled": risk_manager.bot_enabled,
        "daily_stats": risk_manager.daily_stats,
        "version": "1.0.0",
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.post("/bot/toggle")
async def toggle_bot(body: dict):
    """Habilitar/deshabilitar el bot."""
    enabled = body.get("enabled", True)
    risk_manager.bot_enabled = enabled
    action = "✅ Bot habilitado" if enabled else "🔴 Bot deshabilitado"
    logger.info(action)
    await manager.broadcast({"type": "bot_toggle", "enabled": enabled})
    return {"success": True, "enabled": enabled, "message": action}


@app.post("/bot/reconnect")
async def reconnect_ibkr():
    """Intentar reconectar con IBKR."""
    await ibkr.connect()
    return {"connected": ibkr.is_connected()}


@app.post("/bot/close_all")
async def close_all():
    """Cerrar todas las posiciones."""
    result = await order_manager.process_signal({"action": "close_all"})
    await manager.broadcast({"type": "close_all", "result": result})
    return result


@app.post("/bot/cancel_all")
async def cancel_all():
    """Cancelar todas las órdenes pendientes."""
    result = await ibkr.cancel_all_orders()
    return {"success": result, "message": "Órdenes canceladas" if result else "Error"}


# ─── Cuenta ────────────────────────────────────────────────────────────────────
@app.get("/account")
async def get_account():
    broker = await session_manager.get_broker(USER_ID)
    if not broker or not broker.is_connected():
        return {"connected": False}
    return await broker.get_account_summary()

@app.get("/positions")
async def get_positions():
    broker = await session_manager.get_broker(USER_ID)
    return await broker.get_positions() if broker else []

@app.get("/trades")
async def get_trades():
    return db.get_trades(USER_ID)

@app.get("/config/risk")
async def get_risk():
    return db.get_risk_config(USER_ID)

@app.put("/config/broker")
async def update_broker_config(data: dict):
    """Actualiza la configuración del broker."""
    broker_type = data.get("broker_type")
    broker_config = data.get("broker_config")
    
    conn = db.get_db()
    conn.execute(
        "UPDATE users SET broker_type=?, broker_config=? WHERE id=?",
        (broker_type, json.dumps(broker_config), USER_ID)
    )
    conn.commit()
    conn.close()
    
    await session_manager._init_session(USER_ID)
    return {"success": True}

# ─── Frontend & Static ─────────────────────────────────────────────────────────
frontend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend"))
if os.path.exists(frontend_dir):
    app.mount("/css", StaticFiles(directory=os.path.join(frontend_dir, "css")), name="css")
    app.mount("/js", StaticFiles(directory=os.path.join(frontend_dir, "js")), name="js")

@app.get("/")
async def index():
    return FileResponse(os.path.join(frontend_dir, "index.html"))

# ─── WebSocket Endpoints ───────────────────────────────────────────────────────
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(USER_ID, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(USER_ID, websocket)

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000)
