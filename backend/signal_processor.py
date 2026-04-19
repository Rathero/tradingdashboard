"""
Procesador de señales de TradingView.
Parsea, valida y enruta las señales al order manager.
"""
import logging
from typing import Dict, Any, Tuple, Optional

import config

logger = logging.getLogger(__name__)

VALID_ACTIONS = {"buy", "sell", "close", "close_all", "cancel_all"}
VALID_SEC_TYPES = {"STK", "CASH", "FUT", "OPT", "CRYPTO"}
CRYPTO_SYMBOLS = {"BTC", "ETH", "SOL", "BNB", "XRP", "LTC", "ADA", "DOT"}


def validate_webhook_secret(payload: Dict) -> Tuple[bool, str]:
    """Valida que el webhook contiene el secret correcto."""
    secret = payload.get("secret", "")
    if secret != config.WEBHOOK_SECRET:
        return False, "❌ Secret inválido"
    return True, "OK"


def parse_signal(payload: Dict) -> Tuple[bool, str, Optional[Dict]]:
    """
    Parsea y valida el payload del webhook de TradingView.

    Formato esperado:
    {
        "secret": "TU_CLAVE",
        "action": "buy" | "sell" | "close" | "close_all" | "cancel_all",
        "symbol": "AAPL",
        "sec_type": "STK",          // Opcional, default STK
        "exchange": "SMART",        // Opcional
        "currency": "USD",          // Opcional
        "qty": 10,                  // Opcional, si no usa risk manager
        "price": 185.50,            // Opcional (para limit orders)
        "stop_loss": 183.00,        // Opcional
        "take_profit": 190.00,      // Opcional
        "comment": "señal alcista"  // Opcional
    }
    """
    # Validar secret
    valid, msg = validate_webhook_secret(payload)
    if not valid:
        return False, msg, None

    # Validar acción
    action = str(payload.get("action", "")).lower()
    if not action:
        return False, "❌ Campo 'action' requerido", None
    if action not in VALID_ACTIONS:
        return False, f"❌ Acción inválida: '{action}'. Válidas: {VALID_ACTIONS}", None

    # Para close_all y cancel_all no necesitamos símbolo
    if action in ("close_all", "cancel_all"):
        return True, "OK", {"action": action}

    # Validar símbolo
    symbol = str(payload.get("symbol", "")).upper().strip()
    if not symbol:
        return False, "❌ Campo 'symbol' requerido", None

    # Parsear campos opcionales
    sec_type = str(payload.get("sec_type", "")).upper()
    currency = str(payload.get("currency", "USD")).upper()
    
    # Auto-detección de CRYPTO si no se especifica tipo
    if not sec_type:
        is_crypto = any(s in symbol for s in CRYPTO_SYMBOLS)
        sec_type = "CRYPTO" if is_crypto else "STK"
    
    if sec_type not in VALID_SEC_TYPES:
        sec_type = "STK"

    # Limpieza de símbolo para CRYPTO y CASH (de BTCUSD -> BTC)
    if sec_type in ("CRYPTO", "CASH"):
        for base in CRYPTO_SYMBOLS:
            if symbol.startswith(base) and len(symbol) > len(base):
                # Si es BTCUSD, el símbolo en IBKR es solo BTC y la moneda USD
                currency = symbol[len(base):]
                symbol = base
                break
        # Caso especial para Forex si no se detectó arriba (ej: EURUSD)
        if sec_type == "CASH" and len(symbol) == 6:
            currency = symbol[3:]
            symbol = symbol[:3]

    signal = {
        "action": action,
        "symbol": symbol,
        "sec_type": sec_type,
        "exchange": str(payload.get("exchange", "SMART" if sec_type != "CRYPTO" else "PAXOS")),
        "currency": currency,
        "qty": _parse_float(payload.get("qty")),           # None = usa risk manager
        "price": _parse_float(payload.get("price")),
        "stop_loss": _parse_float(payload.get("stop_loss")),
        "take_profit": _parse_float(payload.get("take_profit")),
        "comment": str(payload.get("comment", "")),
    }

    logger.info(f"📨 Señal parseada: {action} {symbol} | qty={signal['qty']} | price={signal['price']}")
    return True, "OK", signal


def _parse_float(value) -> Optional[float]:
    """Convierte un valor a float de forma segura."""
    if value is None:
        return None
    try:
        val = float(str(value))
        return val if val > 0 else None
    except (ValueError, TypeError):
        return None
