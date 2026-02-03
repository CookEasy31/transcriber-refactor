# actScriber - Professionelle Sprach-zu-Text App

Desktop-Anwendung für Echtzeit-Transkription und intelligente Textverarbeitung mit KI-Unterstützung. Entwickelt für juristische und professionelle Anwendungsfälle.

## Features

- **Push-to-Talk Diktat**: Hotkey gedrückt halten → Sprechen → Text wird automatisch eingefügt
- **Intelligente Formatierung**: Automatische juristische Notation (§§, Abs., Art., etc.)
- **Übersetzungsmodus**: Echtzeit-Übersetzung in verschiedene Sprachen
- **Dark/Light Mode**: Automatische Erkennung des Windows-Themes
- **Auto-Updates**: Automatische Prüfung auf neue Versionen via GitHub Releases
- **Per-User Installation**: Keine Admin-Rechte erforderlich
- **Sleep-Mode Recovery**: Automatische Mikrofon-Wiederherstellung nach Energiesparmodus

## Architektur

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   actScriber    │────▶│  Vercel Proxy   │────▶│    Groq API     │
│   (Desktop)     │     │  (Frankfurt)    │     │  (Whisper/LLM)  │
└─────────────────┘     └────────┬────────┘     └─────────────────┘
                                 │
                                 ▼
                        ┌─────────────────┐
                        │    Supabase     │
                        │  (Usage Logs)   │
                        └─────────────────┘
```

## Dateien

| Datei | Beschreibung |
|-------|-------------|
| `main.py` | Haupt-UI (PySide6), ~2500 Zeilen |
| `config.py` | Konfiguration, APP_VERSION, Pfade |
| `api_handler.py` | API-Kommunikation (Proxy oder direkt) |
| `audio_handler.py` | Audio-Aufnahme mit Fallback-Logik + Health-Check |
| `data_handler.py` | SQLite-Logging, History |
| `updater.py` | GitHub Release Update-Checker + Auto-Restart |
| `build_nuitka.py` | Nuitka Build-System (empfohlen) |
| `build_wix.py` | cx_Freeze + WiX Build-System |
| `requirements.txt` | Python-Dependencies |

## API Handler Konfiguration

Der `api_handler.py` unterstützt zwei Modi:

```python
# In api_handler.py
PROXY_BASE_URL = "https://actscriber-proxy.vercel.app"
USE_PROXY = True  # True = Proxy mit Usage-Tracking, False = Direkt zu Groq
```

### Proxy-Endpunkte

| Endpoint | Methode | Beschreibung |
|----------|---------|--------------|
| `/api/transcribe` | POST | Whisper Transkription (multipart/form-data) |
| `/api/chat` | POST | LLM Chat Completion (JSON) |
| `/api/usage` | GET | Admin Dashboard (HTML) |

### User-Tracking

Jeder Request enthält einen `X-User-ID` Header im Format `username@hostname`:
```
X-User-ID: matze@Maetzger
```

## Usage Dashboard

**URL**: `https://actscriber-proxy.vercel.app/api/usage?key=actscriber-admin-2024`

Features:
- Requests/Tokens pro User
- Modell-Statistiken
- Fehler-Log mit Meldungen
- Activity Log (letzte 20 Requests)
- User-Detail-Ansicht (klickbar)
- Auto-Refresh alle 30 Sekunden

## Audio-Fallback-Logik

Der `audio_handler.py` implementiert automatisches Fallback:

1. **Bevorzugtes Gerät** (aus Config)
2. **By-Name Fallback** (falls Gerät-ID sich geändert hat)
3. **System-Default** (als letzter Fallback)

Nützlich für Docking-Station-Szenarien wo sich Device-IDs ändern.

### Sleep-Mode Recovery

Die App prüft alle 10 Sekunden die Audio-Device-Gesundheit:
- Erkennt wenn Mikrofon nach Energiesparmodus nicht mehr verfügbar ist
- Versucht automatisch das Gerät neu zu initialisieren
- Wechselt automatisch auf verfügbare Fallback-Geräte

