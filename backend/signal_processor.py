"""
Procesador de señales de TradingView.
Parsea y valida el formato del payload.
"""
import logging
from typing import Dict, Any, Tuple, Optional

logger = logging.getLogger(__name__)

VALID_ACTIONS = {"buy", "sell", "close", "close_all", "cancel_all"}
VALID_SEC_TYPES = {"STK", "CASH", "FUT", "OPT", "CRYPTO"}

def parse_signal(payload: Dict) -> Tuple[bool, str, Optional[Dict]]:
    """
    Parsea y valida el payload del webhook de TradingView.
    Retorna (es_valido, mensaje_error, señal_limpia)
    """
    # 1. Validar acción
    action = str(payload.get("action", "")).lower()
    if not action:
        return False, "❌ Campo 'action' requerido", None
    if action not in VALID_ACTIONS:
        return False, f"❌ Acción inválida: '{action}'", None

    # 2. Acciones globales
    if action in ("close_all", "cancel_all"):
        return True, "OK", {"action": action}

    # 3. Validar símbolo
    symbol = str(payload.get("symbol", "")).upper().strip()
    if not symbol:
        return False, "❌ Campo 'symbol' requerido", None

    # 4. Campos técnicos
    sec_type = str(payload.get("sec_type", "STK")).upper()
    if sec_type not in VALID_SEC_TYPES:
        sec_type = "STK"

    signal = {
        "action": action,
        "symbol": symbol,
        "sec_type": sec_type,
        "exchange": str(payload.get("exchange", "SMART")),
        "currency": str(payload.get("currency", "USD")).upper(),
        "qty": _parse_float(payload.get("qty")),
        "price": _parse_float(payload.get("price")),
        "stop_loss": _parse_float(payload.get("stop_loss")),
        "take_profit": _parse_float(payload.get("take_profit")),
        "comment": str(payload.get("comment", "")),
    }

    return True, "OK", signal

def _parse_float(value) -> Optional[float]:
    if value is None: return None
    try:
        val = float(str(value))
        return val if val > 0 else None
    except:
        return None
