"""
Cliente de Google Gemini para generar tips de trading.
Replica el comportamiento del Gem personalizado de Senior Portfolio Manager.
Usa el SDK oficial google-genai (v1+).
"""
import logging
import asyncio
from typing import Optional

import config

logger = logging.getLogger(__name__)

# ─── System Prompt del Gem ────────────────────────────────────────────────────
SYSTEM_PROMPT = """Actúa como un Senior Portfolio Manager y Estratega Macro con más de 20 años de experiencia en Wall Street y una especialización profunda en activos digitales (Bitcoin). Tu objetivo es analizar carteras, optimizar el rendimiento ajustado al riesgo y asesorar sobre diversificación y rebalanceo.

Contexto de Mercado Actual (Abril 2026):

Macroeconomía: Estamos en un entorno de "tipos altos por más tiempo". La Fed ha pausado los recortes debido a la volatilidad energética (petróleo >$100 por conflicto en Medio Oriente).

Acciones USA: El S&P 500 muestra resiliencia gracias a beneficios corporativos sólidos (crecimiento del 17%), pero con valoraciones exigentes.

Bitcoin: Analízalo como un "High-Beta Risk Asset". Actualmente cotiza cerca de los $75,000, con una correlación de ~0.74 con el S&P 500. Debes vigilar el soporte de los $60,000 y la resistencia de los $79,000.

Cuando recibas una señal de trading (símbolo + acción), responde con UN consejo conciso y accionable de máximo 3 líneas. Incluye: contexto macro relevante, nivel de riesgo, y una perspectiva profesional sobre el movimiento. No uses markdown, solo texto plano."""

ACTION_LABELS = {
    "buy": "COMPRA",
    "sell": "VENTA",
    "close": "CIERRE DE POSICIÓN",
    "close_all": "CIERRE DE TODAS LAS POSICIONES",
    "cancel_all": "CANCELACIÓN DE ÓRDENES",
}


async def generate_trading_tip(symbol: str, action: str) -> Optional[str]:
    """
    Genera un consejo de trading usando Google Gemini.
    Retorna el tip como string, o None si falla o no está configurado.
    """
    if not config.GEMINI_API_KEY:
        logger.debug("GEMINI_API_KEY no configurada. Tips desactivados.")
        return None

    action_label = ACTION_LABELS.get(action.lower(), action.upper())
    prompt = (
        f"Se ha recibido una señal de trading: {action_label} en {symbol}. "
        f"Dame tu consejo profesional sobre esta operación considerando el contexto macro actual."
    )

    # La SDK de google-genai es síncrona internamente, la ejecutamos en executor
    loop = asyncio.get_running_loop()
    tip = await loop.run_in_executor(None, _call_gemini_sync, prompt)
    return tip


def _call_gemini_sync(prompt: str) -> Optional[str]:
    """Llamada síncrona a la API de Gemini (ejecutada en thread pool executor)."""
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=config.GEMINI_API_KEY)

        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                max_output_tokens=200,
                temperature=0.7,
            ),
        )

        tip = response.text.strip() if response.text else None
        if tip:
            logger.info("✅ Tip de Gemini generado correctamente")
        return tip

    except Exception as e:
        logger.error(f"❌ Error en llamada a Gemini: {e}")
        return None
