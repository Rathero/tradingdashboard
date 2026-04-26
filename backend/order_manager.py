import logging
from typing import Dict, Any, Optional
import database as db
from risk_manager import RiskManager

logger = logging.getLogger(__name__)

class OrderManager:
    def __init__(self, user_id: int, broker: Any, notifier: Any, risk_manager: RiskManager):
        self.user_id = user_id
        self.broker = broker
        self.notifier = notifier
        self.risk_manager = risk_manager

    async def process_signal(self, signal: Dict[str, Any]) -> Dict:
        """Procesa una señal para un usuario específico."""
        action = signal["action"]
        symbol = signal.get("symbol", "")
        
        # ── Acciones Globales ────────────────────────────────────────────────
        if action == "close_all":
            return await self._close_all_positions()
        if action == "cancel_all":
            success = await self.broker.cancel_all_orders()
            return {"success": success, "message": "Órdenes canceladas" if success else "Error"}
        if action == "close":
            return await self._close_position(signal)

        # ── Apertura de Posiciones ──────────────────────────────────────────
        side = "BUY" if action == "buy" else "SELL"
        
        try:
            # 1. Capital de la cuenta
            account = await self.broker.get_account_summary()
            account_value = account.get("net_liquidation", 0)
            if account_value <= 0:
                return {"success": False, "message": "Capital de cuenta no disponible"}

            # 2. Posiciones abiertas
            positions = await self.broker.get_positions()
            
            # 3. Validar Riesgo
            allowed, reason = self.risk_manager.validate_trade(account_value, len(positions), action)
            if not allowed:
                db.save_signal(self.user_id, symbol, action, signal, status="rejected", error=reason)
                await self.notifier.send_message(f"🚫 <b>Trade rechazado</b> ({symbol}): {reason}")
                return {"success": False, "message": reason}

            # 4. Precio de entrada (si no viene en la señal)
            entry_price = signal.get("price") or await self.broker.get_market_price(symbol, signal.get("sec_type", "STK"))
            if not entry_price:
                return {"success": False, "message": "No se pudo obtener precio de mercado"}

            # 5. Parámetros de la orden
            stop_loss = signal.get("stop_loss") or self.risk_manager.calculate_stop_loss(entry_price, side)
            take_profit = signal.get("take_profit") or self.risk_manager.calculate_take_profit(entry_price, side)
            qty = signal.get("qty") or self.risk_manager.calculate_position_size(account_value, entry_price, stop_loss)

            # 6. Ejecución
            order_res = await self.broker.place_bracket_order(
                symbol=symbol, side=side, qty=qty,
                entry_price=signal.get("price"),
                stop_loss=stop_loss, take_profit=take_profit,
                sec_type=signal.get("sec_type", "STK")
            )

            if order_res:
                db.save_trade(self.user_id, symbol, side, qty, entry_price, stop_loss, take_profit, order_res["order_id"])
                db.save_signal(self.user_id, symbol, action, signal, status="executed", order_id=order_res["order_id"])
                
                await self.notifier.send_message(
                    f"✅ <b>Orden Ejecutada</b>\n{symbol}: {side} {qty} @ {entry_price}\nSL: {stop_loss} | TP: {take_profit}"
                )
                return {"success": True, "message": f"Orden enviada: {symbol}", "order": order_res}
            
            return {"success": False, "message": "El broker rechazó la orden"}

        except Exception as e:
            logger.error(f"Error en OrderManager de usuario {self.user_id}: {e}")
            return {"success": False, "message": str(e)}

    async def _close_position(self, signal: Dict) -> Dict:
        symbol = signal.get("symbol")
        res = await self.broker.close_position(symbol, signal.get("sec_type", "STK"))
        if res:
            db.save_signal(self.user_id, "close", signal, status="executed", order_id=res.get("order_id"))
            return {"success": True, "message": f"Cerrando {symbol}"}
        return {"success": False, "message": f"No hay posición en {symbol}"}

    async def _close_all_positions(self) -> Dict:
        positions = await self.broker.get_positions()
        for pos in positions:
            await self.broker.close_position(pos["symbol"], pos["sec_type"])
        return {"success": True, "message": "Cerrando todas las posiciones..."}
