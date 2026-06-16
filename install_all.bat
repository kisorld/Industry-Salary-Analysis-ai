@echo off
setlocal
cd /d "%~dp0"

echo ============================================================
echo  行业薪酬洞察 AI 智能体 - 一键安装依赖
echo ============================================================
echo.

where py >nul 2>nul
if errorlevel 1 (
  echo [ERROR] 未找到 Python 启动器 py。
  echo 请先安装 Python 3.11，并勾选 Add Python to PATH。
  echo 下载地址: https://www.python.org/downloads/release/python-3119/
  pause
  exit /b 1
)

where npm >nul 2>nul
if errorlevel 1 (
  echo [ERROR] 未找到 npm。
  echo 请先安装 Node.js LTS。
  echo 下载地址: https://nodejs.org/
  pause
  exit /b 1
)

echo [1/5] 检查 Python 3.11...
py -3.11 --version >nul 2>nul
if errorlevel 1 (
  echo [ERROR] 当前电脑没有可用的 Python 3.11。
  echo 本项目建议使用 Python 3.11，不建议使用 Python 3.14。
  pause
  exit /b 1
)

echo [2/5] 创建或复用后端虚拟环境...
if not exist "backend\.venv\Scripts\python.exe" (
  py -3.11 -m venv backend\.venv
  if errorlevel 1 (
    echo [ERROR] 创建虚拟环境失败。
    pause
    exit /b 1
  )
) else (
  echo [INFO] 已存在 backend\.venv，继续复用。
)

echo [3/5] 安装后端 Python 依赖...
backend\.venv\Scripts\python.exe -m pip install --upgrade pip
if errorlevel 1 (
  echo [ERROR] pip 升级失败。
  pause
  exit /b 1
)

backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
if errorlevel 1 (
  echo [ERROR] 后端依赖安装失败。
  echo 如果是网络超时，请稍后重试，或切换到稳定网络。
  pause
  exit /b 1
)

echo [4/5] 安装 Playwright Chromium 浏览器内核...
backend\.venv\Scripts\python.exe -m playwright install chromium
if errorlevel 1 (
  echo [WARN] Playwright 浏览器内核安装失败。
  echo 不影响 CSV/Excel 分析和基础功能，但动态网页采集可能不可用。
  echo 可以之后手动执行:
  echo   backend\.venv\Scripts\python.exe -m playwright install chromium
)

echo [5/5] 安装前端 Node 依赖...
pushd frontend
call npm install
if errorlevel 1 (
  popd
  echo [ERROR] 前端依赖安装失败。
  pause
  exit /b 1
)
popd

echo.
echo ============================================================
echo [OK] 依赖安装完成。
echo 下一步可以运行:
echo   .\start_all.bat
echo 然后打开:
echo   http://127.0.0.1:5173
echo ============================================================
pause
