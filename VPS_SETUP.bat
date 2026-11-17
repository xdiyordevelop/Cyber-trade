@echo off
title Cyber Trade - VPS Auto Setup (1-Click Installer)
cd /d "%~dp0"

echo =========================================================
echo       CYBER TRADE - VPS AVTOMATIK SOZLASH TIZIMI
echo =========================================================
echo.

:: 1. Check Python
python --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [1/3] Python 3.11 avtomatik yuklanmoqda va o'rnatilmoqda...
    echo Iltimos, 1-2 daqiqa kuting...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference = 'SilentlyContinue'; [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; (New-Object Net.WebClient).DownloadFile('https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe', '$env:TEMP\python_setup.exe'); Start-Process -FilePath '$env:TEMP\python_setup.exe' -ArgumentList '/quiet InstallAllUsers=1 PrependPath=1 Include_pip=1' -Wait; Remove-Item '$env:TEMP\python_setup.exe' -Force"
    
    :: Refresh Path
    set "PATH=C:\Program Files\Python311;C:\Program Files\Python311\Scripts;%LOCALAPPDATA%\Programs\Python\Python311;%LOCALAPPDATA%\Programs\Python\Python311\Scripts;%PATH%"
) else (
    echo [1/3] Python allaqachon mavjud.
)

:: Find python executable
set "PY=python"
if exist "C:\Program Files\Python311\python.exe" (
    set "PY=C:\Program Files\Python311\python.exe"
) else if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" (
    set "PY=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
)

echo.
echo [2/3] Barcha kerakli kutubxonalar o'rnatilmoqda...
"%PY%" -m pip install --upgrade pip
"%PY%" -m pip install -r requirements.txt

echo.
echo [3/3] XM Global MetaTrader 5 o'rnatuvchisi yuklanmoqda...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference = 'SilentlyContinue'; [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; (New-Object Net.WebClient).DownloadFile('https://download.mql5.com/cdn/web/xm.global.limited/mt5/xmglobal5setup.exe', '$env:TEMP\xmglobal5setup.exe'); Start-Process -FilePath '$env:TEMP\xmglobal5setup.exe'"

if not exist ".env" (
    echo.
    echo [.env] .env fayli yaratilmoqda...
    copy .env.example .env >nul
)

echo.
echo =========================================================
echo   SOZLASH YAKUNLANDI!
echo   1. XM MT5 oynasida Next ni bosib MT5 ni o'rnating.
echo   2. MT5 ochilgach hisobingizga kiring (Login: 108742123, Server: XMGlobal-MT5 5).
echo   3. So'ng START_BOT.bat ni bosing - Bot 24/7 ishga tushadi!
echo =========================================================
echo.
pause
