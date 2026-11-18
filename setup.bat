@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ========================================================
echo   CLOUDFLARE TUNNEL MANAGER - SETUP & INSTALASI
echo ========================================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [1/3] Mendeteksi Python di komputer...
    
    set "PY_CMD="

    :: 1. Coba perintah 'python' terlebih dahulu
    python -c "import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)" >nul 2>nul
    if !errorlevel!==0 (
        set "PY_CMD=python"
        goto :python_detected
    )

    :: 2. Coba perintah 'py -3' (Python Launcher Windows)
    py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)" >nul 2>nul
    if !errorlevel!==0 (
        set "PY_CMD=py -3"
        goto :python_detected
    )

    :: 3. Coba perintah 'py' generik
    py -c "import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)" >nul 2>nul
    if !errorlevel!==0 (
        set "PY_CMD=py"
        goto :python_detected
    )

    :: 4. Jika semua gagal
    goto :python_missing

:python_detected
    echo [OK] Python terdeteksi:
    !PY_CMD! --version
    echo.
    echo [2/3] Membuat virtual environment (.venv)...
    !PY_CMD! -m venv .venv
    if errorlevel 1 goto :venv_error
) else (
    echo [OK] Virtual environment (.venv) sudah tersedia.
)

echo.
echo [3/3] Memperbarui pip dan menginstall dependencies...
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto :install_error

".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :install_error

echo.
echo ========================================================
echo   SETUP SELESAI DENGAN SUKSES!
echo ========================================================
echo.
echo Untuk membuka aplikasi tanpa jendela CMD:
echo   - Double-click: run_gui.vbs (Rekomendasi)
echo   - Atau double-click: tunnel.bat (atau run.bat)
echo.
pause
exit /b 0

:python_missing
echo.
echo ========================================================
echo [ERROR] Python tidak terdeteksi di komputer Anda!
echo ========================================================
echo Penyebab yang sering terjadi:
echo  1. Python belum terinstall di komputer.
echo  2. Saat install Python, opsi "Add python.exe to PATH" lupa dicentang.
echo  3. Fitur "App execution aliases" Windows aktif sehingga 'python' membuka Microsoft Store.
echo.
echo Solusi:
echo  1. Unduh Python resmi di: https://www.python.org/downloads/
echo  2. Saat instalasi, PASTIKAN MENCENTANG:
echo     [v] Add python.exe to PATH
echo  3. Jika sudah install tapi masih tidak terdeteksi:
echo     Buka Start Menu -^> ketik "Manage app execution aliases" -^> Matikan (OFF) opsi "App Installer (python.exe)".
echo ========================================================
echo.
pause
exit /b 1

:venv_error
echo.
echo [ERROR] Gagal membuat virtual environment (.venv).
echo Pastikan izin folder aman dan modul venv tersedia.
pause
exit /b 1

:install_error
echo.
echo [ERROR] Gagal menginstall dependencies.
echo Periksa koneksi internet Anda dan coba jalankan setup.bat kembali.
pause
exit /b 1
