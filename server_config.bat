@echo off
rem Optionale zentrale Konfiguration fuer den Netzwerkbetrieb.
rem Diese Datei wird von allen Start-/Oeffnen-Skripten automatisch geladen.

rem Gemeinsamer Port fuer den Live-Server.
if not defined FRISTEN_SERVER_PORT set "FRISTEN_SERVER_PORT=8502"

rem Optional: Nur dieser Rechner darf den Server starten.
rem Leer lassen, damit die Startdateien auf jedem Rechner funktionieren.
rem Beispiel: set "FRISTEN_SERVER_FIXED_PC=WERKSTATT-PC-01"
set "FRISTEN_SERVER_FIXED_PC="

rem Optional: Hostname/IP, die Clients nutzen sollen.
rem Beispiel: set "FRISTEN_SERVER_PUBLIC_HOST=werkstatt-pc-01"
rem Leer lassen, damit automatisch die aktuelle LAN-IP ermittelt wird.
set "FRISTEN_SERVER_PUBLIC_HOST="

rem Optional: Lokaler Pfad fuer die Python-Umgebung auf dem Server-PC.
rem Default ohne Eintrag: %LOCALAPPDATA%\FristenLiveV1\venv
rem set "FRISTEN_SERVER_VENV_DIR=C:\FristenLiveV1\venv"

rem Optional: Gemeinsame URL-Datei auf einem internen Server (UNC oder Laufwerkspfad).
rem Beispiel: set "FRISTEN_SERVER_URL_FILE=\\fileserver\werkstatt\fristen_live_v1\live_server_url.txt"
rem set "FRISTEN_SERVER_URL_FILE="

rem Optional: Feste URL fuer alle Clients (hat Vorrang vor URL-Datei).
rem Beispiel: set "FRISTEN_SERVER_URL=http://werkstatt-pc-01:8502/"
rem set "FRISTEN_SERVER_URL="
