"""
Gestión de riesgo Multi-usuario: valida cada señal antes de ejecutar la orden.
"""
import logging
from typing import Optional, Tuple, Dict, Any
import database as db

logger = logging.getLogger(__name__)

class RiskManager:
    def __init__(self, user_id: int):
        self.user_id = user_id
        # Estos valores deberían persistirse en BD o cargarse cada vez
        self._daily_loss = 0.0
        self._daily_trades = 0
        self._winning_trades = 0
        self.bot_enabled = True

    def get_config(self) -> Dict:
        """Carga la configuración de riesgo del usuario desde la base de datos."""
        return db.get_risk_config(self.user_id)

    def calculate_position_size(self, account_value: float, entry_price: float,
                                 stop_loss_price: Optional[float] = None) -> int:
        cfg = self.get_config()
        risk_pct = cfg.get("risk_per_trade_pct", 1.0) / 100
        max_pos_pct = cfg.get("max_position_size_pct", 20.0) / 100

        if stop_loss_price and abs(entry_price - stop_loss_price) > 0:
            risk_per_share = abs(entry_price - stop_loss_price)
            risk_capital = account_value * risk_pct
            qty = risk_capital / risk_per_share
        else:
            max_capital = account_value * max_pos_pct
            qty = max_capital / entry_price

        max_by_size = (account_value * max_pos_pct) / entry_price
        qty = min(qty, max_by_size)
        qty = max(1, int(qty))
        return qty

    def calculate_stop_loss(self, entry_price: float, side: str, custom_pct: float = None) -> float:
        cfg = self.get_config()
        sl_pct = (custom_pct or cfg.get("default_stop_loss_pct", 2.0)) / 100
        if side.upper() == "BUY":
            return round(entry_price * (1 - sl_pct), 4)
        else:
            return round(entry_price * (1 + sl_pct), 4)

    def calculate_take_profit(self, entry_price: float, side: str, custom_pct: float = None) -> float:
        cfg = self.get_config()
        tp_pct = (custom_pct or cfg.get("default_take_profit_pct", 4.0)) / 100
        if side.upper() == "BUY":
            return round(entry_price * (1 + tp_pct), 4)
        else:
            return round(entry_price * (1 - tp_pct), 4)

    def validate_trade(self, account_value: float, open_positions: int,
                       action: str) -> Tuple[bool, str]:
        cfg = self.get_config()

        if not self.bot_enabled:
            return False, "🔴 Bot deshabilitado"

        max_daily_loss = account_value * cfg.get("max_daily_loss_pct", 5.0) / 100
        if self._daily_loss >= max_daily_loss:
            return False, f"🛑 Límite de pérdida diaria alcanzado"

        max_positions = cfg.get("max_open_positions", 5)
        if action == "buy" and open_positions >= max_positions:
            return False, f"🛑 Máximo de posiciones abierto ({open_positions}/{max_positions})"

        return True, "OK"

    def register_trade_result(self, pnl: float):
        self._daily_trades += 1
        if pnl < 0:
            self._daily_loss += abs(pnl)
        else:
            self._winning_trades += 1

    @property
    def daily_stats(self) -> Dict:
        wr = (self._winning_trades / self._daily_trades * 100) if self._daily_trades > 0 else 0
        return {
            "daily_loss": round(self._daily_loss, 2),
            "daily_trades": self._daily_trades,
            "winning_trades": self._winning_trades,
            "win_rate": round(wr, 1),
            "bot_enabled": self.bot_enabled,
        }
