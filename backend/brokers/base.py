from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any

class BaseBroker(ABC):
    @abstractmethod
    async def connect(self) -> bool:
        """Establece la conexión con el broker."""
        pass

    @abstractmethod
    def disconnect(self):
        """Cierra la conexión con el broker."""
        pass

    @abstractmethod
    def is_connected(self) -> bool:
        """Verifica si la conexión está activa."""
        pass

    @abstractmethod
    async def get_account_summary(self) -> Dict[str, Any]:
        """Obtiene el resumen de la cuenta (balance, equidad, etc.)."""
        pass

    @abstractmethod
    async def get_positions(self) -> List[Dict[str, Any]]:
        """Obtiene las posiciones abiertas actuales."""
        pass

    @abstractmethod
    async def get_market_price(self, symbol: str, sec_type: str = "STK") -> Optional[float]:
        """Obtiene el precio de mercado actual de un activo."""
        pass

    @abstractmethod
    async def place_bracket_order(self, symbol: str, side: str, qty: float,
                                   entry_price: float = None,
                                   stop_loss: float = None,
                                   take_profit: float = None,
                                   sec_type: str = "STK") -> Optional[Dict[str, Any]]:
        """Coloca una orden bracket (entrada + SL + TP)."""
        pass

    @abstractmethod
    async def cancel_all_orders(self) -> bool:
        """Cancela todas las órdenes pendientes."""
        pass

    @abstractmethod
    async def close_position(self, symbol: str, sec_type: str = "STK") -> Optional[Dict[str, Any]]:
        """Cierra la posición abierta de un símbolo."""
        pass

    @abstractmethod
    async def place_market_order(self, symbol: str, side: str, qty: float, sec_type: str = "STK") -> Optional[Dict[str, Any]]:
        """Coloca una orden a mercado."""
        pass
