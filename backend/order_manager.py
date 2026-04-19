"""
Order Manager: orquesta el proceso completo de una señal
desde la validación de riesgo hasta la ejecución en IBKR.
"""
import logging
from typing import Dict, Any

from ibkr_client import ibkr
from risk_manager import risk_manager
from database import save_trade, close_trade, save_signal
from notifier import notifier

logger = logging.getLogger(__name__)


class OrderManager:

    async def process_signal(self, signal: Dict[str, Any]) -> Dict:
        """
        Proceso completo para una señal:
        1. Obtener datos de cuenta
        2. Validar con risk manager
        3. Calcular tamaño + SL/TP automáticos
        4. Ejecutar orden en IBKR
        5. Guardar en base de datos
        """
        action = signal["action"]
        symbol = signal.get("symbol", "")
        result = {"success": False, "message": "", "order": None}

        # ── Acciones especiales ──────────────────────────────────────────────
        if action == "close_all":
            return await self._close_all_positions()

        if action == "cancel_all":
            cancelled = await ibkr.cancel_all_orders()
            return {"success": cancelled, "message": "Órdenes canceladas" if cancelled else "Error al cancelar"}

        if action == "close":
            return await self._close_position(signal)

        # ── Compra / Venta ───────────────────────────────────────────────────
        if action not in ("buy", "sell"):
            return {"success": False, "message": f"Acción desconocida: {action}"}

        side = "BUY" if action == "buy" else "SELL"

        try:
            # 1. Datos de cuenta
            account = await ibkr.get_account_summary()
            account_value = account.get("net_liquidation", 0)
            if account_value <= 0:
                return {"success": False, "message": "No se pudo obtener el capital de la cuenta"}

            # 2. Obtener posiciones actuales
            positions = await ibkr.get_positions()
            open_count = len(positions)

            # 3. Validación de riesgo
            allowed, reason = risk_manager.validate_trade(account_value, open_count, signal)
            if not allowed:
                logger.warning(f"🚫 Trade rechazado: {reason}")
                save_signal(symbol, action, signal, status="rejected", error=reason)
                await notifier.send_message(f"🚫 <b>Trade rechazado</b>\nSímbolo: {symbol}\nMotivo: {reason}")
                return {"success": False, "message": reason}

            # 4. Precio de entrada
            entry_price = signal.get("price")
            if not entry_price:
                entry_price = await ibkr.get_market_price(symbol, signal.get("sec_type", "STK"))
            if not entry_price:
                return {"success": False, "message": f"No se pudo obtener precio de {symbol}"}

            # 5. Calcular Stop Loss y Take Profit
            stop_loss = signal.get("stop_loss") or risk_manager.calculate_stop_loss(entry_price, side)
            take_profit = signal.get("take_profit") or risk_manager.calculate_take_profit(entry_price, side)

            # 6. Calcular tamaño de posición
            qty = signal.get("qty")
            if not qty:
                qty = risk_manager.calculate_position_size(account_value, entry_price, stop_loss)

            logger.info(f"🎯 Ejecutando: {side} {qty} {symbol} @ {entry_price} | SL: {stop_loss} | TP: {take_profit}")

            # 7. Ejecutar bracket order
            order_result = await ibkr.place_bracket_order(
                symbol=symbol,
                side=side,
                qty=qty,
                entry_price=signal.get("price"),  # None = market order
                stop_loss=stop_loss,
                take_profit=take_profit,
                sec_type=signal.get("sec_type", "STK")
            )

            if order_result:
                # 8. Guardar en base de datos
                trade_id = save_trade(
                    symbol=symbol,
                    side=side,
                    qty=qty,
                    entry_price=entry_price,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    ibkr_order_id=order_result["order_id"]
                )
                save_signal(symbol, action, signal, status="executed", order_id=order_result["order_id"])

                result = {
                    "success": True,
                    "message": f"✅ Orden ejecutada: {side} {qty} {symbol}",
                    "order": {**order_result, "trade_id": trade_id, "entry_price": entry_price,
                              "stop_loss": stop_loss, "take_profit": take_profit}
                }
                
                # Notificar a Telegram
                msg = (f"✅ <b>Orden Ejecutada</b>\n"
                       f"Símbolo: {symbol}\n"
                       f"Operación: {side} {qty}\n"
                       f"Precio: {entry_price}\n"
                       f"SL: {stop_loss} | TP: {take_profit}")
                await notifier.send_message(msg)
            else:
                save_signal(symbol, action, signal, status="failed", error="IBKR no respondió")
                result = {"success": False, "message": "Error al colocar la orden en IBKR"}

        except ConnectionError as e:
            msg = f"IBKR no conectado: {e}"
            logger.error(msg)
            save_signal(symbol, action, signal, status="failed", error=msg)
            result = {"success": False, "message": msg}
        except Exception as e:
            msg = f"Error inesperado: {e}"
            logger.error(msg, exc_info=True)
            save_signal(symbol, action, signal, status="failed", error=msg)
            result = {"success": False, "message": msg}
            await notifier.send_message(f"❌ <b>Error en ejecución</b>\nSímbolo: {symbol}\nError: {msg}")

        return result

    async def _close_position(self, signal: Dict) -> Dict:
        symbol = signal.get("symbol")
        try:
            order_result = await ibkr.close_position(symbol, signal.get("sec_type", "STK"))
            save_signal(symbol, "close", signal, status="executed", order_id=order_result.get("order_id"))
            return {"success": True, "message": f"✅ Posición cerrada: {symbol}", "order": order_result}
        except ValueError as e:
            save_signal(symbol, "close", signal, status="rejected", error=str(e))
            return {"success": False, "message": str(e)}
        except Exception as e:
            return {"success": False, "message": f"Error cerrando posición: {e}"}

    async def _close_all_positions(self) -> Dict:
        positions = await ibkr.get_positions()
        if not positions:
            return {"success": True, "message": "No hay posiciones abiertas"}

        closed = []
        errors = []
        for pos in positions:
            try:
                side = "SELL" if pos["side"] == "LONG" else "BUY"
                await ibkr.place_market_order(pos["symbol"], side, pos["qty"])
                closed.append(pos["symbol"])
            except Exception as e:
                errors.append(f"{pos['symbol']}: {e}")

        msg = f"✅ Cerradas: {', '.join(closed)}"
        if errors:
            msg += f" | ❌ Errores: {', '.join(errors)}"
        return {"success": len(errors) == 0, "message": msg, "closed": closed, "errors": errors}


# Instancia global
order_manager = OrderManager()
