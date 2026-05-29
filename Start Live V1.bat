@echo off
setlocal EnableExtensions

cd /d "%~dp0"
title Fristenplanung Live V1 (NiceGUI)
set "CONFIG_FILE=server_config.bat"
if exist "%CONFIG_FILE%" call "%CONFIG_FILE%"

set "LIVE_PORT=%FRISTEN_SERVER_PORT%"
if not defined LIVE_PORT set "LIVE_PORT=8502"
set "FRISTEN_LIVE_PORT=%LIVE_PORT%"

set "FIXED_PC=%FRISTEN_SERVER_FIXED_PC%"
if defined FIXED_PC if /I not "%COMPUTERNAME%"=="%FIXED_PC%" (
  echo [FEHLER] Dieser Rechner darf den Live-Server nicht starten.
  echo [Info] Erlaubter Rechner: %FIXED_PC%
  echo [Info] Aktueller Rechner: %COMPUTERNAME%
  echo [Hinweis] Die Einschraenkung kommt aus "server_config.bat".
  pause
  exit /b 1
)

set "PUBLIC_HOST=%FRISTEN_SERVER_PUBLIC_HOST%"
if defined PUBLIC_HOST (
  set "LIVE_URL=http://%PUBLIC_HOST%:%LIVE_PORT%/"
) else (
  set "LIVE_URL=http://127.0.0.1:%LIVE_PORT%/"
)
set "VENV_DIR=%FRISTEN_SERVER_VENV_DIR%"
if not defined VENV_DIR (
  if defined LOCALAPPDATA (
    set "VENV_DIR=%LOCALAPPDATA%\FristenLiveV1\venv"
  ) else (
    set "VENV_DIR=.venv"
  )
)
set "PY_EXE=%VENV_DIR%\Scripts\python.exe"

call :open_if_running
if not errorlevel 1 goto :eof

call :ensure_python_runtime
if errorlevel 1 goto :fail

set "REQ_MARKER=%VENV_DIR%\.requirements_installed"
powershell -NoProfile -Command "if(!(Test-Path -LiteralPath '%REQ_MARKER%')){exit 1}; if((Get-Item -LiteralPath 'requirements.txt').LastWriteTimeUtc -gt (Get-Item -LiteralPath '%REQ_MARKER%').LastWriteTimeUtc){exit 1}; exit 0" >nul 2>&1
if errorlevel 1 (
  echo [Setup] Installiere/aktualisiere Pakete...
  "%PY_EXE%" -m pip install --upgrade pip
  "%PY_EXE%" -m pip install -r requirements.txt
  if errorlevel 1 goto :fail
  powershell -NoProfile -Command "New-Item -ItemType File -Path '%REQ_MARKER%' -Force | Out-Null" >nul 2>&1
) else (
  echo [Setup] Pakete sind aktuell.
)

echo [Setup] Beende ggf. alte Prozesse auf Port %LIVE_PORT% ...
for /f %%P in ('powershell -NoProfile -Command "(Get-NetTCPConnection -LocalPort %LIVE_PORT% -State Listen -ErrorAction SilentlyContinue ^| Select-Object -ExpandProperty OwningProcess -Unique)"') do (
  taskkill /PID %%P /T /F >nul 2>&1
)
echo [Setup] Warte bis Port %LIVE_PORT% frei ist ...
powershell -NoProfile -Command "$deadline=(Get-Date).AddSeconds(10); while((Get-Date) -lt $deadline){ if(-not (Get-NetTCPConnection -LocalPort %LIVE_PORT% -State Listen -ErrorAction SilentlyContinue)){ exit 0 }; Start-Sleep -Milliseconds 250 }; exit 1"
if errorlevel 1 (
  call :open_if_running
  if not errorlevel 1 goto :eof
  goto :port_busy
)

echo [Setup] Pruefe Datenbank-Schreibzugriff ...
"%PY_EXE%" db_lock_check.py
if errorlevel 2 goto :db_locked
if errorlevel 1 goto :db_check_failed

echo [Start] Starte Live V1 auf %LIVE_URL%
start "" powershell -NoProfile -WindowStyle Hidden -Command "$u='%LIVE_URL%'; for($i=0; $i -lt 120; $i++){ try { Invoke-WebRequest -Uri $u -UseBasicParsing -TimeoutSec 1 | Out-Null; Start-Process $u; exit 0 } catch { Start-Sleep -Milliseconds 500 } }; Start-Process $u"
"%PY_EXE%" main.py
if errorlevel 1 goto :runtime_fail
goto :eof

:open_if_running
powershell -NoProfile -Command "try { Invoke-WebRequest -Uri '%LIVE_URL%' -UseBasicParsing -TimeoutSec 2 | Out-Null; exit 0 } catch { exit 1 }" >nul 2>&1
if errorlevel 1 exit /b 1
echo [Start] Live V1 laeuft bereits. Oeffne %LIVE_URL%
start "" "%LIVE_URL%"
exit /b 0

:port_busy
echo [FEHLER] Port %LIVE_PORT% ist weiterhin belegt.
echo [Hinweis] Bitte pruefen, welcher Prozess den Port blockiert.
powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort %LIVE_PORT% -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object { Get-CimInstance Win32_Process -Filter ('ProcessId=' + $_) | Select-Object ProcessId,Name,CommandLine | Format-List }"
pause
exit /b 1

:runtime_fail
echo [FEHLER] Live-Server wurde mit Fehler beendet.
echo [Hinweis] Die Meldungen oben enthalten die Ursache.
pause
exit /b 1

:db_locked
echo [FEHLER] Die SQLite-Datenbank ist durch einen anderen Prozess gesperrt.
echo [Hinweis] Schliessen Sie alle offenen Live-V1-Fenster und Python-Prozesse, die zu dieser App gehoeren.
echo [Hinweis] Falls kein Fenster sichtbar ist: Im Task-Manager python.exe beenden oder Windows neu starten.
echo [Info] Aktive Python-Prozesse:
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='python.exe' OR Name='pythonw.exe'\" | Where-Object { $_.CommandLine -notmatch 'db_lock_check\\.py' -and ($_.CommandLine -match 'fristen_live_v1|FristenLiveV1|main\\.py|nicegui') } | Select-Object ProcessId,Name,CommandLine | Format-List"
echo [Info] Falls hier kein Prozess angezeigt wird, liegt die Sperre wahrscheinlich auf einem anderen Rechner
echo [Info] oder als haengende Dateisperre auf dem Netzlaufwerk.
pause
exit /b 1

:db_check_failed
echo [FEHLER] Die Datenbank-Pruefung konnte nicht ausgefuehrt werden.
echo [Hinweis] Die Meldungen direkt oberhalb enthalten die eigentliche Ursache.
echo [Hinweis] Das ist keine SQLite-Sperre, sondern ein Start-/Importproblem.
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

