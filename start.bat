@echo off
echo.
echo ============================================
echo   Trading Bot - TradingView + IBKR
echo ============================================
echo.

REM Ir al directorio del backend
cd /d "%~dp0backend"

REM Verificar Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python no encontrado. Instala Python 3.10+ desde python.org
    pause
    exit /b 1
)

REM Instalar dependencias si no están
if not exist ".venv" (
    echo [INFO] Creando entorno virtual...
    python -m venv .venv
)

echo [INFO] Activando entorno virtual...
call .venv\Scripts\activate.bat

echo [INFO] Instalando dependencias...
pip install -r requirements.txt -q

REM Copiar .env si no existe
if not exist ".env" (
    if exist "..\.env.example" (
        copy "..\.env.example" ".env" >nul
        echo [AVISO] Se ha creado el archivo .env
        echo [AVISO] Edita .env y cambia WEBHOOK_SECRET antes de usar en produccion
        echo.
    )
)

echo.
echo [INFO] Iniciando Trading Bot...
echo [INFO] Dashboard: http://localhost:8080
echo [INFO] API Docs:  http://localhost:8080/docs
echo [INFO] Presiona Ctrl+C para detener
echo.

python main.py

pause
