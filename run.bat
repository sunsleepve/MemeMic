@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo First run: installing dependencies...
    call install.bat
    if errorlevel 1 exit /b 1
)

".venv\Scripts\python.exe" -m mememic
if errorlevel 1 pause
