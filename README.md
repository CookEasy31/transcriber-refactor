# ACT Scriber - PySide6 Edition

> **⚠️ WORK IN PROGRESS**: Diese Version befindet sich noch in aktiver Entwicklung. Einige UI-Elemente und Funktionen sind noch nicht vollständig implementiert.

## Übersicht

ACT Scriber ist eine Desktop-Anwendung für Sprachtranskription und -verarbeitung mit KI-Unterstützung.

## Aktuelle Dateien

| Datei              | Beschreibung                   |
| ------------------ | ------------------------------ |
| `main.py`          | Hauptanwendung (PySide6-UI)    |
| `config.py`        | Konfigurationsmanagement       |
| `api_handler.py`   | Groq API Integration           |
| `audio_handler.py` | Audio-Aufnahme mit sounddevice |
| `data_handler.py`  | Datenbank und Logging          |
| `requirements.txt` | Python-Abhängigkeiten          |

## Assets

- `icon.ico` - Anwendungs-Icon
- `act_scriber_transparent.png` - Logo
- `act_only_transparent.png` - Kompakt-Logo

## Ordner

| Ordner                | Beschreibung                      |
| --------------------- | --------------------------------- |
| `Referenzprojekt/`    | Original-Code als Referenz        |
| `_old_customtkinter/` | Archivierte CustomTkinter-Version |

## Bekannte Probleme (WIP)

- [ ] Sidebar-Buttons: Active/Inactive Styling noch nicht konsistent
- [ ] Hotkey-Zuweisung: Funktioniert teilweise nicht
- [ ] Audio-Level-Monitor: Zeigt keinen Live-Pegel
- [ ] Settings-View: Buttons/Layout noch nicht vollständig responsiv
- [ ] Einige UI-Elemente haben noch Styling-Probleme

## Installation

```bash
pip install -r requirements.txt
python main.py
```

## Anforderungen

- Python 3.10+
- PySide6
- pynput
- sounddevice
- numpy
- Groq API Key

## Verwendung

1. Groq API Key in Einstellungen eingeben
2. Mikrofon auswählen
3. Hotkey gedrückt halten (Standard: rechte Strg-Taste)
4. Sprechen → Text wird transkribiert und eingefügt

## Entwicklung

Die Migration von CustomTkinter zu PySide6 ist im Gange. Bei Fragen zur ursprünglichen Implementierung siehe `Referenzprojekt/` und `_old_customtkinter/`.
