@echo off
chcp 65001 > nul
cd /d "%~dp0"
python app.py
if errorlevel 1 (
  echo.
  echo 실행하지 못했습니다. 파이썬이 설치되어 있는지 확인해 주세요: https://www.python.org/downloads/
  pause
)
