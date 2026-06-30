@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if errorlevel 1 (
    echo No se encontro Python.
    echo Instala Python 3.11 o 3.12 desde python.org y marca "Add Python to PATH".
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo Creando entorno local...
    py -3 -m venv .venv
)

call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt

rmdir /s /q build 2>nul
rmdir /s /q dist 2>nul
del /q HabdornPDF.spec 2>nul

pyinstaller --noconfirm --clean --windowed --onedir --name HabdornPDF main.py

echo.
echo ================================================
echo LISTO: dist\HabdornPDF\HabdornPDF.exe
echo Puedes copiar toda la carpeta HabdornPDF a otro PC.
echo ================================================
pause
