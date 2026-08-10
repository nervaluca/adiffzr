@echo off
title ADIF FZR 2.4 - Crea Installer
color 0B
cd /d "%~dp0"

echo.
echo ==========================================================
echo    ADIF FZR 2.4 - Creazione installer con Inno Setup
echo ==========================================================
echo.

REM 1) Controllo che l'eseguibile esista
if not exist "dist\ADIF_FZR.exe" (
    echo [ERRORE] Non trovo  dist\ADIF_FZR.exe
    echo   Compila prima l'eseguibile con COMPILA_SPEC.bat
    pause & exit /b 1
)

REM 2) Cerco Inno Setup 6 nei due percorsi standard
set "ISCC=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=C:\Program Files\Inno Setup 6\ISCC.exe"

if not exist "%ISCC%" (
    echo [ERRORE] Inno Setup 6 non trovato.
    echo   Scaricalo gratis da:  https://jrsoftware.org/isdl.php
    echo   Installalo ^(avanti-avanti^) e rilancia questo file.
    pause & exit /b 1
)

REM 3) Creo la cartella di output e compilo l'installer
if not exist "installer_output" mkdir installer_output

echo Uso: "%ISCC%"
echo Script: setup_v25_modular.iss
echo.
"%ISCC%" "setup_v25_modular.iss"

if errorlevel 1 (
    echo.
    echo [ERRORE] Creazione installer fallita. Copiami le ultime righe qui sopra.
    pause & exit /b 1
)

echo.
echo ==========================================================
echo    FATTO!  Installer creato in:
echo    installer_output\ADIF_FZR_v2.5_Setup.exe
echo ==========================================================
echo.
pause
