@echo off
title ADIF FZR 2.4 - Compilazione (via .spec)
color 0A
cd /d "%~dp0"

echo [1/2] Dipendenze...
python -m pip install --upgrade pyinstaller customtkinter reportlab pillow adif_io openpyxl pyserial pywin32 skyfield sgp4 matplotlib
echo.
echo [2/2] Compilo dal file ADIF_FZR.spec ...
echo.
python -m PyInstaller ADIF_FZR.spec --clean --noconfirm

if errorlevel 1 (
    echo.
    echo [ERRORE] Compilazione fallita. Copiami le ultime righe qui sopra.
    pause & exit /b 1
)
echo.
echo ==========================================================
echo   FATTO!  Eseguibile:  dist\ADIF_FZR.exe
echo ==========================================================
pause
