@echo off
setlocal

cd /d "%~dp0"

echo [1/3] Checking Python...
where python >nul 2>nul
if errorlevel 1 (
  echo Python was not found in PATH.
  echo Please install Python 3.10+ and make sure "Add python.exe to PATH" is enabled.
  pause
  exit /b 1
)

echo [2/3] Installing dependencies...
python -m pip install -r requirements.txt
if errorlevel 1 (
  echo Failed to install dependencies.
  pause
  exit /b 1
)

echo [3/3] Starting Streamlit...
python -m streamlit run app.py %*

endlocal
