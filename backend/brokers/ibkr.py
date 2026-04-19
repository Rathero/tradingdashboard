import asyncio
import logging
from typing import Optional, List, Dict, Any
from ib_insync import IB, Stock, Forex, Future, Crypto, Contract, MarketOrder, LimitOrder, StopOrder
from .base import BaseBroker

logger = logging.getLogger(__name__)

class IBKRBroker(BaseBroker):
    def __init__(self, host: str, port: int, client_id: int):
        self.host = host
        self.port = port
        self.client_id = client_id
        self.ib = IB()
        self.connected = False
        self._account_id = None

    async def connect(self) -> bool:
        """Conecta a TWS o IB Gateway."""
        try:
            await self.ib.connectAsync(
                host=self.host,
                port=self.port,
                clientId=self.client_id,
                timeout=20
            )
            self.connected = True
            accounts = self.ib.managedAccounts()
            self._account_id = accounts[0] if accounts else None

            # Suscribir a eventos
            self.ib.disconnectedEvent += self._on_disconnected
            self.ib.errorEvent += self._on_error

            logger.info(f"✅ IBKR Conectado | Cuenta: {self._account_id} | Puerto: {self.port}")
            return True
        except Exception as e:
            self.connected = False
            logger.error(f"❌ Error de conexión IBKR ({self.port}): {e}")
            return False

    def disconnect(self):
        if self.connected:
            self.ib.disconnect()
            self.connected = False
            logger.info(f"🔌 IBKR Desconectado ({self.port})")

    def is_connected(self) -> bool:
        return self.connected and self.ib.isConnected()

    def _on_disconnected(self):
        self.connected = False
        logger.warning(f"⚠️ IBKR Desconectado ({self.port}).")

    def _on_error(self, req_id, error_code, error_string, contract):
        if error_code in (2103, 2104, 2105, 2106, 2107, 2108, 2158, 2119, 10167, 10168, 300):
            return
        logger.error(f"IBKR Error [{error_code}] en puerto {self.port}: {error_string}")

    # ─── Contratos ─────────────────────────────────────────────────────────────

    def _get_contract(self, symbol: str, sec_type: str = "STK", exchange: str = "SMART", currency: str = "USD") -> Contract:
        if sec_type == "STK":
            return Stock(symbol, exchange, currency)
        elif sec_type == "CASH":
            base, quote = symbol[:3], symbol[3:]
            return Forex(f"{base}{quote}")
        elif sec_type == "FUT":
            return Future(symbol, exchange=exchange, currency=currency)
        elif sec_type == "CRYPTO":
            return Crypto(symbol, exchange, currency)
        return Stock(symbol, exchange, currency)

    async def qualify_contract(self, contract: Contract) -> Optional[Contract]:
        try:
            qualified = await self.ib.qualifyContractsAsync(contract)
            return qualified[0] if qualified else None
        except:
            return None

    # ─── Cuenta y Posiciones ───────────────────────────────────────────────────

    async def get_account_summary(self) -> Dict[str, Any]:
        if not self.is_connected():
            return {}
        try:
            summary = await self.ib.accountSummaryAsync(self._account_id)
            result = {item.tag: {"value": item.value, "currency": item.currency} for item in summary}
            return {
                "account_id": self._account_id,
                "net_liquidation": float(result.get("NetLiquidation", {}).get("value", 0)),
                "buying_power": float(result.get("BuyingPower", {}).get("value", 0)),
                "cash_balance": float(result.get("TotalCashValue", {}).get("value", 0)),
                "unrealized_pnl": float(result.get("UnrealizedPnL", {}).get("value", 0)),
                "realized_pnl": float(result.get("RealizedPnL", {}).get("value", 0)),
                "currency": result.get("NetLiquidation", {}).get("currency", "USD"),
            }
        except Exception as e:
            logger.error(f"Error account summary: {e}")
            return {}

    async def get_positions(self) -> List[Dict[str, Any]]:
        if not self.is_connected():
            return []
        try:
            positions = await self.ib.reqPositionsAsync()
            result = []
            for pos in positions:
                if pos.position == 0: continue
                price = await self.get_market_price(pos.contract.symbol, pos.contract.secType) or 0
                avg_cost = pos.avgCost or 0
                unrealized = (price - avg_cost) * pos.position if price > 0 else 0
                result.append({
                    "symbol": pos.contract.symbol,
                    "sec_type": pos.contract.secType,
                    "side": "LONG" if pos.position > 0 else "SHORT",
                    "qty": abs(pos.position),
                    "avg_cost": round(avg_cost, 4),
                    "market_price": round(price, 4),
                    "unrealized_pnl": round(unrealized, 2),
                })
            return result
        except Exception as e:
            logger.error(f"Error positions: {e}")
            return []

    async def get_market_price(self, symbol: str, sec_type: str = "STK") -> Optional[float]:
        if not self.is_connected(): return None
        try:
            contract = self._get_contract(symbol, sec_type)
            qualified = await self.qualify_contract(contract)
            if not qualified: return None
            self.ib.reqMarketDataType(3)  # Delayed data
            ticker = self.ib.reqMktData(qualified, "", False, False)
            await asyncio.sleep(1.5)
            price = ticker.last or ticker.close or ticker.bid or ticker.ask
            self.ib.cancelMktData(qualified)
            return float(price) if price and price > 0 else None
        except:
            return None

    # ─── Órdenes ───────────────────────────────────────────────────────────────

    async def place_market_order(self, symbol: str, side: str, qty: float, sec_type: str = "STK") -> Optional[Dict]:
        if not self.is_connected(): raise ConnectionError("IBKR no conectado")
        contract = await self.qualify_contract(self._get_contract(symbol, sec_type))
        if not contract: raise ValueError(f"Contrato inválido: {symbol}")
        
        order = MarketOrder(side.upper(), qty)
        trade = self.ib.placeOrder(contract, order)
        return {"order_id": str(trade.order.orderId), "status": "submitted"}

    async def place_bracket_order(self, symbol: str, side: str, qty: float,
                                   entry_price: float = None,
                                   stop_loss: float = None,
                                   take_profit: float = None,
                                   sec_type: str = "STK") -> Optional[Dict]:
        if not self.is_connected(): raise ConnectionError("IBKR no conectado")
        contract = await self.qualify_contract(self._get_contract(symbol, sec_type))
        if not contract: raise ValueError(f"Contrato inválido: {symbol}")

        parent = LimitOrder(side.upper(), qty, entry_price) if entry_price else MarketOrder(side.upper(), qty)
        parent.transmit = False
        
        close_side = "SELL" if side.upper() == "BUY" else "BUY"
        orders = [parent]
        
        if stop_loss:
            sl = StopOrder(close_side, qty, stop_loss)
            sl.parentId = parent.orderId
            sl.transmit = not bool(take_profit)
            orders.append(sl)
            
        if take_profit:
            tp = LimitOrder(close_side, qty, take_profit)
            tp.parentId = parent.orderId
            tp.transmit = True
            orders.append(tp)

        for o in orders:
            self.ib.placeOrder(contract, o)
            
        return {"order_id": str(parent.orderId), "status": "submitted"}

    async def cancel_all_orders(self) -> bool:
        if not self.is_connected(): return False
        self.ib.reqGlobalCancel()
        return True

    async def close_position(self, symbol: str, sec_type: str = "STK") -> Optional[Dict]:
        positions = await self.get_positions()
        pos = next((p for p in positions if p["symbol"] == symbol), None)
        if not pos: return None
        side = "SELL" if pos["side"] == "LONG" else "BUY"
        return await self.place_market_order(symbol, side, pos["qty"], sec_type)
