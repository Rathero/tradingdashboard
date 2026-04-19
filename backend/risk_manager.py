"""
Gestión de riesgo: valida cada señal antes de ejecutar la orden.
Calcula tamaños de posición, verifica límites de pérdida y posiciones.
"""
import logging
from typing import Optional, Tuple, Dict, Any

import config
from database import get_risk_config

logger = logging.getLogger(__name__)


class RiskManager:
    def __init__(self):
        self._daily_loss = 0.0
        self._daily_trades = 0
        self._winning_trades = 0
        self.bot_enabled = True

    def reload_config(self) -> Dict:
        """Carga la configuración de riesgo desde la base de datos."""
        cfg = get_risk_config()
        return cfg if cfg else {
            "risk_per_trade_pct": config.RISK_PER_TRADE_PCT,
            "max_daily_loss_pct": config.MAX_DAILY_LOSS_PCT,
            "max_open_positions": config.MAX_OPEN_POSITIONS,
            "default_stop_loss_pct": config.DEFAULT_STOP_LOSS_PCT,
            "default_take_profit_pct": config.DEFAULT_TAKE_PROFIT_PCT,
            "max_position_size_pct": config.MAX_POSITION_SIZE_PCT,
        }

    def calculate_position_size(self, account_value: float, entry_price: float,
                                 stop_loss_price: Optional[float] = None) -> int:
        """
        Calcula el número de acciones a comprar basándose en el riesgo por trade.

        Si hay stop loss: qty = (capital * riesgo%) / (entry - stop_loss)
        Si no hay stop: qty = (capital * max_pos_size%) / entry_price
        """
        cfg = self.reload_config()
        risk_pct = cfg.get("risk_per_trade_pct", 1.0) / 100
        max_pos_pct = cfg.get("max_position_size_pct", 20.0) / 100

        if stop_loss_price and abs(entry_price - stop_loss_price) > 0:
            risk_per_share = abs(entry_price - stop_loss_price)
            risk_capital = account_value * risk_pct
            qty = risk_capital / risk_per_share
        else:
            # Sin stop loss: usar % máximo de capital para esta posición
            max_capital = account_value * max_pos_pct
            qty = max_capital / entry_price

        # Limitar también por max_position_size_pct
        max_by_size = (account_value * max_pos_pct) / entry_price
        qty = min(qty, max_by_size)
        qty = max(1, int(qty))

        logger.info(f"📐 Tamaño calculado: {qty} acciones | Capital: ${account_value:.0f} | Riesgo: {risk_pct*100:.1f}%")
        return qty

    def calculate_stop_loss(self, entry_price: float, side: str, custom_pct: float = None) -> float:
        """Calcula el precio de stop loss automático."""
        cfg = self.reload_config()
        sl_pct = (custom_pct or cfg.get("default_stop_loss_pct", 2.0)) / 100
        if side.upper() == "BUY":
            return round(entry_price * (1 - sl_pct), 4)
        else:
            return round(entry_price * (1 + sl_pct), 4)

    def calculate_take_profit(self, entry_price: float, side: str, custom_pct: float = None) -> float:
        """Calcula el precio de take profit automático."""
        cfg = self.reload_config()
        tp_pct = (custom_pct or cfg.get("default_take_profit_pct", 4.0)) / 100
        if side.upper() == "BUY":
            return round(entry_price * (1 + tp_pct), 4)
        else:
            return round(entry_price * (1 - tp_pct), 4)

    def validate_trade(self, account_value: float, open_positions: int,
                       signal: dict) -> Tuple[bool, str]:
        """
        Valida si se puede ejecutar el trade según las reglas de riesgo.
        Devuelve (permitido: bool, motivo: str)
        """
        cfg = self.reload_config()

        # 1. ¿El bot está habilitado?
        if not self.bot_enabled:
            return False, "🔴 Bot deshabilitado manualmente"

        # 2. Max pérdida diaria alcanzada
        max_daily_loss = account_value * cfg.get("max_daily_loss_pct", 5.0) / 100
        if self._daily_loss >= max_daily_loss:
            return False, f"🛑 Límite de pérdida diaria alcanzado (${self._daily_loss:.2f} / ${max_daily_loss:.2f})"

        # 3. Max posiciones abiertas
        max_positions = cfg.get("max_open_positions", 5)
        if signal.get("action") == "buy" and open_positions >= max_positions:
            return False, f"🛑 Máximo de posiciones abiertas alcanzado ({open_positions}/{max_positions})"

        # 4. Capital insuficiente
        if account_value < 100:
            return False, "🛑 Capital insuficiente en la cuenta"

        logger.info(f"✅ Trade validado para {signal.get('symbol')} | Posiciones: {open_positions}/{max_positions} | Pérdida diaria: ${self._daily_loss:.2f}")
        return True, "OK"

    def register_trade_result(self, pnl: float):
        """Registra el resultado de un trade cerrado para el tracking diario."""
        self._daily_trades += 1
        if pnl < 0:
            self._daily_loss += abs(pnl)
            logger.warning(f"📉 Pérdida registrada: ${pnl:.2f} | Pérdida acumulada hoy: ${self._daily_loss:.2f}")
        else:
            self._winning_trades += 1
            logger.info(f"📈 Ganancia registrada: ${pnl:.2f}")

    def reset_daily_stats(self):
        """Reinicia las estadísticas diarias (llamar al inicio de cada sesión)."""
        self._daily_loss = 0.0
        self._daily_trades = 0
        self._winning_trades = 0
        logger.info("🔄 Estadísticas diarias reiniciadas")

    @property
    def win_rate(self) -> float:
        if self._daily_trades == 0:
            return 0.0
        return round(self._winning_trades / self._daily_trades * 100, 1)

    @property
    def daily_stats(self) -> Dict:
        return {
            "daily_loss": round(self._daily_loss, 2),
            "daily_trades": self._daily_trades,
            "winning_trades": self._winning_trades,
            "win_rate": self.win_rate,
            "bot_enabled": self.bot_enabled,
        }


# Instancia global
risk_manager = RiskManager()
