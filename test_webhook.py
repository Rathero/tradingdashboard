"""
Script de prueba para enviar señales fake al webhook del Trading Bot.
Ejecutar con el servidor corriendo: python test_webhook.py
"""
import json
import urllib.request
import urllib.error
import sys

# Fix emoji output on Windows console
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# ─── Configuración ────────────────────────────────────────────────────────────
BASE_URL = "http://localhost:8080"
WEBHOOK_SECRET = "MICLAVESECRETAPARANUESOBOT184568X"

# ─── Señales de prueba disponibles ────────────────────────────────────────────
SIGNALS = {
    "1": {
        "name": "📈 COMPRA AAPL (Market Order)",
        "payload": {
            "secret": WEBHOOK_SECRET,
            "action": "buy",
            "symbol": "AAPL",
            "sec_type": "STK",
        }
    },
    "2": {
        "name": "📉 VENTA AAPL (Market Order)",
        "payload": {
            "secret": WEBHOOK_SECRET,
            "action": "sell",
            "symbol": "AAPL",
            "sec_type": "STK",
        }
    },
    "3": {
        "name": "📈 COMPRA MSFT con precio límite",
        "payload": {
            "secret": WEBHOOK_SECRET,
            "action": "buy",
            "symbol": "MSFT",
            "sec_type": "STK",
            "price": 415.50,
            "stop_loss": 405.00,
            "take_profit": 435.00,
            "qty": 5
        }
    },
    "4": {
        "name": "₿ COMPRA Bitcoin",
        "payload": {
            "secret": WEBHOOK_SECRET,
            "action": "buy",
            "symbol": "BTC",
            "sec_type": "CRYPTO",
            "price": 75000,
        }
    },
    "5": {
        "name": "❌ CIERRE posición AAPL",
        "payload": {
            "secret": WEBHOOK_SECRET,
            "action": "close",
            "symbol": "AAPL",
            "sec_type": "STK",
        }
    },
    "6": {
        "name": "🔴 CIERRE de TODAS las posiciones",
        "payload": {
            "secret": WEBHOOK_SECRET,
            "action": "close_all",
        }
    },
    "7": {
        "name": "🚫 Señal INVÁLIDA (secret malo - para probar rechazo)",
        "payload": {
            "secret": "CLAVE_INCORRECTA",
            "action": "buy",
            "symbol": "AAPL",
        }
    },
}


def send_webhook(payload: dict) -> None:
    url = f"{BASE_URL}/webhook"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            body = json.loads(response.read().decode())
            print(f"  ✅ Respuesta [{response.status}]: {json.dumps(body, ensure_ascii=False, indent=2)}")
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"  ⚠️  HTTP {e.code}: {body}")
    except Exception as e:
        print(f"  ❌ Error de conexión: {e}")
        print(f"     ¿Está corriendo el servidor en {BASE_URL}?")


def main():
    print("\n" + "="*55)
    print("  Trading Bot — Webhook Tester")
    print("="*55)
    print(f"  Servidor: {BASE_URL}")
    print("="*55)
    print()

    # Si se pasa un número como argumento, ejecutar directamente
    if len(sys.argv) > 1:
        key = sys.argv[1]
        if key in SIGNALS:
            sig = SIGNALS[key]
            print(f"Enviando: {sig['name']}")
            print(f"Payload:  {json.dumps(sig['payload'], ensure_ascii=False)}")
            send_webhook(sig["payload"])
            return
        else:
            print(f"Opción inválida: {key}. Usa un número del 1 al {len(SIGNALS)}.")
            return

    # Menú interactivo
    while True:
        print("Selecciona la señal a enviar:\n")
        for key, sig in SIGNALS.items():
            print(f"  [{key}] {sig['name']}")
        print(f"  [0] Salir\n")

        choice = input("Opción: ").strip()
        if choice == "0":
            print("Saliendo...")
            break
        if choice not in SIGNALS:
            print("Opción inválida.\n")
            continue

        sig = SIGNALS[choice]
        print(f"\n→ Enviando: {sig['name']}")
        print(f"  Payload: {json.dumps(sig['payload'], ensure_ascii=False)}")
        send_webhook(sig["payload"])
        print()


if __name__ == "__main__":
    main()
