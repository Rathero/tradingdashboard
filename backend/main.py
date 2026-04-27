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
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, date, timedelta
from typing import List, Dict, Any, Optional

import uvicorn
import httpx
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel

import config
import database as db
from core.auth import get_password_hash, verify_password, create_access_token, get_current_user
from core.session_manager import session_manager
from signal_processor import parse_signal
from order_manager import OrderManager
from risk_manager import RiskManager
from notifier import notifier
from gemini_client import generate_trading_tip

# ─── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger(__name__)
logging.getLogger("ib_insync").setLevel(logging.WARNING)

# ─── Models ────────────────────────────────────────────────────────────────────
class UserRegister(BaseModel):
    username: str
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str

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
    """Actualiza datos para todos los usuarios activos cada 5 segundos."""
    while True:
        await asyncio.sleep(5)
        users = db.get_active_users()
        for user in users:
            uid = user['id']
            try:
                broker = await session_manager.get_broker(uid)
                if not broker or not broker.is_connected(): continue

                acc = await broker.get_account_summary()
                pos = await broker.get_positions()
                
                # Sincronizar P&L en BD (Simplificado)
                today = date.today().isoformat()
                db.upsert_daily_pnl(uid, today, acc.get("realized_pnl", 0), acc.get("unrealized_pnl", 0), 0, 0)

                await manager.send_to_user(uid, {
                    "type": "live_update",
                    "account": acc,
                    "positions": pos,
                    "timestamp": datetime.utcnow().isoformat()
                })
            except Exception as e:
                logger.debug(f"Error update usuario {uid}: {e}")

# ─── Lifecycle ─────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    loop = asyncio.get_running_loop()
    asyncio.set_event_loop(loop)
    import eventkit.util
    eventkit.util.main_event_loop = loop
    
    logger.info("🚀 Iniciando Trading Bot...")
    db.init_db()
    task = asyncio.create_task(push_live_updates())
    yield
    task.cancel()
    await session_manager.close_all()

app = FastAPI(title="Trading SaaS API", version="2.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ─── Auth Endpoints ────────────────────────────────────────────────────────────
@app.post("/auth/register")
async def register(user_data: UserRegister):
    if db.get_user_by_username(user_data.username):
        raise HTTPException(status_code=400, detail="El usuario ya existe")
    
    secret = str(uuid.uuid4())[:18]
    uid = db.create_user(
        username=user_data.username,
        password_hash=get_password_hash(user_data.password),
        webhook_secret=secret
    )
    return {"message": "Usuario creado", "webhook_secret": secret}

@app.post("/auth/login", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    user = db.get_user_by_username(form_data.username)
    if not user or not verify_password(form_data.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Credenciales incorrectas")
    
    access_token = create_access_token(data={"sub": user["username"]})
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/auth/me")
async def get_me(user: dict = Depends(get_current_user)):
    return {"id": user["id"], "username": user["username"], "webhook_secret": user["webhook_secret"]}

# ─── Webhook ───────────────────────────────────────────────────────────────────
@app.post("/webhook")
async def receive_webhook(request: Request):
    payload = await request.json()
    secret = payload.get("secret")
    user = db.get_user_by_secret(secret)
    if not user:
        raise HTTPException(status_code=403, detail="Webhook secret inválido")

    valid, msg, signal = parse_signal(payload)
    if not valid:
        db.save_signal(user["id"], "UNKNOWN", "REJECTED", payload, status="error", error=msg)
        raise HTTPException(status_code=400, detail=msg)

    # Iniciar procesamiento
    broker = await session_manager.get_broker(user["id"])
    notifier = await session_manager.get_notifier(user["id"])
    risk = RiskManager(user["id"])
    
    om = OrderManager(user["id"], broker, notifier, risk)
    # Por ahora procesamos directo (o podríamos enviarlo a Telegram para aprobación si se añade el polling)
    asyncio.create_task(om.process_signal(signal))
    
    return {"status": "processing", "user": user["username"]}

# ─── Dashboard Endpoints ───────────────────────────────────────────────────────
    # Notificar señal válida en Telegram + tip de Gemini
    tip = await generate_trading_tip(signal['symbol'], signal['action'])
    telegram_msg = (
        f"📨 <b>Señal recibida</b>\n"
        f"Símbolo: {signal['symbol']}\n"
        f"Acción: {signal['action'].upper()}\n"
        f"Precio: {signal.get('price', 'Mercado')}"
    )
    if tip:
        telegram_msg += f"\n\n💡 <b>Tip del Portfolio Manager:</b>\n{tip}"
    await notifier.send_message(telegram_msg)

    # Procesar señal (async)
    result = await order_manager.process_signal(signal)

    # Notificar al dashboard
    await manager.broadcast({
        "type": "new_signal",
        "symbol": signal.get("symbol", ""),
        "action": signal.get("action", ""),
        "result": result,
        "timestamp": datetime.utcnow().isoformat()
    })

    status_code = 200 if result["success"] else 500
    return {"status": "ok" if result["success"] else "error", **result}


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
async def get_account(user: dict = Depends(get_current_user)):
    broker = await session_manager.get_broker(user["id"])
    if not broker or not broker.is_connected():
        return {"connected": False}
    return await broker.get_account_summary()

@app.get("/positions")
async def get_positions(user: dict = Depends(get_current_user)):
    broker = await session_manager.get_broker(user["id"])
    return await broker.get_positions() if broker else []

@app.get("/trades")
async def get_trades(user: dict = Depends(get_current_user)):
    return db.get_trades(user["id"])

@app.get("/config/risk")
async def get_risk(user: dict = Depends(get_current_user)):
    return db.get_risk_config(user["id"])

@app.put("/config/broker")
async def update_broker_config(data: dict, user: dict = Depends(get_current_user)):
    """Actualiza la configuración del broker del usuario."""
    broker_type = data.get("broker_type")
    broker_config = data.get("broker_config")
    
    conn = db.get_db()
    conn.execute(
        "UPDATE users SET broker_type=?, broker_config=? WHERE id=?",
        (broker_type, json.dumps(broker_config), user["id"])
    )
    conn.commit()
    conn.close()
    
    # Reiniciar sesión para aplicar cambios
    await session_manager._init_session(user["id"])
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
async def websocket_endpoint(websocket: WebSocket, token: str = None):
    # En producción usaríamos el token para autenticar
    # Mock user_id 1 por ahora para pruebas de frontend iniciales
    uid = 1 
    await manager.connect(uid, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(uid, websocket)

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000)
