@echo off
title ADIF FZR 2.4 - Build completo (pulizia + exe + installer)
color 0A
cd /d "%~dp0"

echo.
echo ==========================================================
echo    ADIF FZR 2.4 - BUILD COMPLETO
echo    Pulizia  ^>  Eseguibile  ^>  Installer
echo ==========================================================
echo.

REM ----------------------------------------------------------
REM  [1/4] PULIZIA build precedenti
REM ----------------------------------------------------------
echo [1/4] Pulizia cartelle di build vecchie...
if exist "dist"  rmdir /s /q "dist"
if exist "build" rmdir /s /q "build"
echo    fatto.
echo.

REM ----------------------------------------------------------
REM  [2/4] DIPENDENZE
REM ----------------------------------------------------------
echo [2/4] Aggiorno le dipendenze...
python -m pip install --upgrade pyinstaller customtkinter reportlab pillow adif_io openpyxl pyserial pywin32 skyfield sgp4 matplotlib >nul
echo    fatto.
echo.

REM ----------------------------------------------------------
REM  [3/4] COMPILAZIONE (usa ADIF_FZR.spec)
REM ----------------------------------------------------------
echo [3/4] Compilo l'eseguibile...
echo.
python -m PyInstaller ADIF_FZR.spec --clean --noconfirm
if errorlevel 1 (
    echo.
    echo [ERRORE] Compilazione fallita. Copiami le ultime righe qui sopra.
    pause & exit /b 1
)
if not exist "dist\ADIF_FZR.exe" (
    echo [ERRORE] Non trovo dist\ADIF_FZR.exe dopo la compilazione.
    pause & exit /b 1
)
echo.
echo    Eseguibile creato: dist\ADIF_FZR.exe
echo.

REM ----------------------------------------------------------
REM  [4/4] INSTALLER (Inno Setup)
REM ----------------------------------------------------------
echo [4/4] Creo l'installer...
echo.
set "ISCC=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=C:\Program Files\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" (
    echo [ATTENZIONE] Inno Setup 6 non trovato.
    echo   L'eseguibile pero' e' pronto:  dist\ADIF_FZR.exe
    echo   Per l'installer: installa Inno Setup da https://jrsoftware.org/isdl.php e rilancia.
    pause & exit /b 1
)
if not exist "installer_output" mkdir installer_output
"%ISCC%" "setup_v25_modular.iss"
if errorlevel 1 (
    echo.
    echo [ERRORE] Creazione installer fallita. Copiami le ultime righe qui sopra.
    pause & exit /b 1
)

echo.
echo ==========================================================
echo    TUTTO FATTO!
echo.
echo    Eseguibile : dist\ADIF_FZR.exe
echo    Installer  : installer_output\ADIF_FZR_v2.5_Setup.exe
echo ==========================================================
echo.
echo   NOTA: se hai cambiato lo splash, prima di lanciare questo
echo   bat metti la nuova immagine come  splash.png  nella cartella.
echo.
pause