## Dark Mode

Die App erkennt automatisch das Windows-Theme via Registry:
```
HKCU\SOFTWARE\Microsoft\Windows\CurrentVersion\Themes\Personalize\AppsUseLightTheme
```

## Update-System

- **Repo**: `CookEasy31/transcriber-refactor`
- **Check-Intervall**: Alle 30 Minuten
- **Erster Check**: 3 Sekunden nach App-Start
- **Force Updates**: Release-Titel mit `[FORCE]` oder `[REQUIRED]`
- **Download**: MSI-Installer aus GitHub Release Assets
- **Auto-Restart**: App startet automatisch nach Update neu
- **Keine Admin-Rechte**: User können selbst Updates durchführen

### Version erhöhen

**WICHTIG: Bei Multi-System-Entwicklung immer `git pull` vor Änderungen!**

1. Version in **allen 4 Dateien** aktualisieren:
```python
# config.py (WICHTIGSTE - wird zur Laufzeit verwendet)
APP_VERSION = "2.0.3"

# build_nuitka.py
VERSION = "2.0.3"

# build_wix.py
VERSION = "2.0.3"

# build_msi.py
VERSION = "2.0.3"
```

2. Build erstellen: `python build_wix.py` (oder `build_nuitka.py` mit MSVC)
3. GitHub Release erstellen: `gh release create v2.0.3 actScriber-2.0.3-win64.msi --title "v2.0.3 - Titel"`
4. Änderungen committen und pushen

## Installation (Entwicklung)

```bash
# Dependencies installieren (uv bevorzugt)
uv pip install -r requirements.txt

# App starten
python main.py
```

## Build (MSI Installer)

```bash
# Voraussetzungen:
# - WiX Toolset v6 + Extensions:
dotnet tool install --global wix
wix extension add WixToolset.UI.wixext --global
wix extension add WixToolset.Util.wixext --global

# - cx_Freeze:
pip install cx_Freeze

# Build mit cx_Freeze (empfohlen - funktioniert mit Python 3.13)
python build_wix.py

# Alternativ: Build mit Nuitka (braucht Visual Studio Build Tools)
python build_wix.py
```

Output: `actScriber-X.X.X-win64.msi` (~50 MB mit Nuitka, ~200 MB mit cx_Freeze)

### Installation
- **Installation nach**: `C:\Program Files\actScriber\`
- **Admin-Rechte** nur bei Erstinstallation erforderlich
- **Auto-Updates ohne Admin**: Ordner-Berechtigungen werden bei Installation gesetzt
- User können selbstständig Updates durchführen

## Environment Variables

### Lokal (.env)
```
GROQ_API_KEY=gsk_...
```

### Vercel Proxy
```
GROQ_API_KEY=gsk_...
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_SERVICE_KEY=eyJ...
ADMIN_KEY=actscriber-admin-2024
```

## Proxy Deployment (Vercel)

```bash
cd actscriber-proxy

# Login
vercel login

# Deploy
vercel --prod

