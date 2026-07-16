@echo off
setlocal
cd /d "%~dp0"

py -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 1)" >nul 2>nul
if errorlevel 1 (
  echo RecommendSignal needs Python 3.10 or newer.
  echo Install it from https://www.python.org/downloads/ and try again.
  pause
  exit /b 1
)

if not exist .venv py -3 -m venv .venv
call .venv\Scripts\activate.bat
if not defined ARROW_DEFAULT_MEMORY_POOL set ARROW_DEFAULT_MEMORY_POOL=system

for /f %%H in ('powershell -NoProfile -Command "$a=(Get-FileHash requirements.txt -Algorithm SHA256).Hash; $b=(Get-FileHash pyproject.toml -Algorithm SHA256).Hash; $bytes=[Text.Encoding]::UTF8.GetBytes($a+$b); ([BitConverter]::ToString([Security.Cryptography.SHA256]::Create().ComputeHash($bytes))).Replace('-','').ToLower()"') do set REQ_HASH=%%H
if not exist .venv\.recommendsignal-requirements-%REQ_HASH% (
  echo Installing RecommendSignal packages. Later launches will be faster.
  python -m pip --disable-pip-version-check install --prefer-binary -r requirements.txt
  del /q .venv\.recommendsignal-requirements-* .venv\.recommendsignal-ready 2>nul
  type nul > .venv\.recommendsignal-requirements-%REQ_HASH%
)

if not defined RECOMMENDSIGNAL_PORT set RECOMMENDSIGNAL_PORT=8587
if not defined RECOMMENDSIGNAL_MAX_UPLOAD_MB set RECOMMENDSIGNAL_MAX_UPLOAD_MB=200
python -m streamlit run app.py --server.headless=false --server.address=127.0.0.1 --server.port=%RECOMMENDSIGNAL_PORT% --server.maxUploadSize=%RECOMMENDSIGNAL_MAX_UPLOAD_MB% --server.fileWatcherType=none --browser.gatherUsageStats=false
