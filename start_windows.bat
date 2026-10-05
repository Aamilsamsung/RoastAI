@echo off
setlocal
cd /d %~dp0
if not exist backend\.venv\Scripts\python.exe (echo Run setup.bat first.&pause&exit /b 1)
start "RoastBot API" cmd /k "cd /d %~dp0backend && call .venv\Scripts\activate.bat && python -m uvicorn app.main:app --host 127.0.0.1 --port 8000"
start "RoastBot UI" cmd /k "cd /d %~dp0frontend && npm run dev"
timeout /t 3 >nul
start http://localhost:3000