# Environment Variables setzen
echo -n "VALUE" | vercel env add VAR_NAME production
```

## Groq Modelle

| Modell | Verwendung |
|--------|------------|
| `whisper-large-v3` | Transkription |
| `moonshotai/kimi-k2-instruct-0905` | LLM (Formatierung, Übersetzung) |
| `llama-3.3-70b-versatile` | Fallback LLM |

## Bekannte Einschränkungen

- Whisper API unterstützt keinen `user` Parameter direkt
- Max 60 Sekunden Timeout pro Request (Vercel Limit)
- Dashboard zeigt max 1000 Logs

## Troubleshooting

### "Invalid API Key" im Dashboard
→ Supabase Service Key prüfen (muss JWT sein: `eyJ...`)

### Transkription langsam
→ Proxy-Latenz ~50-100ms, Region Frankfurt

### Audio-Gerät nicht gefunden
→ App nutzt automatisches Fallback, Log prüfen

## Lizenz

Privates Repository - Interne Nutzung

---

## SESSION-BERICHT 30.01.2026 (WICHTIG - BITTE LESEN!)

### Was ist passiert

1. **Update-Loop bei Clients** - Durch Wechsel des Installationspfades (LocalAppData → Program Files) entstand ein Loop:
   - Alte Clients hatten App in `%LOCALAPPDATA%\actScriber\`
   - Neue MSI (v2.0.3) installierte nach `C:\Program Files\actScriber\`
   - Nach Update startete die ALTE App aus LocalAppData (Shortcut zeigte dorthin)
   - Alte App sah wieder Update → Loop!

2. **Notfall-Stopp** - Alle Releases v2.0.x wurden gelöscht. Aktuell ist **v1.4.0** das neueste Release.

### Aktueller Stand

| Datei | Version | Installationspfad |
|-------|---------|-------------------|
| `config.py` | 2.0.4 | - |
| `build_wix.py` | 2.0.4 | `ProgramFiles64Folder` + `perMachine` |
| `build_nuitka.py` | 2.0.4 | `ProgramFiles64Folder` + `perMachine` |
| `updater.py` | - | Zeigt auf `PROGRAMFILES` |
| GitHub Latest | **v1.4.0** | War `LocalAppDataFolder` |

### PROBLEM: Inkonsistenz!

- **Alte Clients**: App in `%LOCALAPPDATA%\actScriber\`
- **Neue Build-Skripte**: Installieren nach `C:\Program Files\actScriber\`
- **Das verursacht Chaos bei Updates!**

### Was noch zu tun ist

1. **Entscheidung treffen**: EIN Installationspfad für alle - entweder:
   - `LocalAppData` (perUser, keine Admin-Rechte) - **funktionierte früher**
   - `Program Files` (perMachine, Admin bei Install) - **aktuell in Build-Skripten**

2. **Killswitch implementieren**: JSON-Datei auf GitHub die Updates global stoppen kann

3. **Clients aufräumen**: Alte Installationen in LocalAppData UND Program Files entfernen

4. **Sauberes Release**: Erst wenn alles konsistent ist!

### WICHTIGE REGELN

- **NIEMALS** `git push` oder `gh release create` ohne explizite User-Bestätigung!
- **NIEMALS** Installationspfad ändern ohne Migration-Plan für bestehende Clients
- Releases triggern sofort Updates bei ALLEN Clients!

### Dateien die geändert wurden (nicht gepusht!)

- `updater.py` - Auf ZIP-basierte Updates umgestellt (experimentell, nicht getestet)
- Lokale MSI: `actScriber-2.0.4-win64.msi` (nicht releasen!)
- Lokale ZIP: `actScriber-2.0.4-win64.zip` (nicht releasen!)

### Nächste Session

1. Überblick verschaffen über Client-Installationen
2. Entscheidung: LocalAppData oder Program Files?
3. Build-Skripte + updater.py konsistent machen
4. Killswitch implementieren
5. Sauber testen BEVOR Release

---

## SESSION-BERICHT 03.02.2026

### Was wurde gemacht

#### 1. ZIP-basierte Updates implementiert (statt MSI-Extraktion)
**Problem:** MSI-Extraktion via `msiexec /a` war unzuverlässig (Pfade nicht vorhersagbar).

**Lösung:**
- `updater.py` bevorzugt jetzt ZIP-Downloads
- Extraktion via PowerShell `Expand-Archive` (zuverlässig, in Windows eingebaut)
- MSI bleibt als Fallback

#### 2. Robustes Update-Script mit taskkill
**Problem:** "Unzulässiger SHARE-Vorgang" - App war beim Kopieren noch nicht beendet.

**Lösung:** Neues Batch-Script mit:
```batch
[1/5] taskkill /F /IM actScriber.exe     # Aktiv beenden
[2/5] Warte-Schleife (max 30 Sek)        # Sicherstellen dass Prozess weg
[3/5] Expand-Archive / xcopy             # Dateien kopieren
[4/5] Cleanup                            # Temp-Dateien löschen
[5/5] App neu starten                    # Fertig
```

Plus: Schöne formatierte Ausgabe im CMD-Fenster für User.

#### 3. Vercel Cold Start Prevention (Warmup)
**Problem:** Erste API-Anfrage nach 10-15 Min Inaktivität war langsam (Cold Start).

**Lösung:**
- Neuer Endpoint: `GET /api/health` → `{"status": "warm"}`
- Bei Hotkey-Druck: Fire-and-forget Ping (wenn letzter Ping > 9 Min her)
- Läuft async im Hintergrund während User spricht
- Vercel ist warm wenn Aufnahme fertig

**Dateien geändert:**
- `actscriber-proxy/api/health.py` (neu)
- `api_handler.py` (`warmup_proxy_if_needed()`)
- `main.py` (Warmup bei Hotkey-Druck)

#### 4. Build-System erweitert
`build_update.py` unterstützt jetzt:
```bash
python build_update.py 2.1.4           # Nur MSI
python build_update.py 2.1.4 --zip     # Nur ZIP
python build_update.py 2.1.4 --upload  # MSI + GitHub Upload
python build_update.py 2.1.4 --zip --upload  # ZIP + GitHub Upload
```

### Aktueller Stand

| Was | Version/Status |
|-----|----------------|
| `config.py` | 2.1.4 |
| GitHub Latest | v1.4.0 (Kill-Switch von früher) |
| GitHub Draft | v2.1.4 (für IT-Rollout) |
| Vercel Proxy | Deployed mit /api/health |

### Installationspfade (FINAL ENTSCHIEDEN)

```
Installation:    C:\Program Files\actScriber\     (Admin bei Install)
                 → PermissionEx User="Users" GenericAll="yes"
                 → User können danach ohne Admin updaten!

