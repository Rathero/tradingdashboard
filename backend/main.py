"""
FastAPI Server principal:
- Webhook para recibir señales de TradingView
- REST API para el dashboard
- WebSocket para actualizaciones en tiempo real
"""
import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, date
from typing import List

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

import config
import database as db
from ibkr_client import ibkr
from order_manager import order_manager
from risk_manager import risk_manager
from signal_processor import parse_signal
from notifier import notifier

# ─── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger(__name__)

# Silenciar los logs de nivel INFO de ib_insync ("Warning 10167" se registra como INFO allí)
logging.getLogger("ib_insync").setLevel(logging.WARNING)
logging.getLogger("ib_insync.wrapper").setLevel(logging.ERROR)


# ─── WebSocket Manager ─────────────────────────────────────────────────────────
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, data: dict):
        msg = json.dumps(data)
        dead = []
        for ws in self.active_connections:
            try:
                await ws.send_text(msg)
            except:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


manager = ConnectionManager()


# ─── Background tasks ──────────────────────────────────────────────────────────
async def push_live_updates():
    """Envía actualizaciones en tiempo real al dashboard cada 3 segundos."""
    while True:
        await asyncio.sleep(3)
        try:
            if not manager.active_connections:
                continue

            account = await ibkr.get_account_summary() if ibkr.is_connected() else {}
            positions = await ibkr.get_positions() if ibkr.is_connected() else []

            # Actualizar P&L diario en BD
            today_str = date.today().isoformat()
            closed_today = db.get_trades(status="closed")
            today_pnl = sum(t.get("realized_pnl", 0) or 0 for t in closed_today
                            if t.get("closed_at", "").startswith(today_str))
            unrealized = sum(p.get("unrealized_pnl", 0) for p in positions)

            db.upsert_daily_pnl(
                date=today_str,
                realized_pnl=today_pnl,
                unrealized_pnl=unrealized,
                total=risk_manager._daily_trades,
                winning=risk_manager._winning_trades,
            )

            await manager.broadcast({
                "type": "live_update",
                "timestamp": datetime.utcnow().isoformat(),
                "ibkr_connected": ibkr.is_connected(),
                "account": account,
                "positions": positions,
                "daily_stats": risk_manager.daily_stats,
            })
        except Exception as e:
            logger.debug(f"Error en push_live_updates: {e}")


# ─── Sincronizar posiciones IBKR → BD ─────────────────────────────────────────
async def sync_ibkr_positions_to_db() -> int:
    """
    Importa las posiciones abiertas en IBKR a la tabla 'trades' local
    como registros con status='open', evitando duplicados por ibkr_order_id o símbolo.
    Devuelve el número de posiciones importadas.
    """
    if not ibkr.is_connected():
        return 0
    try:
        positions = await ibkr.get_positions()
        existing = {t["symbol"]: t for t in db.get_trades(status="open")}
        imported = 0
        for pos in positions:
            sym = pos["symbol"]
            if sym in existing:
                continue  # ya registrado
            db.save_trade(
                symbol=sym,
                side=pos["side"],
                qty=pos["qty"],
                entry_price=pos["avg_cost"],
                stop_loss=None,
                take_profit=None,
                ibkr_order_id=None,
            )
            imported += 1
            logger.info(f"📥 Posición importada de IBKR → BD: {pos['side']} {pos['qty']} {sym} @ {pos['avg_cost']}")
        if imported:
            logger.info(f"✅ {imported} posición(es) sincronizadas desde IBKR")
        return imported
    except Exception as e:
        logger.error(f"Error sincronizando posiciones IBKR: {e}")
        return 0


# ─── App Lifecycle ─────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Iniciando Trading Bot...")
    db.init_db()

    # Conectar a IBKR
    connected = await ibkr.connect()
    if connected:
        logger.info("✅ IBKR conectado")
        # Importar posiciones existentes que no estén ya en la BD
        await sync_ibkr_positions_to_db()
    else:
        logger.warning("⚠️ IBKR no disponible - arranca en modo desconectado")

    # Iniciar updates en tiempo real
    task = asyncio.create_task(push_live_updates())

    yield

    task.cancel()
    ibkr.disconnect()
    logger.info("👋 Bot detenido")


