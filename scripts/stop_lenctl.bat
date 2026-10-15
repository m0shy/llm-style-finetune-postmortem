@echo off
chcp 65001 >nul
title Local Model Server - STOP
echo ============================================================
echo   Stop llama-server (port 8001)
echo   NOTE: this only stops the INFERENCE server.
echo         Training processes are NOT touched.
echo ============================================================
echo.
echo [Before]
tasklist | findstr /I "llama-server" || echo   (no llama-server running)
echo.
taskkill /IM llama-server.exe /F 2>nul
timeout /t 3 /nobreak >nul
echo.
echo [After]
tasklist | findstr /I "llama-server" || echo   [OK] all stopped
echo.
echo Server stopped.
timeout /t 3 >nul
