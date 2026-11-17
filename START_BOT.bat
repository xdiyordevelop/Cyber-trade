@echo off
title Cyber Trade Multi-Agent AI (MT5 + COMEX Gold)
cd /d "%~dp0"
echo =========================================================
echo       CYBER TRADE - MULTI-AGENT AI TRADING BOT
echo       XM Broker MT5 (0ms Live Stream) + SMC + ML
echo =========================================================
echo.

set PYTHON_CMD=python
where python >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" (
        set PYTHON_CMD="%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    ) else if exist "..\xaubot-ai\.venv\Scripts\python.exe" (
        set PYTHON_CMD="..\xaubot-ai\.venv\Scripts\python.exe"
    ) else (
        echo [XATOLIK] Python topilmadi! Iltimos, Python o'rnatilganligini tekshiring.
        pause
        exit /b 1
    )
)

echo Python aniqlandi: %PYTHON_CMD%
echo MetaTrader 5 va XM Brokerga ulanish amalga oshirilmoqda...
echo To'xtatish uchun: Ctrl + C
echo =========================================================
echo.

%PYTHON_CMD% main.py
pause
