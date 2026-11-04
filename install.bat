@echo off
setlocal
cd /d "%~dp0"

if not exist "requirements.txt" (
    echo requirements.txt not found. Run install.bat from the project folder.
    exit /b 1
)

set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY (
    where python >nul 2>nul && set "PY=python"
)
if not defined PY (
    echo Python 3.10+ not found.
    echo Install it from https://www.python.org/downloads/ and enable "Add python.exe to PATH".
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo Creating virtual environment...
    %PY% -m venv .venv
    if errorlevel 1 goto :error
)

echo Installing dependencies...
".venv\Scripts\python.exe" -m pip install --upgrade pip --quiet
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :error

echo.
echo Done. Start the app with run.bat
exit /b 0

:error
echo.
echo Installation failed. Check the messages above.
exit /b 1
