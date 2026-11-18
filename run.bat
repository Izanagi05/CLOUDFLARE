@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
    echo Virtual environment belum tersedia. Jalankan setup.bat terlebih dahulu.
    pause
    exit /b 1
)
:: Jalankan dengan pythonw di background sehingga window cmd ini bisa langsung tertutup
start "" ".venv\Scripts\pythonw.exe" main.py
exit /b 0
