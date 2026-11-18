@echo off
setlocal
cd /d "%~dp0"

echo [1/3] Membuat virtual environment...
if not exist ".venv\Scripts\python.exe" (
    where py >nul 2>nul
    if %errorlevel%==0 (
        py -3.11 -m venv .venv
    ) else (
        python -m venv .venv
    )
    if errorlevel 1 goto :error
)

echo [2/3] Memperbarui pip...
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto :error

echo [3/3] Menginstall dependencies...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :error

echo.
echo Setup selesai. Jalankan run.bat untuk membuka aplikasi.
pause
exit /b 0

:error
echo.
echo Setup gagal. Periksa instalasi Python dan koneksi internet.
pause
exit /b 1
