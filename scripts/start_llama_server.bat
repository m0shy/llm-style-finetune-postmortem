@echo off
chcp 65001 >nul
title Local Model Server (lenctl_v1)
echo ============================================================
echo   Model: lenctl_v1-Q4_K_M  (CPT v3 + SFT length-control)
echo   Port : http://127.0.0.1:8001
echo   WebUI: ui\chapter_chat_zh.html
echo ============================================================
echo.
echo Config: -ngl 28 (VRAM~1.5G) | KV on CPU | -c 6144
echo Measured: 46.6 tok/s | 3000-word chapter ~40s | zero crash
echo.
echo NOTE: DRY sampler DISABLED (incompatible with this model, CUDA crash)
echo STOP: press Ctrl+C ONCE here. Do NOT restart repeatedly.
echo -----------------------------------------------------------
echo.
cd /d <本地工具链>\llama.cpp
cuda\llama-server.exe ^
  -m "<项目目录>\Models\gguf\lenctl_v1-Q4_K_M.gguf" ^
  -ngl 28 ^
  -c 6144 ^
  -t 8 ^
  --host 127.0.0.1 ^
  --port 8001 ^
  --alias local-model
echo.
echo Server exited.
pause
