@echo off
title Cyber Trade Multi-Agent AI (MT5 + COMEX Gold)
cd /d "%~dp0"
echo =========================================================
echo       CYBER TRADE - MULTI-AGENT AI TRADING BOT
echo       XM Broker MT5 (0ms Live Stream) + SMC + ML
echo =========================================================
echo.

set PYTHON_CMD=

if exist "..\xaubot-ai\.venv\Scripts\python.exe" (
    set PYTHON_CMD="..\xaubot-ai\.venv\Scripts\python.exe"
) else if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" (
    set PYTHON_CMD="%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
) else (
    set PYTHON_CMD=python
)

echo Tanlangan Python muhiti: %PYTHON_CMD%
echo MetaTrader 5 va XM Brokerga ulanish amalga oshirilmoqda...
echo To'xtatish uchun: Ctrl + C
echo =========================================================
echo.

%PYTHON_CMD% main.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo =========================================================
    echo [ESLATMA] Agar xatolik chiqsa:
    echo 1. MetaTrader 5 dasturini oching.
    echo 2. Agar "Smart App Control blocked" desa:
    echo    Windows Start -^> "Smart App Control" -^> Off (O'chirish)
    echo =========================================================
)
pause
