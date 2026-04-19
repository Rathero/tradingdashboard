import logging
import httpx
import asyncio
from typing import Optional
import config

logger = logging.getLogger(__name__)

class TelegramNotifier:
    def __init__(self):
        self.enabled = bool(config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID)
        self.token = config.TELEGRAM_BOT_TOKEN
        self.chat_id = config.TELEGRAM_CHAT_ID
        self.api_url = f"https://api.telegram.org/bot{self.token}/sendMessage" if self.token else None

    async def send_message(self, text: str, parse_mode: str = "HTML") -> bool:
        """Envía un mensaje a Telegram de forma asíncrona."""
        if not self.enabled or not self.api_url:
            logger.debug("Telegram notifier desactivado o sin configurar.")
            return False

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                payload = {
                    "chat_id": self.chat_id,
                    "text": text,
                    "parse_mode": parse_mode
                }
                response = await client.post(self.api_url, json=payload)
                response.raise_for_status()
                logger.info("✅ Mensaje enviado a Telegram")
                return True
        except Exception as e:
            logger.error(f"❌ Error enviando mensaje a Telegram: {e}")
            return False

    def send_message_sync(self, text: str, parse_mode: str = "HTML"):
        """Envía un mensaje de forma síncrona (útil si hay que llamar desde contexto no-async)."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(self.send_message(text, parse_mode))
            else:
                asyncio.run(self.send_message(text, parse_mode))
        except Exception as e:
            logger.error(f"Error en send_message_sync: {e}")

# Instancia global
notifier = TelegramNotifier()
