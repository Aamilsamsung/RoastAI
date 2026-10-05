@echo off
setlocal
cd /d %~dp0
if not exist backend\.venv\Scripts\python.exe (echo Run setup.bat first.&pause&exit /b 1)
call backend\.venv\Scripts\activate.bat
cd backend
python -m pytest tests -q
if errorlevel 1 exit /b 1
cd ..\frontend
call npm run build
if errorlevel 1 exit /b 1
echo Production build and backend checks passed.
pause
