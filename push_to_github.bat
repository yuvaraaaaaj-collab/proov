@echo off
title Push TraderPro to GitHub
cd /d "%~dp0"
echo =================================================================
echo  Pushing TraderPro to: https://github.com/yuvaraaaaaj-collab/proov.git
echo =================================================================
echo.
git push -u origin main
echo.
echo =================================================================
echo  Done! Now open Render.com to deploy your repository.
echo =================================================================
pause
