@echo off
title WorldMate Pro Server
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  echo Python topilmadi. Python 3 o'rnating.
  pause
  exit /b
)
python server.py
pause
