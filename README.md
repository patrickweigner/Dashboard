# Fristenplanung Live V1 (NiceGUI)

Lauffähige Nicht-Streamlit-Version mit:

- Live-Dashboard (Auto-Refresh alle 2 Sekunden)
- Werkstatthalle-Ansicht (4A/4B/5A/5B/URD)
- Upload-Seite für Excel (`Fzg Zusatzarbeiten`)
- Archiv-Seite
- Upsert in die bestehende Tabelle `open_tasks`
- Aktionen direkt im Dashboard:
  - `Erledigt` (Archivierung)
  - `Problem speichern`
  - Bereich-Zuordnung
- Nutzung der vorhandenen Datei `fristenplanung.db`

## 1) Start (Windows)

Server + Vollbild-App starten (im Ordner `fristen_live_v1`):

```bat
Start Fristen Live App.bat
```

Browser öffnen (im Hauptordner):

```bat
Oeffne Fristendashboard.bat
```

Verhalten:

- `fristen_live_v1\Start Fristen Live App.bat` startet den Netzwerk-Server und die lokale Vollbild-App.
- `fristen_live_v1\server_config.bat` steuert optionalen festen Server-Rechner, Hostname, Port und optionale zentrale URL-Datei.
- `Oeffne Fristendashboard.bat` im Hauptordner öffnet die feste URL/Hostname aus `server_config.bat` oder die gespeicherte URL-Datei.
- Im Hauptordner gibt es nur diese eine Client-Datei: `Oeffne Fristendashboard.bat`.
- Die Python-Umgebung wird standardmäßig lokal auf dem Server-PC angelegt (`%LOCALAPPDATA%\FristenLiveV1\venv`).
- Wenn eine alte/ungültige Python-Umgebung gefunden wird, wird sie automatisch neu erstellt.

Danach im Browser:

- `http://127.0.0.1:8502` (Startseite)
- Offene Aufträge: `http://127.0.0.1:8502/offen`
- Werkstatthalle: `http://127.0.0.1:8502/werkstatthalle`
- Priorisierung: `http://127.0.0.1:8502/priorisierung`
- 5S-Plan: `http://127.0.0.1:8502/shopfloorboard`
- Upload-Seite: `http://127.0.0.1:8502/upload`
- Archiv: `http://127.0.0.1:8502/archiv`

## 2) Netzwerkbetrieb von jedem Rechner

1. Projektordner auf dem internen Server ablegen (gemeinsame Freigabe für alle Clients).
2. Datei `fristen_live_v1\server_config.bat` anpassen:

```bat
set "FRISTEN_SERVER_PUBLIC_HOST=werkstatt-pc-01"
set "FRISTEN_SERVER_PORT=8502"
set "FRISTEN_SERVER_URL_FILE=\\fileserver\werkstatt\fristen_live_v1\live_server_url.txt"
```

3. Optional: Wenn nur ein bestimmter Rechner den Server starten darf, zusätzlich setzen:

```bat
set "FRISTEN_SERVER_FIXED_PC=WERKSTATT-PC-01"
```

4. Den Server bei Bedarf auf jedem Rechner mit `Start Fristen Live App.bat` oder `Start Live V1.bat` starten.
5. Alternativ nur `Oeffne Fristendashboard.bat` nutzen, wenn bereits ein Server läuft.

Wirkung:

- Serverstart ist standardmäßig auf jedem Rechner möglich.
- Wenn `FRISTEN_SERVER_FIXED_PC` gesetzt ist, wird der Serverstart auf andere Rechner blockiert.
- Alle Clients nutzen dieselbe URL/Hostname.
- Optional wird die aktuelle URL zentral auf dem internen Server abgelegt.

## 3) Manuell starten

```bat
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

## 4) Konfiguration per Umgebungsvariablen

- `FRISTEN_DB_PATH` (optional): Pfad zur SQLite-Datei  
  Default: `./fristenplanung.db` (im Ordner `fristen_live_v1`)
- `FRISTEN_LIVE_HOST` (optional): Default `0.0.0.0`
- `FRISTEN_LIVE_PORT` (optional): Default `8502`
- `NOTIFY_FLOW_URL` (optional): Webhook für Verzögerungen, LWU und Archiv-Benachrichtigungen

Beispiel:

```bat
set FRISTEN_DB_PATH=C:\Pfad\zu\fristenplanung.db
set FRISTEN_LIVE_PORT=8510
set NOTIFY_FLOW_URL=https://...
python main.py
```

## 5) Nächste Ausbaustufen

Sinnvolle nächste Schritte:

- Priorisierung (Timeline-Details auf Streamlit-Niveau angleichen)
- 5S-Plan (Admin-/Freigabe-Logik angleichen)
- Admin-Freigaben/Rollen
- ECM4-Import-Diff und LWU-Logik
