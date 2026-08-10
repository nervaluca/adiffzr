@echo off
REM ===== Compila ADIF FZR (struttura a moduli) =====
REM Lancia questo file DENTRO la cartella ADIF_FZR_Modular (dove c'e' main.py)

pushd "%~dp0"

echo Installo/aggiorno le dipendenze...
python -m pip install --upgrade pyinstaller customtkinter reportlab pillow adif_io openpyxl pyserial pywin32

echo.
echo Compilo...
python -m PyInstaller ADIF_FZR.spec --clean --noconfirm

echo.
echo Fatto. L'eseguibile e' in:  dist\ADIF_FZR.exe
popd
pause
