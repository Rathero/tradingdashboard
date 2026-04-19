import logging
import httpx
import asyncio
from typing import Optional, Any, List, Tuple
import json
import config

logger = logging.getLogger(__name__)

class TelegramNotifier:
    def __init__(self):
        self.enabled = bool(config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID)
        self.token = config.TELEGRAM_BOT_TOKEN
        self.chat_id = config.TELEGRAM_CHAT_ID
        self.api_url = f"https://api.telegram.org/bot{self.token}/sendMessage" if self.token else None

    async def send_message(self, text: str, parse_mode: str = "HTML", reply_markup: dict = None) -> Optional[int]:
        """Envía un mensaje a Telegram de forma asíncrona. Devuelve el message_id si tiene éxito."""
        if not self.enabled or not self.api_url:
            logger.debug("Telegram notifier desactivado o sin configurar.")
            return None

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                payload = {
                    "chat_id": self.chat_id,
                    "text": text,
                    "parse_mode": parse_mode
                }
                if reply_markup:
                    payload["reply_markup"] = reply_markup
                    
                response = await client.post(self.api_url, json=payload)
                response.raise_for_status()
                data = response.json()
                logger.info("✅ Mensaje enviado a Telegram")
                return data.get("result", {}).get("message_id")
        except Exception as e:
            logger.error(f"❌ Error enviando mensaje a Telegram: {e}")
            return None

    async def edit_message(self, message_id: int, text: str, parse_mode: str = "HTML", reply_markup: dict = None) -> bool:
        """Edita un mensaje existente en Telegram."""
        if not self.enabled or not self.token:
            return False
            
        url = f"https://api.telegram.org/bot{self.token}/editMessageText"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                payload = {
                    "chat_id": self.chat_id,
                    "message_id": message_id,
                    "text": text,
                    "parse_mode": parse_mode
                }
                if reply_markup is not None: # Permitir enviar {} para quitar botones
                    payload["reply_markup"] = reply_markup
                    
                response = await client.post(url, json=payload)
                response.raise_for_status()
                return True
        except Exception as e:
            logger.error(f"❌ Error editando mensaje en Telegram: {e}")
            return False

    # ─── Data Fetching & Technical Analysis ───────────────────────────────────

    def _calculate_ema(self, prices: List[float], period: int = 200) -> Optional[float]:
        """Calcula la Media Móvil Exponencial (EMA)."""
        if len(prices) < period:
            return None
        
        multiplier = 2 / (period + 1)
        ema = sum(prices[:period]) / period  # Simple MA as starting point
        
        for price in prices[period:]:
            ema = (price - ema) * multiplier + ema
        return ema

    def _calculate_rsi(self, prices: List[float], period: int = 14) -> Optional[float]:
        """Calcula el Relative Strength Index (RSI)."""
        if len(prices) < period + 1:
            return None
            
        deltas = [prices[i+1] - prices[i] for i in range(len(prices)-1)]
        seed = deltas[:period]
        up = sum([d for d in seed if d > 0]) / period
        down = sum([-d for d in seed if d < 0]) / period
        
        if down == 0: return 100
        rs = up / down
        
        for d in deltas[period:]:
            u = d if d > 0 else 0
            d_val = -d if d < 0 else 0
            up = (up * (period - 1) + u) / period
            down = (down * (period - 1) + d_val) / period
            
        if down == 0: return 100
        rs = up / down
        return 100 - (100 / (1 + rs))

    async def _get_fear_greed_index(self) -> Tuple[Optional[float], Optional[str]]:
        """Obtiene el índice Fear & Greed de CNN."""
        url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        try:
            async with httpx.AsyncClient(timeout=5.0, follow_redirects=True) as client:
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                data = response.json()
                latest = data["fear_and_greed_historical"]["data"][-1]
                return float(latest["y"]), str(latest["rating"])
        except Exception as e:
            logger.debug(f"Error F&G: {e}")
            return None, None

    async def _get_market_snapshot(self) -> dict:
        """Obtiene VIX, SPY (% hoy) y DXY."""
        # Tickers: ^VIX, SPY, DX-Y.NYB
        tickers = ["%5EVIX", "SPY", "DX-Y.NYB"]
        results = {}
        
        headers = {"User-Agent": "Mozilla/5.0"}
        async with httpx.AsyncClient(timeout=5.0) as client:
            for t in tickers:
                try:
                    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{t}"
                    resp = await client.get(url, headers=headers)
                    if resp.status_code == 200:
                        meta = resp.json()["chart"]["result"][0]["meta"]
                        price = meta["regularMarketPrice"]
                        prev_close = meta.get("previousClose", price)
                        change_pct = ((price / prev_close) - 1) * 100 if prev_close else 0
                        results[t] = {"price": price, "change_pct": change_pct}
                except:
                    results[t] = None
        return results

    async def _get_symbol_technicals(self, symbol: str) -> dict:
        """Calcula RSI(14) y EMA(200) para el símbolo."""
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=250d&interval=1d"
        headers = {"User-Agent": "Mozilla/5.0"}
        try:
            async with httpx.AsyncClient(timeout=7.0) as client:
                resp = await client.get(url, headers=headers)
                resp.raise_for_status()
                data = resp.json()["chart"]["result"][0]
                closes = [c for c in data["indicators"]["quote"][0]["close"] if c is not None]
                
                if not closes: return None
                
                current_price = closes[-1]
                ema200 = self._calculate_ema(closes, 200)
                rsi14 = self._calculate_rsi(closes, 14)
                
                dist_ema = ((current_price / ema200) - 1) * 100 if ema200 else None
                
                return {
                    "rsi": rsi14,
                    "ema200": ema200,
                    "dist_ema_pct": dist_ema,
                    "price": current_price
                }
        except Exception as e:
            logger.debug(f"Error technicals {symbol}: {e}")
            return None

    async def send_approval_message(self, signal_id: int, symbol: str, action: str, price: Any) -> Optional[int]:
        """Envía un mensaje detallado con contexto completo del mercado."""
        # 1. Obtener todos los datos en paralelo
        fng_task = asyncio.create_task(self._get_fear_greed_index())
        market_task = asyncio.create_task(self._get_market_snapshot())
        tech_task = asyncio.create_task(self._get_symbol_technicals(symbol))
        
        await asyncio.wait([fng_task, market_task, tech_task], timeout=8.0)
        
        fng_score, fng_rating = fng_task.result() if fng_task.done() else (None, None)
        market = market_task.result() if market_task.done() else {}
        techs = tech_task.result() if tech_task.done() else None

        # ── FORMATEO DE MENSAJE ──
        
        # Sentimiento
        fng_str = f"<b>{fng_score:.0f} - {fng_rating.upper()}</b>" if fng_score else "N/A"
        
        # Mercado Global
        vix = market.get("%5EVIX")
        spy = market.get("SPY")
        dxy = market.get("DX-Y.NYB")
        
        vix_str = f"{vix['price']:.2f}" if vix else "N/A"
        spy_change = f"{spy['change_pct']:+.2f}%" if spy else "N/A"
        dxy_str = f"{dxy['price']:.2f}" if dxy else "N/A"
        
        # Técnicos Símbolo
        rsi_str = f"{techs['rsi']:.1f}" if techs and techs['rsi'] else "N/A"
        ema_dist = f"{techs['dist_ema_pct']:+.2f}%" if techs and techs['dist_ema_pct'] is not None else "N/A"

        text = (
            f"🔔 <b>NUEVA SEÑAL PENDIENTE</b>\n"
            f"<b>Símbolo:</b> {symbol}\n"
            f"<b>Acción:</b> {action.upper()}\n"
            f"<b>Precio:</b> {price if price else 'Mercado'}\n\n"
            
            f"🧠 <b>Sentimiento (Fear & Greed)</b>\n"
            f"Índice: {fng_str}\n\n"
            
            f"🌍 <b>Mercado Global</b>\n"
            f"VIX: <code>{vix_str}</code> | SPY: <code>{spy_change}</code>\n"
            f"DXY (Dólar): <code>{dxy_str}</code>\n\n"
            
            f"📈 <b>Técnicos ({symbol})</b>\n"
            f"RSI (14): <code>{rsi_str}</code>\n"
            f"Dist. EMA 200: <code>{ema_dist}</code>\n\n"
            
            f"¿Deseas ejecutar esta operación?"
        )
        
        reply_markup = {
            "inline_keyboard": [[
                {"text": "✅ Aceptar", "callback_data": f"approve_{signal_id}"},
                {"text": "❌ Rechazar", "callback_data": f"reject_{signal_id}"}
            ]]
        }
        
        return await self.send_message(text, reply_markup=reply_markup)

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
