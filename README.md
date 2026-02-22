# act Scriber - Professionelle Sprach-zu-Text App

Desktop-Anwendung für Echtzeit-Transkription und intelligente Textverarbeitung mit KI-Unterstützung. Entwickelt für juristische und professionelle Anwendungsfälle.

## Aktuelle Version: 2.2.3

## Features

- **Push-to-Talk Diktat**: Hotkey gedrückt halten → Sprechen → Text wird automatisch eingefügt
- **Intelligente Formatierung**: Automatische juristische Notation (§§, Abs., Art., etc.)
- **Übersetzungsmodus**: Echtzeit-Übersetzung in verschiedene Sprachen
- **Dark/Light Mode**: Automatische Erkennung des Windows-Themes
- **Auto-Updates**: ZIP-basierte Updates via GitHub Releases (silent, kein Admin nötig)
- **Vercel Warmup**: Automatischer Cold-Start-Prevention bei Hotkey-Druck
- **Sleep-Mode Recovery**: Automatische Mikrofon-Wiederherstellung nach Energiesparmodus

## Architektur

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   act Scriber   │────▶│  Vercel Proxy   │────▶│    Groq API     │
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
| `main.py` | Haupt-UI (PySide6) |
| `config.py` | Konfiguration, APP_VERSION, Pfade |
| `api_handler.py` | API-Kommunikation (Proxy oder direkt) |
| `audio_handler.py` | Audio-Aufnahme mit Fallback-Logik + Health-Check |
| `data_handler.py` | SQLite-Logging, History |
| `updater.py` | GitHub Release Update-Checker + ZIP-Updater |
| `build_nuitka.py` | Nuitka Build-System (empfohlen) |
| `build_wix.py` | WiX Build-System (alternativ) |
| `build_msi.py` | cx_Freeze Build (legacy) |
| `requirements.txt` | Python-Dependencies |

---

## PFADE UND KONSISTENZ (WICHTIG!)

### Feste Pfade — NIEMALS ändern!

```
Installation:       C:\Program Files\act Scriber\      (MIT Leerzeichen!)
                    ├── actScriber.exe
                    ├── .env
                    └── (alle DLLs, Daten, etc.)

Einstellungen:      %LOCALAPPDATA%\act Scriber\        (MIT Leerzeichen!)
                    ├── settings.json
                    ├── history.db
                    ├── updates\
                    └── update.log

Executable-Name:    actScriber.exe                     (OHNE Leerzeichen!)
```

### Wo diese Pfade definiert sind

| Pfad | Datei | Zeile/Stelle |
|------|-------|-------------|
| Install-Ordner MSI | `build_nuitka.py` | `APP_DISPLAY_NAME` → WiX `Directory Name=` |
| Install-Ordner Updater (ZIP) | `updater.py` | `'act Scriber'` in `install_zip_update()` |
| Install-Ordner Updater (MSI) | `updater.py` | `'act Scriber'` in `install_msi_update()` |
| Einstellungs-Ordner | `config.py` | `APP_NAME = "act Scriber"` → `APP_DATA_DIR` |

### Version — wo sie definiert ist

Die Version muss in **allen 4 Dateien identisch** sein:

```python
# config.py          ← wird zur Laufzeit verwendet (Updater vergleicht diese!)
APP_VERSION = "2.2.3"

# build_nuitka.py    ← wird in EXE-Metadaten + Dateinamen eingebettet
VERSION = "2.2.3"

# build_wix.py       ← wird in MSI-Metadaten eingebettet
VERSION = "2.2.3"

# build_msi.py       ← legacy, trotzdem synchron halten
VERSION = "2.2.3"
```

---

## Update-System — So funktioniert es

### Wie der Updater arbeitet

