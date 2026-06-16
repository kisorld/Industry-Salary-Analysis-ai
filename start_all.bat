@echo off
setlocal
cd /d "%~dp0"

if not exist "backend\.venv\Scripts\python.exe" (
  echo [ERROR] backend\.venv not found.
  echo Please run:
  echo   cd backend
  echo   py -3.11 -m venv .venv
  echo   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
  pause
  exit /b 1
)

where npm >nul 2>nul
if errorlevel 1 (
  echo [ERROR] npm not found. Please install Node.js LTS from https://nodejs.org/
  pause
  exit /b 1
)

if not exist "frontend\node_modules" (
  echo [INFO] Installing frontend dependencies...
  pushd frontend
  call npm install
  if errorlevel 1 (
    echo [ERROR] npm install failed.
    pause
    exit /b 1
  )
  popd
)

echo [INFO] Stopping old services on ports 8000 and 5173...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-NetTCPConnection -LocalPort 8000,5173 -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }"

echo [INFO] Starting backend at http://127.0.0.1:8000
start "salary-backend" cmd /k "cd /d %~dp0backend && .\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000"

echo [INFO] Starting frontend at http://127.0.0.1:5173
start "salary-frontend" cmd /k "cd /d %~dp0frontend && npm run dev"

echo [OK] Services are starting. Open http://127.0.0.1:5173
pause