Einstellungen:   %LOCALAPPDATA%\act Scriber\      (MIT Leerzeichen!)
                 ├── settings.json
                 ├── history.db
                 └── updates\

Alte Installation: %LOCALAPPDATA%\actScriber\     (OHNE Leerzeichen)
                   → Muss bei Rollout gelöscht werden!
```

### v2.1.4 Release (Draft - nicht öffentlich)

**Download:** https://github.com/CookEasy31/transcriber-refactor/releases/tag/untagged-8a5211fd905785f9d184

**Enthält:**
- ZIP-basierter Updater
- Warmup für Vercel Cold Start
- taskkill + Warte-Schleife für saubere Updates
- Formatierte CMD-Ausgabe beim Update

### IT-Rollout Plan

```bash
# 1. Deinstallieren (alle Clients)
- "act Scriber" über Systemsteuerung entfernen
- Ordner löschen: %LOCALAPPDATA%\actScriber\  (alte Installation)
- NICHT löschen: %LOCALAPPDATA%\act Scriber\  (Einstellungen!)

# 2. Installieren
msiexec /i actScriber-2.1.4-win64.msi /qn

# 3. Fertig
- App in: C:\Program Files\actScriber\
- Shortcuts auf Desktop + Startmenü
- User-Rechte für künftige Updates gesetzt
```

### Nächste Schritte

1. **IT-Rollout durchführen** (manuell via IT-Tool)
2. **Testen** auf einem Client zuerst
3. **Später:** Wenn Update gewünscht:
   - Neue Version bauen (z.B. v2.1.5)
   - ZIP erstellen und als GitHub Release veröffentlichen
   - Clients laden automatisch herunter

### Wichtige Regeln (unverändert)

- **NIEMALS** `gh release create` ohne explizite User-Bestätigung
- Draft Releases sind sicher (Clients sehen sie nicht)
- Erst publizieren wenn IT-Rollout abgeschlossen
