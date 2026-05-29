@echo off
setlocal EnableExtensions EnableDelayedExpansion

cd /d "%~dp0"
title Fristenplanung Live V1 (Desktop App + Server)

set "CONFIG_FILE=server_config.bat"
if exist "%CONFIG_FILE%" call "%CONFIG_FILE%"

set "LIVE_PORT=%FRISTEN_SERVER_PORT%"
if not defined LIVE_PORT set "LIVE_PORT=8502"

set "URL_FILE=%FRISTEN_SERVER_URL_FILE%"
if not defined URL_FILE set "URL_FILE=live_server_url.txt"

set "FIXED_PC=%FRISTEN_SERVER_FIXED_PC%"
if defined FIXED_PC if /I not "%COMPUTERNAME%"=="%FIXED_PC%" goto :wrong_pc

set "PUBLIC_HOST=%FRISTEN_SERVER_PUBLIC_HOST%"
set "LIVE_IP="
set "LIVE_URL="
set "VENV_DIR=%FRISTEN_SERVER_VENV_DIR%"
if not defined VENV_DIR (
  if defined LOCALAPPDATA (
    set "VENV_DIR=%LOCALAPPDATA%\FristenLiveV1\venv"
  ) else (
    set "VENV_DIR=.venv"
  )
)
set "PY_EXE=%VENV_DIR%\Scripts\python.exe"

call :ensure_python_runtime
if errorlevel 1 goto :fail

echo [Setup] Installiere/aktualisiere Pakete...
"%PY_EXE%" -m pip install --upgrade pip
"%PY_EXE%" -m pip install -r requirements.txt
if errorlevel 1 goto :fail

if not defined PUBLIC_HOST (
  echo [Setup] Ermittle aktuelle LAN-IP...
  for /f "tokens=2 delims=:" %%I in ('ipconfig ^| findstr /R /C:"IPv4.*:"') do (
    set "CAND=%%I"
    set "CAND=!CAND: =!"

    if not "!CAND!"=="" if /I not "!CAND!"=="127.0.0.1" if /I not "!CAND:~0,8!"=="169.254." (
      if not defined LIVE_IP set "LIVE_IP=!CAND!"

      rem Bevorzuge private Netzbereiche
      if "!CAND:~0,8!"=="192.168." set "LIVE_IP=!CAND!"
      if "!CAND:~0,3!"=="10." set "LIVE_IP=!CAND!"
      for /f "tokens=1,2 delims=." %%A in ("!CAND!") do (
        if "%%A"=="172" (
          if %%B GEQ 16 if %%B LEQ 31 set "LIVE_IP=!CAND!"
        )
      )
    )
  )

  if not defined LIVE_IP (
    echo [Warnung] Konnte keine LAN-IP ermitteln. Fallback: 127.0.0.1
    set "LIVE_IP=127.0.0.1"
  )

  set "PUBLIC_HOST=!LIVE_IP!"
)

set "LIVE_URL=http://%PUBLIC_HOST%:%LIVE_PORT%/"
for %%F in ("%URL_FILE%") do set "URL_DIR=%%~dpF"
if not exist "%URL_DIR%" mkdir "%URL_DIR%" >nul 2>&1
> "%URL_FILE%" echo %LIVE_URL%

echo [Info] Server-URL: %LIVE_URL%
echo [Info] URL-Datei: %URL_FILE%

echo [Setup] Beende ggf. alte Prozesse auf Port %LIVE_PORT% ...
for /f %%P in ('powershell -NoProfile -Command "(Get-NetTCPConnection -LocalPort %LIVE_PORT% -State Listen -ErrorAction SilentlyContinue ^| Select-Object -ExpandProperty OwningProcess -Unique)"') do (
  taskkill /PID %%P /F >nul 2>&1
)
echo [Setup] Warte bis Port %LIVE_PORT% frei ist ...
powershell -NoProfile -Command "$deadline=(Get-Date).AddSeconds(10); while((Get-Date) -lt $deadline){ if(-not (Get-NetTCPConnection -LocalPort %LIVE_PORT% -State Listen -ErrorAction SilentlyContinue)){ exit 0 }; Start-Sleep -Milliseconds 250 }; exit 1"
if errorlevel 1 goto :port_busy

set "FRISTEN_LIVE_NATIVE=1"
set "FRISTEN_LIVE_HOST=0.0.0.0"
set "FRISTEN_LIVE_PORT=%LIVE_PORT%"

echo [Start] Starte Fristenplanung Live V1 als Desktop-App (Vollbild) und Server auf %LIVE_URL%...
"%PY_EXE%" main.py
if errorlevel 1 goto :runtime_fail
goto :eof

:wrong_pc
echo [FEHLER] Dieser Rechner darf den Live-Server nicht starten.
echo [Info] Erlaubter Rechner: %FIXED_PC%
echo [Info] Aktueller Rechner: %COMPUTERNAME%
echo [Hinweis] Die Einschraenkung kommt aus "server_config.bat".
pause
exit /b 1

:port_busy
echo [FEHLER] Port %LIVE_PORT% ist weiterhin belegt.
echo [Hinweis] Bitte pruefen, welcher Prozess den Port blockiert.
pause
exit /b 1

:runtime_fail
echo [FEHLER] Desktop-App wurde mit Fehler beendet.
echo [Hinweis] Die Meldungen oben enthalten die Ursache.
pause
exit /b 1

:ensure_python_runtime
if exist "%PY_EXE%" (
  "%PY_EXE%" -c "import sys" >nul 2>&1
  if not errorlevel 1 exit /b 0
  echo [Setup] Vorhandene Python-Umgebung ist ungueltig. Erstelle sie neu...
  if exist "%VENV_DIR%" rmdir /s /q "%VENV_DIR%" >nul 2>&1
)

call :find_bootstrap_python
if errorlevel 1 (
  echo [FEHLER] Kein Python gefunden: py oder python oder python3.
  echo [Hinweis] Bitte Python auf dem Server-Rechner installieren.
  exit /b 1
)

for %%F in ("%VENV_DIR%") do set "VENV_PARENT=%%~dpF"
if defined VENV_PARENT if not exist "%VENV_PARENT%" mkdir "%VENV_PARENT%" >nul 2>&1

echo [Setup] Erstelle virtuelle Umgebung in "%VENV_DIR%" mit %BOOTSTRAP_PY%...
%BOOTSTRAP_PY% -m venv "%VENV_DIR%"
if errorlevel 1 exit /b 1

if not exist "%PY_EXE%" (
  echo [FEHLER] Python in "%VENV_DIR%" konnte nicht erstellt werden.
  exit /b 1
)
exit /b 0

:find_bootstrap_python
set "BOOTSTRAP_PY="

where py >nul 2>&1
if not errorlevel 1 (
  py -3 -c "import sys" >nul 2>&1
  if not errorlevel 1 (
    set "BOOTSTRAP_PY=py -3"
    exit /b 0
  )
  py -c "import sys" >nul 2>&1
  if not errorlevel 1 (
    set "BOOTSTRAP_PY=py"
    exit /b 0
  )
)

where python >nul 2>&1
if not errorlevel 1 (
  python -c "import sys" >nul 2>&1
  if not errorlevel 1 (
    set "BOOTSTRAP_PY=python"
    exit /b 0
  )
)

where python3 >nul 2>&1
if not errorlevel 1 (
  python3 -c "import sys" >nul 2>&1
  if not errorlevel 1 (
    set "BOOTSTRAP_PY=python3"
    exit /b 0
  )
)

exit /b 1

:fail
echo [FEHLER] Start fehlgeschlagen.
pause
exit /b 1

