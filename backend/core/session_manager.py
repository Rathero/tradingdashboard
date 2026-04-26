import logging
import json
from typing import Dict, Any, Optional
from brokers.ibkr import IBKRBroker
from brokers.alpaca import AlpacaBroker
from notifier import TelegramNotifier
import database as db

logger = logging.getLogger(__name__)

class SessionManager:
    def __init__(self):
        # Mapeo: user_id -> { "broker": BaseBroker, "notifier": TelegramNotifier }
        self._sessions: Dict[int, Dict[str, Any]] = {}

    async def get_broker(self, user_id: int):
        """Obtiene o inicializa el broker de un usuario."""
        if user_id not in self._sessions:
            await self._init_session(user_id)
        return self._sessions.get(user_id, {}).get("broker")

    async def get_notifier(self, user_id: int):
        """Obtiene o inicializa el notificador de un usuario."""
        if user_id not in self._sessions:
            await self._init_session(user_id)
        return self._sessions.get(user_id, {}).get("notifier")

    async def _init_session(self, user_id: int):
        """Carga la configuración del usuario e inicializa sus servicios."""
        user = db.get_active_users() # Simplificado: aquí deberíamos tener un get_user_by_id
        user = next((u for u in user if u['id'] == user_id), None)
        
        if not user:
            logger.error(f"Usuario {user_id} no encontrado para inicializar sesión")
            return

        # 1. Inicializar Notificador
        notifier = TelegramNotifier() 
        notifier.token = user.get("tg_token")
        notifier.chat_id = user.get("tg_chat_id")
        notifier.enabled = bool(notifier.token and notifier.chat_id)
        notifier.api_url = f"https://api.telegram.org/bot{notifier.token}/sendMessage" if notifier.token else None

        # 2. Inicializar Broker
        broker_type = user.get("broker_type", "ibkr")
        config = json.loads(user.get("broker_config") or "{}")
        
        broker = None
        if broker_type == "ibkr":
            broker = IBKRBroker(
                host=config.get("host", "127.0.0.1"),
                port=int(config.get("port", 7497)),
                client_id=int(config.get("client_id", user_id)) # Usamos user_id como client_id para evitar conflictos
            )
        elif broker_type == "alpaca":
            broker = AlpacaBroker(
                api_key=config.get("api_key"),
                secret_key=config.get("secret_key"),
                paper=config.get("paper", True)
            )

        if broker:
            await broker.connect()

        self._sessions[user_id] = {
            "broker": broker,
            "notifier": notifier
        }
        logger.info(f"🚀 Sesión inicializada para usuario {user_id} ({broker_type})")

    async def close_all(self):
        """Cierra todas las conexiones de todas las sesiones."""
        for user_id, session in self._sessions.items():
            broker = session.get("broker")
            if broker:
                broker.disconnect()
        self._sessions.clear()

# Instancia global
session_manager = SessionManager()