# ─── FastAPI App ───────────────────────────────────────────────────────────────
app = FastAPI(
    title="Trading Bot API",
    description="Bot de trading automático TradingView + Interactive Brokers",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Servir el frontend — montamos /css y /js directamente para que el HTML los encuentre
frontend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend"))
if os.path.exists(frontend_dir):
    css_dir = os.path.join(frontend_dir, "css")
    js_dir  = os.path.join(frontend_dir, "js")
    if os.path.exists(css_dir):
        app.mount("/css", StaticFiles(directory=css_dir), name="css")
    if os.path.exists(js_dir):
        app.mount("/js", StaticFiles(directory=js_dir), name="js")
    logger.info(f"📂 Frontend cargado desde: {frontend_dir}")


# ─── Webhook ───────────────────────────────────────────────────────────────────
@app.post("/webhook")
async def receive_webhook(request: Request):
    """Endpoint principal para recibir alertas de TradingView."""
    raw_body = await request.body()
    try:
        payload = json.loads(raw_body)
    except Exception as e:
        body_text = raw_body.decode(errors="replace")
        error_msg = f"❌ <b>Error JSON Webhook</b>\nError: {str(e)}\nBody: <code>{body_text}</code>"
        logger.error(f"Error parseando JSON: {e} | Body: {body_text}")
        await notifier.send_message(error_msg)
        raise HTTPException(status_code=400, detail="JSON inválido")

    logger.info(f"📨 Webhook recibido: {payload}")

    # Parsear y validar señal
    valid, msg, signal = parse_signal(payload)
    if not valid:
        logger.warning(f"🚫 Señal inválida: {msg}")
        # Guardar en base de datos para tener registro de señales inválidas
        symbol = str(payload.get("symbol", "UNKNOWN"))
        action_received = str(payload.get("action", "UNKNOWN"))
        db.save_signal(symbol, action_received, payload, status="rejected", error=msg)
        
        # Notificar al dashboard de la señal rechazada
        await manager.broadcast({
            "type": "new_signal",
            "symbol": symbol,
            "action": action_received,
            "result": {"success": False, "message": msg},
            "timestamp": datetime.utcnow().isoformat()
        })
        
        await notifier.send_message(f"🚫 <b>Señal rechazada</b>\nSímbolo: {symbol}\nAcción: {action_received}\nMotivo: {msg}")
        raise HTTPException(status_code=403, detail=msg)

    # Notificar señal válida en Telegram
    await notifier.send_message(f"📨 <b>Señal recibida</b>\nSímbolo: {signal['symbol']}\nAcción: {signal['action']}\nPrecio: {signal.get('price', 'Mercado')}")

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
async def get_account():
    """Resumen de la cuenta IBKR. Devuelve vacío si no está conectado."""
    if not ibkr.is_connected():
        return {"ibkr_connected": False, "net_liquidation": 0, "buying_power": 0,
                "cash_balance": 0, "unrealized_pnl": 0, "realized_pnl": 0}
    return await ibkr.get_account_summary()


# ─── Posiciones ────────────────────────────────────────────────────────────────
@app.get("/positions")
async def get_positions():
    """Posiciones abiertas actuales."""
    if not ibkr.is_connected():
        return []
    return await ibkr.get_positions()


# ─── Órdenes ───────────────────────────────────────────────────────────────────
@app.get("/orders")
async def get_orders():
    """Órdenes abiertas/pendientes."""
    if not ibkr.is_connected():
        return []
    return await ibkr.get_open_orders()


# ─── Señales ───────────────────────────────────────────────────────────────────
@app.get("/signals")
async def get_signals(limit: int = 50):
    """Log de señales recibidas de TradingView."""
    return db.get_signals(limit)


# ─── Trades ────────────────────────────────────────────────────────────────────
@app.get("/trades")
async def get_trades(limit: int = 100, status: str = None):
    """Historial de trades ejecutados."""
    return db.get_trades(limit, status)


@app.post("/trades/sync")
async def sync_trades():
    """Importa posiciones abiertas en IBKR que no estén en la BD local."""
    if not ibkr.is_connected():
        raise HTTPException(status_code=503, detail="IBKR no conectado")
    imported = await sync_ibkr_positions_to_db()
    return {"success": True, "imported": imported, "message": f"{imported} posición(es) importada(s)"}


# ─── P&L ───────────────────────────────────────────────────────────────────────
@app.get("/pnl")
async def get_pnl(days: int = 30):
    """Histórico de P&L diario para el gráfico."""
    return db.get_pnl_history(days)


# ─── Configuración de Riesgo ───────────────────────────────────────────────────
@app.get("/config/risk")
async def get_risk_config():
    """Configuración de riesgo actual."""
    return db.get_risk_config()


@app.put("/config/risk")
async def update_risk_config(body: dict):
    """Actualizar configuración de riesgo."""
    allowed_fields = {
        "risk_per_trade_pct", "max_daily_loss_pct", "max_open_positions",
        "default_stop_loss_pct", "default_take_profit_pct", "max_position_size_pct"
    }
    update = {k: v for k, v in body.items() if k in allowed_fields}
    if not update:
        raise HTTPException(status_code=400, detail="No hay campos válidos para actualizar")
    db.update_risk_config(update)
    logger.info(f"⚙️ Configuración de riesgo actualizada: {update}")
    return {"success": True, "config": db.get_risk_config()}


# ─── WebSocket ─────────────────────────────────────────────────────────────────
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    logger.info(f"🔗 Nueva conexión WebSocket ({len(manager.active_connections)} activas)")
    try:
        # Enviar estado inicial
        account = await ibkr.get_account_summary() if ibkr.is_connected() else {}
        positions = await ibkr.get_positions() if ibkr.is_connected() else []
        await websocket.send_text(json.dumps({
            "type": "init",
            "ibkr_connected": ibkr.is_connected(),
            "account": account,
            "positions": positions,
            "daily_stats": risk_manager.daily_stats,
        }))
        while True:
            await websocket.receive_text()  # Keep alive
    except WebSocketDisconnect:
        manager.disconnect(websocket)
        logger.info(f"🔌 WebSocket desconectado ({len(manager.active_connections)} activas)")


# ─── Frontend ──────────────────────────────────────────────────────────────────
@app.get("/")
async def serve_dashboard():
    """Sirve el dashboard web."""
    index_path = os.path.join(frontend_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "Dashboard no encontrado - asegúrate de que la carpeta frontend existe"}


# ─── Entry Point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=config.SERVER_HOST,
        port=config.SERVER_PORT,
        reload=False,
        log_level=config.LOG_LEVEL.lower()
    )
