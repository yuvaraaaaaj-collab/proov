@echo off
title TraderPro Cloudflare Live Tunnel
cd /d "%~dp0"
echo =========================================================
echo    Starting TraderPro Strategy Scanner with Cloudflare
echo =========================================================
python start_with_cloudflare.py
pause
