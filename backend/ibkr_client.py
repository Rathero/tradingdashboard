"""
Cliente de Interactive Brokers usando ib_insync.
Gestiona la conexión, reconexión automática y datos de cuenta/posiciones.
"""
import asyncio
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime

from ib_insync import IB, Stock, Forex, Future, Option, Crypto, Contract, Order, MarketOrder, LimitOrder, StopOrder

import config

logger = logging.getLogger(__name__)


class IBKRClient:
    def __init__(self):
        self.ib = None
        self.connected = False
        self._reconnect_task = None
        self._account_id = None

    # ─── Conexión ──────────────────────────────────────────────────────────────

    async def connect(self):
        """Conecta a TWS o IB Gateway."""
        if self.ib is None:
            self.ib = IB()
            # Suscribir a eventos
            self.ib.disconnectedEvent += self._on_disconnected
            self.ib.errorEvent += self._on_error

        try:
            await self.ib.connectAsync(
                host=config.IBKR_HOST,
                port=config.IBKR_PORT,
                clientId=config.IBKR_CLIENT_ID,
                timeout=20
            )
            self.connected = True
            accounts = self.ib.managedAccounts()
            self._account_id = accounts[0] if accounts else None

            mode = "📄 PAPER TRADING" if config.PAPER_TRADING else "💸 REAL TRADING"
            logger.info(f"✅ Conectado a IBKR {mode} | Cuenta: {self._account_id} | Puerto: {config.IBKR_PORT}")
            return True

        except Exception as e:
            self.connected = False
            logger.error(f"❌ Error de conexión IBKR: {e}")
            return False

    def disconnect(self):
        if self.connected:
            self.ib.disconnect()
            self.connected = False
            logger.info("🔌 Desconectado de IBKR")

    def _on_disconnected(self):
        self.connected = False
        logger.warning("⚠️ Desconectado de IBKR. Intentando reconectar...")
        asyncio.create_task(self._reconnect())

    def _on_error(self, req_id, error_code, error_string, contract):
        # Ignorar errores informativos comunes (data farms, conexiones secundarias)
        if error_code in (2103, 2104, 2105, 2106, 2107, 2108, 2158, 2119):
            return
        # 10167: aviso de datos diferidos activos (informativo, el fallback funciona)
        # 10168: sin suscripción (manejado con fallback)
        # 300: tickerId no encontrado al cancelar (consecuencia de 10168, inofensivo)
        if error_code in (10167, 10168, 300):
            return
        logger.error(f"IBKR Error [{error_code}]: {error_string} | ReqID: {req_id}")

    async def _reconnect(self, max_attempts: int = 10, delay: int = 5):
        for attempt in range(1, max_attempts + 1):
            logger.info(f"🔄 Intento de reconexión {attempt}/{max_attempts}...")
            await asyncio.sleep(delay)
            success = await self.connect()
            if success:
                logger.info("✅ Reconexión exitosa")
                return
        logger.error("❌ No se pudo reconectar después de múltiples intentos")

    def is_connected(self) -> bool:
        return self.connected and self.ib is not None and self.ib.isConnected()

    # ─── Contratos ─────────────────────────────────────────────────────────────

    def _get_contract(self, symbol: str, sec_type: str = "STK", exchange: str = "SMART", currency: str = "USD") -> Contract:
        """Crea un contrato IBKR a partir de los parámetros."""
        if sec_type == "STK":
            return Stock(symbol, exchange, currency)
        elif sec_type == "CASH":
            base, quote = symbol[:3], symbol[3:]
            return Forex(f"{base}{quote}")
        elif sec_type == "FUT":
            return Future(symbol, exchange=exchange, currency=currency)
        elif sec_type == "CRYPTO":
            return Crypto(symbol, exchange, currency)
        else:
            return Stock(symbol, exchange, currency)

    async def qualify_contract(self, contract: Contract) -> Optional[Contract]:
        """Valida y completa los datos del contrato."""
        try:
            qualified = await self.ib.qualifyContractsAsync(contract)
            return qualified[0] if qualified else None
        except Exception as e:
            logger.error(f"Error al cualificar contrato {contract}: {e}")
            return None

    # ─── Cuenta ────────────────────────────────────────────────────────────────

    async def get_account_summary(self) -> Dict[str, Any]:
        """Devuelve resumen de la cuenta: balance, buying power, margin, etc."""
        if not self.is_connected():
            return {}
        try:
            summary = await self.ib.accountSummaryAsync(self._account_id)
            result = {}
            for item in summary:
                result[item.tag] = {
                    "value": item.value,
                    "currency": item.currency
                }
            return {
                "account_id": self._account_id,
                "net_liquidation": float(result.get("NetLiquidation", {}).get("value", 0)),
                "buying_power": float(result.get("BuyingPower", {}).get("value", 0)),
                "cash_balance": float(result.get("TotalCashValue", {}).get("value", 0)),
                "unrealized_pnl": float(result.get("UnrealizedPnL", {}).get("value", 0)),
                "realized_pnl": float(result.get("RealizedPnL", {}).get("value", 0)),
                "currency": result.get("NetLiquidation", {}).get("currency", "USD"),
                "available_funds": float(result.get("AvailableFunds", {}).get("value", 0)),
                "maintenance_margin": float(result.get("MaintMarginReq", {}).get("value", 0)),
            }
        except Exception as e:
            logger.error(f"Error obteniendo resumen de cuenta: {e}")
            return {}

    # ─── Posiciones ────────────────────────────────────────────────────────────

    async def get_positions(self) -> List[Dict[str, Any]]:
        """Devuelve todas las posiciones abiertas."""
        if not self.is_connected():
            return []
        try:
            positions = await self.ib.reqPositionsAsync()
            result = []
            for pos in positions:
                if pos.position == 0:
                    continue
                market_price = await self._get_price_with_fallback(pos.contract)
                avg_cost = pos.avgCost or 0
                unrealized_pnl = (market_price - avg_cost) * pos.position if market_price > 0 else 0

                result.append({
                    "symbol": pos.contract.symbol,
                    "sec_type": pos.contract.secType,
                    "side": "LONG" if pos.position > 0 else "SHORT",
                    "qty": abs(pos.position),
                    "avg_cost": round(avg_cost, 4),
                    "market_price": round(market_price, 4),
                    "unrealized_pnl": round(unrealized_pnl, 2),
                    "pnl_pct": round(((market_price - avg_cost) / avg_cost * 100) if avg_cost > 0 and market_price > 0 else 0, 2),
                    "account": pos.account,
                })
            return result
        except Exception as e:
            logger.error(f"Error obteniendo posiciones: {e}")
            return []

    # ─── Órdenes ───────────────────────────────────────────────────────────────

    async def get_open_orders(self) -> List[Dict[str, Any]]:
        """Devuelve las órdenes abiertas/pendientes."""
        if not self.is_connected():
            return []
        try:
            orders = await self.ib.reqOpenOrdersAsync()
            result = []
            for trade in orders:
                result.append({
                    "order_id": str(trade.order.orderId),
                    "symbol": trade.contract.symbol,
                    "side": trade.order.action,
                    "order_type": trade.order.orderType,
                    "qty": trade.order.totalQuantity,
                    "limit_price": trade.order.lmtPrice,
                    "stop_price": trade.order.auxPrice,
                    "status": trade.orderStatus.status,
                    "filled": trade.orderStatus.filled,
                    "remaining": trade.orderStatus.remaining,
                })
            return result
        except Exception as e:
            logger.error(f"Error obteniendo órdenes: {e}")
            return []

    # ─── Precio actual ─────────────────────────────────────────────────────────

    async def _get_price_with_fallback(self, contract: Contract) -> float:
        """
        Intenta obtener el precio de mercado usando datos diferidos (gratuitos, ~15 min retraso).
        Si falla, busca el último precio de cierre en el historial.
        """
        symbol = contract.symbol
        try:
            # Solicitar datos diferidos (tipo 3 = delayed, tipo 1 = live)
            self.ib.reqMarketDataType(3)
            ticker = self.ib.reqMktData(contract, "", False, False)
            await asyncio.sleep(2)
            price = ticker.last or ticker.close or ticker.bid or ticker.ask
            self.ib.cancelMktData(contract)
            self.ib.reqMarketDataType(1)  # restaurar modo live
            if price and price > 0:
                return float(price)
        except Exception as e:
            logger.debug(f"Datos diferidos no disponibles para {symbol}: {e}")

        # Fallback: último cierre del historial (no requiere suscripción)
        try:
            bars = await self.ib.reqHistoricalDataAsync(
                contract,
                endDateTime="",
                durationStr="2 D",
                barSizeSetting="1 day",
                whatToShow="TRADES",
                useRTH=True,
                formatDate=1,
            )
            if bars:
                price = bars[-1].close
                logger.debug(f"Precio histórico para {symbol}: {price} (cierre anterior)")
                return float(price) if price and price > 0 else 0.0
        except Exception as e:
            logger.debug(f"Datos históricos no disponibles para {symbol}: {e}")

        return 0.0

    async def get_market_price(self, symbol: str, sec_type: str = "STK") -> Optional[float]:
        """Obtiene el precio de mercado actual de un símbolo."""
        if not self.is_connected():
            return None
        try:
            contract = self._get_contract(symbol, sec_type)
            qualified = await self.qualify_contract(contract)
            if not qualified:
                return None
            price = await self._get_price_with_fallback(qualified)
            return float(price) if price and price > 0 else None
        except Exception as e:
            logger.error(f"Error obteniendo precio de {symbol}: {e}")
            return None

    # ─── Ejecutar órdenes ──────────────────────────────────────────────────────

    async def place_market_order(self, symbol: str, side: str, qty: float, sec_type: str = "STK") -> Optional[Dict]:
        """Coloca una orden a mercado."""
        if not self.is_connected():
            raise ConnectionError("No conectado a IBKR")

        contract = self._get_contract(symbol, sec_type)
        qualified = await self.qualify_contract(contract)
        if not qualified:
            raise ValueError(f"Contrato no encontrado: {symbol}")

        order = MarketOrder(side.upper(), qty)
        trade = self.ib.placeOrder(qualified, order)
        await asyncio.sleep(1)

        logger.info(f"📈 Orden a mercado colocada: {side} {qty} {symbol} | ID: {trade.order.orderId}")
        return {
            "order_id": str(trade.order.orderId),
            "symbol": symbol,
            "side": side,
            "qty": qty,
            "order_type": "MARKET",
            "status": trade.orderStatus.status
        }

    async def place_bracket_order(self, symbol: str, side: str, qty: float,
                                   entry_price: float = None,
                                   stop_loss: float = None,
                                   take_profit: float = None,
                                   sec_type: str = "STK") -> Optional[Dict]:
        """Coloca una bracket order (entrada + stop loss + take profit)."""
        if not self.is_connected():
            raise ConnectionError("No conectado a IBKR")

        contract = self._get_contract(symbol, sec_type)
        qualified = await self.qualify_contract(contract)
        if not qualified:
            raise ValueError(f"Contrato no encontrado: {symbol}")

        close_side = "SELL" if side.upper() == "BUY" else "BUY"

        # Orden principal
        if entry_price:
            parent_order = LimitOrder(side.upper(), qty, entry_price)
        else:
            parent_order = MarketOrder(side.upper(), qty)

        parent_order.transmit = False
        child_orders = []

        # Stop Loss
        if stop_loss:
            sl_order = StopOrder(close_side, qty, stop_loss)
            sl_order.parentId = parent_order.orderId
            sl_order.transmit = not bool(take_profit)
            child_orders.append(sl_order)

        # Take Profit
        if take_profit:
            tp_order = LimitOrder(close_side, qty, take_profit)
            tp_order.parentId = parent_order.orderId
            tp_order.transmit = True
            child_orders.append(tp_order)
        else:
            if child_orders:
                child_orders[-1].transmit = True
            else:
                parent_order.transmit = True

        parent_trade = self.ib.placeOrder(qualified, parent_order)
        for child_order in child_orders:
            self.ib.placeOrder(qualified, child_order)

        await asyncio.sleep(1)
        logger.info(f"📊 Bracket order: {side} {qty} {symbol} | SL: {stop_loss} | TP: {take_profit} | ID: {parent_order.orderId}")

        return {
            "order_id": str(parent_order.orderId),
            "symbol": symbol,
            "side": side,
            "qty": qty,
            "order_type": "BRACKET",
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "status": parent_trade.orderStatus.status
        }

    async def close_position(self, symbol: str, sec_type: str = "STK") -> Optional[Dict]:
        """Cierra la posición abierta de un símbolo."""
        positions = await self.get_positions()
        pos = next((p for p in positions if p["symbol"] == symbol), None)

        if not pos:
            raise ValueError(f"No hay posición abierta en {symbol}")

        side = "SELL" if pos["side"] == "LONG" else "BUY"
        return await self.place_market_order(symbol, side, pos["qty"], sec_type)

    async def cancel_all_orders(self) -> bool:
        """Cancela todas las órdenes pendientes."""
        if not self.is_connected():
            return False
        try:
            self.ib.reqGlobalCancel()
            logger.info("🚫 Todas las órdenes canceladas")
            return True
        except Exception as e:
            logger.error(f"Error cancelando órdenes: {e}")
            return False


# Instancia global
ibkr = IBKRClient()
