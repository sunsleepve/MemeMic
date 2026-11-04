@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Run install.bat first.
    exit /b 1
)

".venv\Scripts\python.exe" -m pip install --quiet pyinstaller || exit /b 1

".venv\Scripts\python.exe" -m PyInstaller ^
    --noconfirm ^
    --clean ^
    --onefile ^
    --windowed ^
    --name MemeMic ^
    --icon assets\mememic.ico ^
    --collect-all sounddevice ^
    main.py || exit /b 1

echo.
echo Built: dist\MemeMic.exe
