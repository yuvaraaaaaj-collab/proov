@echo off
title TraderPro Cloudflare Token Setup
cd /d "%~dp0"
echo =========================================================
echo       TraderPro Cloudflare Token Setup
echo =========================================================
echo.
set /p TOKEN="Paste your Cloudflare Tunnel Token here and press Enter: "
if "%TOKEN%"=="" (
    echo [!] No token entered. Exiting.
    pause
    exit /b
)

echo CLOUDFLARE_TUNNEL_TOKEN=%TOKEN% > .env
echo.
echo [SUCCESS] Token saved to .env!
echo Starting TraderPro with your permanent Cloudflare Tunnel...
echo =========================================================
python -u start_with_cloudflare.py
pause
