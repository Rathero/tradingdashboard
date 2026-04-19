import logging
import asyncio
from typing import Optional, List, Dict, Any
import alpaca_trade_api as tradeapi
from .base import BaseBroker

logger = logging.getLogger(__name__)

class AlpacaBroker(BaseBroker):
    def __init__(self, api_key: str, secret_key: str, paper: bool = True):
        self.api_key = api_key
        self.secret_key = secret_key
        self.base_url = "https://paper-api.alpaca.markets" if paper else "https://api.alpaca.markets"
        self.api = None
        self.connected = False

    async def connect(self) -> bool:
        """Inicializa la conexión con Alpaca."""
        try:
            self.api = tradeapi.REST(self.api_key, self.secret_key, self.base_url, api_version='v2')
            # Verificar conexión obteniendo cuenta
            self.api.get_account()
            self.connected = True
            logger.info(f"✅ Alpaca Conectado (API Key: {self.api_key[:5]}...)")
            return True
        except Exception as e:
            self.connected = False
            logger.error(f"❌ Error de conexión Alpaca: {e}")
            return False

    def disconnect(self):
        self.connected = False
        self.api = None
        logger.info("🔌 Alpaca Desconectado")

    def is_connected(self) -> bool:
        return self.connected and self.api is not None

    async def get_account_summary(self) -> Dict[str, Any]:
        if not self.is_connected(): return {}
        try:
            acc = self.api.get_account()
            return {
                "account_id": acc.id,
                "net_liquidation": float(acc.equity),
                "buying_power": float(acc.buying_power),
                "cash_balance": float(acc.cash),
                "unrealized_pnl": float(acc.unrealized_intraday_pl),
                "realized_pnl": float(acc.long_market_value) - float(acc.cash), # Simplificado
                "currency": "USD",
            }
        except Exception as e:
            logger.error(f"Error Alpaca account: {e}")
            return {}

    async def get_positions(self) -> List[Dict[str, Any]]:
        if not self.is_connected(): return []
        try:
            positions = self.api.list_positions()
            result = []
            for pos in positions:
                result.append({
                    "symbol": pos.symbol,
                    "sec_type": "STK", # Alpaca es mayormente STK y CRYPTO
                    "side": "LONG" if pos.side == "long" else "SHORT",
                    "qty": abs(float(pos.qty)),
                    "avg_cost": float(pos.avg_entry_price),
                    "market_price": float(pos.current_price),
                    "unrealized_pnl": float(pos.unrealized_pl),
                })
            return result
        except Exception as e:
            logger.error(f"Error Alpaca positions: {e}")
            return []

    async def get_market_price(self, symbol: str, sec_type: str = "STK") -> Optional[float]:
        if not self.is_connected(): return None
        try:
            # Obtener último trade
            trade = self.api.get_latest_trade(symbol)
            return float(trade.p)
        except:
            return None

    async def place_market_order(self, symbol: str, side: str, qty: float, sec_type: str = "STK") -> Optional[Dict]:
        if not self.is_connected(): raise ConnectionError("Alpaca no conectado")
        try:
            order = self.api.submit_order(
                symbol=symbol,
                qty=qty,
                side=side.lower(),
                type='market',
                time_in_force='gtc'
            )
            return {"order_id": order.id, "status": order.status}
        except Exception as e:
            logger.error(f"Error Alpaca market order: {e}")
            return None

    async def place_bracket_order(self, symbol: str, side: str, qty: float,
                                   entry_price: float = None,
                                   stop_loss: float = None,
                                   take_profit: float = None,
                                   sec_type: str = "STK") -> Optional[Dict]:
        if not self.is_connected(): raise ConnectionError("Alpaca no conectado")
        try:
            order_params = {
                "symbol": symbol,
                "qty": qty,
                "side": side.lower(),
                "type": 'limit' if entry_price else 'market',
                "time_in_force": 'gtc',
                "order_class": 'bracket' if (stop_loss or take_profit) else 'simple'
            }
            if entry_price:
                order_params["limit_price"] = entry_price
            
            if stop_loss or take_profit:
                order_params["stop_loss"] = {"stop_price": stop_loss} if stop_loss else None
                order_params["take_profit"] = {"limit_price": take_profit} if take_profit else None

            order = self.api.submit_order(**order_params)
            return {"order_id": order.id, "status": order.status}
        except Exception as e:
            logger.error(f"Error Alpaca bracket order: {e}")
            return None

    async def cancel_all_orders(self) -> bool:
        if not self.is_connected(): return False
        self.api.cancel_all_orders()
        return True

    async def close_position(self, symbol: str, sec_type: str = "STK") -> Optional[Dict]:
        if not self.is_connected(): return None
        try:
            self.api.close_position(symbol)
            return {"symbol": symbol, "status": "closed"}
        except:
            return None
