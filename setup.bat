@echo off
setlocal
cd /d %~dp0
where python >nul 2>nul || (echo Python 3.12+ is required.&pause&exit /b 1)
where node >nul 2>nul || (echo Node.js 22+ is required.&pause&exit /b 1)
python -m venv backend\.venv
call backend\.venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r backend\requirements-dev.txt
cd frontend
call npm ci
cd ..
if not exist backend\.env copy backend\.env.example backend\.env >nul
echo.
if not exist frontend\.env.local copy frontend\.env.example frontend\.env.local >nul
echo RoastAI v2 setup complete.
echo Edit backend\.env and add GEMINI_API_KEY and ADMIN_TOKEN, then run start_windows.bat.
pause
