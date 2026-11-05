@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Run install.bat first.
    exit /b 1
)

".venv\Scripts\python.exe" -m pip install --quiet pyinstaller || exit /b 1

if exist "dist\MemeMic" rmdir /s /q "dist\MemeMic"
if exist "dist\MemeMic-win64.zip" del /q "dist\MemeMic-win64.zip"

".venv\Scripts\python.exe" -m PyInstaller ^
    --noconfirm ^
    --clean ^
    --onedir ^
    --windowed ^
    --name MemeMic ^
    --icon assets\mememic.ico ^
    --collect-all sounddevice ^
    main.py || exit /b 1

copy /y README.md "dist\MemeMic\README.md" >nul
copy /y README.ru.md "dist\MemeMic\README.ru.md" >nul
copy /y LICENSE "dist\MemeMic\LICENSE" >nul

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "Compress-Archive -Path 'dist\MemeMic' -DestinationPath 'dist\MemeMic-win64.zip' -CompressionLevel Optimal -Force" || exit /b 1

echo.
echo Built: dist\MemeMic\MemeMic.exe
echo ZIP:   dist\MemeMic-win64.zip
