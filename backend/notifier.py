import logging
import httpx
import asyncio
from typing import Optional, Any, List, Tuple
import json

logger = logging.getLogger(__name__)

class TelegramNotifier:
    def __init__(self, token: str = None, chat_id: str = None):
        self.token = token
        self.chat_id = chat_id
        self.enabled = bool(token and chat_id)
        self.api_url = f"https://api.telegram.org/bot{self.token}" if self.token else None

    async def send_message(self, text: str, parse_mode: str = "HTML", reply_markup: dict = None) -> Optional[int]:
        if not self.enabled: return None
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                payload = {"chat_id": self.chat_id, "text": text, "parse_mode": parse_mode}
                if reply_markup: payload["reply_markup"] = reply_markup
                resp = await client.post(f"{self.api_url}/sendMessage", json=payload)
                resp.raise_for_status()
                return resp.json().get("result", {}).get("message_id")
        except Exception as e:
            logger.error(f"Error Telegram send: {e}")
            return None

    async def edit_message(self, message_id: int, text: str, parse_mode: str = "HTML", reply_markup: dict = None) -> bool:
        if not self.enabled: return False
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                payload = {"chat_id": self.chat_id, "message_id": message_id, "text": text, "parse_mode": parse_mode}
                if reply_markup is not None: payload["reply_markup"] = reply_markup
                resp = await client.post(f"{self.api_url}/editMessageText", json=payload)
                resp.raise_for_status()
                return True
        except Exception as e:
            logger.error(f"Error Telegram edit: {e}")
            return False

    async def send_approval_message(self, signal_id: int, symbol: str, action: str, price: Any) -> Optional[int]:
        text = (
            f"🔔 <b>NUEVA SEÑAL PENDIENTE</b>\n"
            f"<b>Símbolo:</b> {symbol}\n"
            f"<b>Acción:</b> {action.upper()}\n"
            f"<b>Precio:</b> {price if price else 'Mercado'}\n\n"
            f"¿Deseas ejecutar esta operación?"
        )
        reply_markup = {
            "inline_keyboard": [[
                {"text": "✅ Aceptar", "callback_data": f"approve_{signal_id}"},
                {"text": "❌ Rechazar", "callback_data": f"reject_{signal_id}"}
            ]]
        }
        return await self.send_message(text, reply_markup=reply_markup)
