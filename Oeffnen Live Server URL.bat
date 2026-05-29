@echo off
setlocal EnableExtensions EnableDelayedExpansion

pushd "%~dp0" >nul 2>&1
if errorlevel 1 (
  echo [FEHLER] Arbeitsverzeichnis konnte nicht geoeffnet werden:
  echo %~dp0
  pause
  exit /b 1
)

set "CONFIG_FILE=server_config.bat"
if exist "%CONFIG_FILE%" call "%CONFIG_FILE%"

set "LIVE_URL=%FRISTEN_SERVER_URL%"
if not defined LIVE_URL (
  set "PUBLIC_HOST=%FRISTEN_SERVER_PUBLIC_HOST%"
  set "LIVE_PORT=%FRISTEN_SERVER_PORT%"
  if not defined LIVE_PORT set "LIVE_PORT=8502"
  if defined PUBLIC_HOST set "LIVE_URL=http://%PUBLIC_HOST%:%LIVE_PORT%/"
)

if not defined LIVE_URL (
  set "URL_FILE=%FRISTEN_SERVER_URL_FILE%"
  if not defined URL_FILE set "URL_FILE=live_server_url.txt"

  if not exist "!URL_FILE!" goto :missing

  set /p LIVE_URL=<"!URL_FILE!"
)
if not defined LIVE_URL goto :missing

echo [Open] Oeffne %LIVE_URL%
start "" "%LIVE_URL%"
popd
goto :eof

:missing
echo [Hinweis] Keine gespeicherte Server-URL gefunden.
echo Bitte zuerst den Server starten oder "server_config.bat" pruefen.
echo [Info] Erwartete URL-Datei: %URL_FILE%
popd
pause
exit /b 1