1. App prüft alle **30 Minuten** (erster Check: 3 Sek. nach Start)
2. Ruft `https://api.github.com/repos/CookEasy31/transcriber-refactor/releases/latest` ab
3. Vergleicht `APP_VERSION` (config.py) mit Release `tag_name`
4. Sucht nach `.zip` Asset (bevorzugt) oder `.msi` Asset (Fallback)
5. Bei ZIP: Download → PowerShell-Script → wartet bis App beendet → entpackt nach `C:\Program Files\act Scriber\` → startet neu

### Was ein Update TRIGGERT

- Ein **veröffentlichtes** GitHub Release (NICHT Draft, NICHT Pre-Release)
- Release-Version muss **höher** sein als `APP_VERSION` in `config.py`
- Release muss ein Asset mit `actScriber` im Namen und `.zip`-Endung haben

### Was ein Update NICHT triggert

- **Draft Releases** — unsichtbar für `/releases/latest`
- **Pre-Releases** — unsichtbar für `/releases/latest`
- **Normaler `git push`** — Updater prüft nur Releases, nicht Commits

---

## Neues Update ausrollen — Schritt für Schritt

### 1. Version erhöhen (alle 4 Dateien!)

```python
# config.py, build_nuitka.py, build_wix.py, build_msi.py
# Alle auf die GLEICHE neue Version setzen, z.B.:
"2.2.4"
```

### 2. Build erstellen

```bash
# Nuitka-Build (erstellt ZIP automatisch)
python build_nuitka.py

# MSI separat bauen (WiX muss installiert sein):
wix build Package.wxs -arch x64 \
  -ext WixToolset.Util.wixext \
  -ext WixToolset.UI.wixext \
  -b build\exe.win-amd64-3.12 \
  -b . \
  -o actScriber-X.X.X-win64.msi
```

**Output:**
- `actScriber-X.X.X-win64.zip` (66 MB) — für Auto-Updates
- `actScriber-X.X.X-win64.msi` (51 MB) — für Erstinstallation

### 3. Committen und pushen

```bash
git add config.py build_nuitka.py build_wix.py build_msi.py
git commit -m "chore: bump version to X.X.X"
git push origin main
```

### 4a. Update ausrollen (ZIP für bestehende Clients)

```bash
# ACHTUNG: Das triggert sofort Updates bei ALLEN Clients!
gh release create vX.X.X \
  actScriber-X.X.X-win64.zip \
  --title "vX.X.X - Beschreibung" \
  --notes "Changelog hier"
```

### 4b. Nur zum Testen hochladen (Draft — kein Auto-Update)

```bash
gh release create vX.X.X \
  actScriber-X.X.X-win64.msi \
  --draft \
  --title "vX.X.X - Test" \
  --notes "Interner Test"
```

---

## Erstinstallation (neue Clients)

```bash
# MSI installieren (Admin-Rechte nötig)
msiexec /i actScriber-X.X.X-win64.msi

# Oder silent:
msiexec /i actScriber-X.X.X-win64.msi /qn
```

Die MSI:
- Installiert nach `C:\Program Files\act Scriber\`
- Setzt User-Berechtigungen (für spätere ZIP-Updates ohne Admin)
- Erstellt Desktop- und Startmenü-Shortcuts

---

## Installation (Entwicklung)

```bash
# Dependencies installieren
pip install -r requirements.txt

# App starten
python main.py
```

### Build-Voraussetzungen

```bash
# Nuitka
pip install nuitka ordered-set zstandard

# .NET SDK (für WiX)
winget install Microsoft.DotNet.SDK.8

# WiX v6
dotnet tool install --global wix
wix extension add WixToolset.Util.wixext
wix extension add WixToolset.UI.wixext
```

## API Handler Konfiguration

```python
# In api_handler.py
PROXY_BASE_URL = "https://actscriber-proxy.vercel.app"
USE_PROXY = True  # True = Proxy mit Usage-Tracking, False = Direkt zu Groq
```

### Proxy-Endpunkte

| Endpoint | Methode | Beschreibung |
|----------|---------|--------------|
| `/api/transcribe` | POST | Whisper Transkription |
| `/api/chat` | POST | LLM Chat Completion |
| `/api/health` | GET | Warmup-Ping |
| `/api/usage` | GET | Admin Dashboard |

## Groq Modelle

| Modell | Verwendung |
|--------|------------|
| `whisper-large-v3` | Transkription |
| `moonshotai/kimi-k2-instruct-0905` | LLM (Formatierung, Übersetzung) |
| `llama-3.3-70b-versatile` | Fallback LLM |

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

## Wichtige Regeln

- **NIEMALS** `gh release create` ohne `--draft` wenn nicht explizit gewollt — das triggert sofort alle Clients!
- **NIEMALS** Installationspfad ändern — bestehende Clients updaten dann ins Leere
- **NIEMALS** Versions-Dateien einzeln ändern — immer alle 4 gleichzeitig
- Draft Releases sind sicher (Clients sehen sie nicht)

## Lizenz

Privates Repository - Interne Nutzung (act legal IT)
