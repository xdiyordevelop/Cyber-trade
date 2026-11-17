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
    echo [1/3] Python topilmadi. Python 3.11 avtomatik yuklanmoqda va o'rnatilmoqda...
    powershell -NoProfile -ExecutionPolicy Bypass -Command ^
      "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; " ^
      "$url = 'https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe'; " ^
      "$out = '$env:TEMP\python_setup.exe'; " ^
      "Write-Host 'Yuklanmoqda: Python 3.11...' -ForegroundColor Cyan; " ^
      "Invoke-WebRequest -Uri $url -OutFile $out; " ^
      "Write-Host 'O`'rnatilmoqda (1 daqiqa kuting)...' -ForegroundColor Cyan; " ^
      "Start-Process -FilePath $out -ArgumentList '/quiet InstallAllUsers=1 PrependPath=1 Include_pip=1' -Wait; " ^
      "Remove-Item $out -Force; " ^
      "Write-Host 'Python 3.11 tayyor!' -ForegroundColor Green;"
    
    :: Refresh Path
    set "PATH=C:\Program Files\Python311;C:\Program Files\Python311\Scripts;%LOCALAPPDATA%\Programs\Python\Python311;%LOCALAPPDATA%\Programs\Python\Python311\Scripts;%PATH%"
) else (
    echo [1/3] Python allaqachon mavjud.
)

echo.
echo [2/3] Barcha kerakli kutubxonalar (pip packages) o'rnatilmoqda...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

echo.
echo [3/3] XM Global MetaTrader 5 o'rnatuvchisi yuklanmoqda...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; " ^
  "$url = 'https://download.mql5.com/cdn/web/xm.global.limited/mt5/xmglobal5setup.exe'; " ^
  "$out = '$env:TEMP\xmglobal5setup.exe'; " ^
  "Write-Host 'XM MT5 yuklanmoqda...' -ForegroundColor Cyan; " ^
  "Invoke-WebRequest -Uri $url -OutFile $out; " ^
  "Start-Process -FilePath $out; " ^
  "Write-Host 'XM MT5 o`'rnatish dasturi ochildi!' -ForegroundColor Green;"

if not exist ".env" (
    echo.
    echo [.env] .env fayli yaratilmoqda...
    copy .env.example .env >nul
)

echo.
echo =========================================================
echo   SOZLASH YAKUNLANDI!
echo   1. XM MT5 oynasida "Next" ni bosib MT5 ni o'rnating.
echo   2. MT5 ochilgach, hisobingizga kiring (Login: 108742123, Server: XMGlobal-MT5 5).
echo   3. So'ng START_BOT.bat ni bosing - Bot 24/7 ishga tushadi!
echo =========================================================
echo.
pause
