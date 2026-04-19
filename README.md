# 🤖 Trading Bot — TradingView + Interactive Brokers

Sistema de trading automatizado que conecta alertas de TradingView con Interactive Brokers para ejecutar órdenes automáticas con gestión de riesgo integrada.

---

## 📁 Estructura del Proyecto

```
trading-bot/
├── backend/
│   ├── main.py              # Servidor FastAPI: webhook + REST + WebSocket
│   ├── ibkr_client.py       # Cliente IBKR (ib_insync)
│   ├── order_manager.py     # Gestor de órdenes
│   ├── risk_manager.py      # Gestión de riesgo
│   ├── signal_processor.py  # Parser de señales TradingView
│   ├── database.py          # SQLite: historial y configuración
│   ├── config.py            # Configuración central
│   └── requirements.txt
├── frontend/
│   ├── index.html           # Dashboard principal
│   ├── css/style.css
│   └── js/
│       ├── app.js           # Lógica del dashboard
│       ├── charts.js        # Gráfico P&L
│       └── websocket.js     # Conexión en tiempo real
├── .env.example             # Variables de entorno (copia a .env)
├── start.bat                # Script de arranque Windows
└── README.md
```

---

## 🚀 Instalación y Configuración

### 1. Prerequisitos

- **Python 3.10+** — [python.org](https://www.python.org/downloads/)
- **TWS o IB Gateway** — Descarga desde [interactivebrokers.com](https://www.interactivebrokers.com/en/trading/tws.php)
- **Cuenta Interactive Brokers** (paper trading recomendado para empezar)

### 2. Configurar TWS / IB Gateway

1. Abre **TWS** o **IB Gateway**
2. Ve a: `Edit → Global Configuration → API → Settings`
3. Activa: ✅ **Enable ActiveX and Socket Clients**
4. Puerto: `7497` (Paper Trading) o `7496` (Real)
5. Activa: ✅ **Allow connections from localhost only**

### 3. Configurar el Bot

```bash
# Copia el ejemplo de .env
copy .env.example backend\.env

# Edita el archivo y cambia:
# - WEBHOOK_SECRET (clave secreta que usarás en TradingView)
# - IBKR_PORT (7497 para paper, 7496 para real)
# - PAPER_TRADING (true/false)
```

### 4. Arrancar

```bash
# Doble click en start.bat  —  O desde terminal:
start.bat
```

Abre el dashboard en: **http://localhost:8000**

---

## 📡 Configurar Alertas en TradingView

### Formato del mensaje (JSON)

```json
{
  "secret": "TU_CLAVE_WEBHOOK",
  "action": "{{strategy.order.action}}",
  "symbol": "{{ticker}}",
  "price": {{close}},
  "qty": 10
}
```

### Campos disponibles

| Campo | Tipo | Descripción |
|---|---|---|
| `secret` | string | **Requerido** — debe coincidir con WEBHOOK_SECRET |
| `action` | string | **Requerido** — `buy`, `sell`, `close`, `close_all`, `cancel_all` |
| `symbol` | string | **Requerido** — ticker (ej: `AAPL`, `MSFT`) |
| `sec_type` | string | Opcional — `STK` (default), `CASH`, `FUT` |
| `qty` | number | Opcional — si no se indica, lo calcula el risk manager |
| `price` | number | Opcional — si no indica, ejecuta a mercado |
| `stop_loss` | number | Opcional — precio de stop loss |
| `take_profit` | number | Opcional — precio de take profit |

### URL del Webhook

```
http://TU_IP_PUBLICA:8000/webhook
```

> **Nota**: Para que TradingView llegue a tu servidor necesitas IP pública o usar **ngrok**:
> ```bash
> ngrok http 8000
> ```

---

## ⚙️ Gestión de Riesgo

### Parámetros configurables desde el Dashboard

| Parámetro | Descripción |
|---|---|
| **Riesgo por Trade (%)** | % del capital expuesto por trade (ej: 1% = arriesgas $100 en una cuenta de $10k) |
| **Pérdida Máx. Diaria (%)** | El bot se detiene automáticamente si se supera este límite |
| **Max. Posiciones Abiertas** | Número máximo de trades simultáneos |
| **Stop Loss por Defecto (%)** | Si el Pine Script no especifica SL, el bot lo calcula automáticamente |
| **Take Profit por Defecto (%)** | Igual para el TP |
| **Tamaño Máx. Posición (%)** | Máximo % del capital en una sola posición |

### Cálculo de tamaño de posición

Con Stop Loss:
```
Qty = (Capital × Riesgo%) / (Entrada - Stop Loss)
```

Sin Stop Loss:
```
Qty = (Capital × Max.Posición%) / Precio Entrada
```

---

## 📊 Dashboard

| Sección | Descripción |
|---|---|
| **Header** | Estado conexión IBKR, ON/OFF del bot, botones de emergencia |
| **Stats Cards** | Balance, P&L diario, posiciones abiertas, win rate |
| **Gráfico P&L** | Histórico diario (7D / 30D / 90D) |
| **Posiciones** | Tabla en vivo con unrealized P&L, opción de cerrar individualmente |
| **Historial** | Todos los trades ejecutados |
| **Señales** | Log en tiempo real de señales recibidas de TradingView |
| **Riesgo** | Panel de configuración editable |
| **Webhook** | URL y formato del mensaje para copiar en TradingView |

---

## 🔌 API Endpoints

| Método | Ruta | Descripción |
|---|---|---|
| POST | `/webhook` | Recibe alertas de TradingView |
| GET | `/status` | Estado del bot |
| GET | `/account` | Datos de cuenta IBKR |
| GET | `/positions` | Posiciones abiertas |
| GET | `/orders` | Órdenes pendientes |
| GET | `/signals?limit=50` | Log de señales |
| GET | `/trades?status=open` | Historial de trades |
| GET | `/pnl?days=30` | P&L histórico |
| GET/PUT | `/config/risk` | Configuración de riesgo |
| POST | `/bot/toggle` | Habilitar/deshabilitar bot |
| POST | `/bot/reconnect` | Reconectar IBKR |
| POST | `/bot/close_all` | Cerrar todas las posiciones |
| POST | `/bot/cancel_all` | Cancelar todas las órdenes |
| WS | `/ws` | WebSocket en tiempo real |
| GET | `/docs` | Documentación interactiva (FastAPI/Swagger) |

---

## ⚠️ Advertencias

- **Empieza siempre en Paper Trading** (`IBKR_PORT=7497`)
- **Nunca compartas tu WEBHOOK_SECRET**
- **IBKR solo acepta conexiones locales** — el bot debe correr en el mismo PC que TWS
- Para acceso remoto, usa una VPN o proxy seguro
- **Verifica siempre las señales** antes de poner el bot en modo real

---

## 📄 Licencia

Uso personal — Úsalo bajo tu propia responsabilidad. El trading implica riesgo de pérdida de capital.
