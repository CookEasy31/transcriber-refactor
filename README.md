# actScriber - Professionelle Sprach-zu-Text App

Desktop-Anwendung für Echtzeit-Transkription und intelligente Textverarbeitung mit KI-Unterstützung. Entwickelt für juristische und professionelle Anwendungsfälle.

## Features

- **Push-to-Talk Diktat**: Hotkey gedrückt halten → Sprechen → Text wird automatisch eingefügt
- **Intelligente Formatierung**: Automatische juristische Notation (§§, Abs., Art., etc.)
- **Übersetzungsmodus**: Echtzeit-Übersetzung in verschiedene Sprachen
- **Dark/Light Mode**: Automatische Erkennung des Windows-Themes
- **Auto-Updates**: Automatische Prüfung auf neue Versionen via GitHub Releases

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
| `audio_handler.py` | Audio-Aufnahme mit Fallback-Logik |
| `data_handler.py` | SQLite-Logging, History |
| `updater.py` | GitHub Release Update-Checker |
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

### Version erhöhen

In `config.py`:
```python
APP_VERSION = "1.3.7"  # Semantic Versioning
```

GitHub Release Tag muss `v1.3.7` Format haben.

## Installation (Entwicklung)

```bash
# Dependencies installieren (uv bevorzugt)
uv pip install -r requirements.txt

# App starten
python main.py
```

## Build (MSI Installer)

```bash
# Voraussetzung: WiX Toolset v3 installiert
python build_wix.py
```

Output: `dist/actScriber-X.X.X-win64.msi`

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
