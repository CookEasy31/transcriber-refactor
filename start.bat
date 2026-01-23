@echo off
setlocal

:: Wechsle ins Skript-Verzeichnis
cd /d "%~dp0"

:: Automatische Erkennung der Python-Umgebung
:: Conda: venv\python.exe | Standard-venv: venv\Scripts\python.exe

if exist "venv\python.exe" (
    set "PYTHON_EXE=venv\python.exe"
) else if exist "venv\Scripts\python.exe" (
    set "PYTHON_EXE=venv\Scripts\python.exe"
) else if exist ".venv\Scripts\python.exe" (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
) else (
    echo [FEHLER] Keine virtuelle Umgebung gefunden!
    pause
    exit /b 1
)

:: App starten (optimiert: -O fuer schnelleren Start)
"%PYTHON_EXE%" -O main.py

if %ERRORLEVEL% NEQ 0 (
    echo [FEHLER] App wurde unerwartet beendet.
    pause
)

endlocal
