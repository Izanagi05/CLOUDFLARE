@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo =======================================================
echo   BUILD STANDALONE EXE (NO CONSOLE / WINDOWED)
echo =======================================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment belum siap. Jalankan setup.bat terlebih dahulu.
    pause
    exit /b 1
)

echo [1/3] Memeriksa / Menginstall PyInstaller...
".venv\Scripts\python.exe" -m pip install pyinstaller
if errorlevel 1 (
    echo [ERROR] Gagal menginstall PyInstaller.
    pause
    exit /b 1
)

echo.
echo [2/3] Membangun executable CloudflareTunnelManager.exe...
:: Parameter --noconsole / --windowed memastikan cmd.exe tidak muncul saat exe dijalankan!
".venv\Scripts\pyinstaller.exe" --noconsole --windowed --clean --name "CloudflareTunnelManager" --add-data "bin;bin" --add-data "tunnel_manager;tunnel_manager" main.py
if errorlevel 1 (
    echo [ERROR] Build gagal.
    pause
    exit /b 1
)

echo.
echo [3/3] Build selesai!
echo Executable dapat ditemukan di folder: dist\CloudflareTunnelManager\CloudflareTunnelManager.exe
echo.
echo Silakan jalankan dist\CloudflareTunnelManager\CloudflareTunnelManager.exe (tidak akan ada cmd.exe yang muncul).
pause
exit /b 0
