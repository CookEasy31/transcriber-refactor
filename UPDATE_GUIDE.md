# act Scriber - Update- und Build-Dokumentation

## 1. App-Metadaten (Zentrale Konfiguration)

Die App hat zwei Dateien mit Versionsinformationen, die **synchron gehalten werden müssen**:

### config.py (Runtime)

```python
APP_NAME = "act Scriber"      # Anzeigename mit Leerzeichen
APP_VERSION = "1.3.7"         # <- Aktuelle Version
APP_DATA_DIR = %LOCALAPPDATA%\act Scriber\  # Benutzer-Einstellungen
CONFIG_FILE = settings.json   # Persistente Konfiguration
```

### build_wix.py (Build-System)

```python
VERSION = "1.3.7"                          # <- Für Updates: NUR HIER ändern!
APP_NAME = "actScriber"                    # Interner Name (OHNE Leerzeichen)
APP_DISPLAY_NAME = "act Scriber"           # Anzeigename
MANUFACTURER = "act legal IT"
UPGRADE_CODE = "{848528C6-9E3F-4946-BF92-112233445566}"  # NIEMALS ändern!
```

> [!CAUTION] > **UPGRADE_CODE** ist die einzige Konstante, die Windows verwendet, um zu erkennen, dass verschiedene MSI-Dateien zur gleichen App gehören. Er muss **IMMER** gleich bleiben!

---

## 2. Update-Logik (Wie Windows Updates erkennt)

```
┌─────────────────────────────────────────────────────────────┐
│  Installierte Version: 1.3.6                                │
│  Neue MSI-Version:     1.3.7                                │
│  UPGRADE_CODE:         {848528C6-9E3F-4946-BF92-...}        │
│                                                             │
│  → Windows erkennt: Gleicher UPGRADE_CODE + höhere Version  │
│  → Alte Version wird automatisch entfernt                   │
│  → Neue Version wird installiert                            │
│  → Benutzer-Einstellungen bleiben erhalten                  │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. Benötigte Dateien

| Datei                         | Zweck                                           |
| ----------------------------- | ----------------------------------------------- |
| `build_wix.py`                | Haupt-Build-Skript (erstellt MSI)               |
| `build_msi.py`                | cx_Freeze-Konfiguration (erstellt .exe)         |
| `icon.ico`                    | App-Icon (für .exe, Installer, Systemsteuerung) |
| `license.rtf`                 | Lizenztext für Installer-Dialog                 |
| `act_scriber_transparent.png` | Logo in der App                                 |
| `act_only_transparent.png`    | Tray-Icon                                       |

### Aktuelle Assets ✓

- `icon.ico` ✓
- `act_scriber_transparent.png` ✓
- `act_only_transparent.png` ✓
- `license.rtf` ⚠️ (muss noch erstellt werden)
- `build_wix.py` ⚠️ (muss noch erstellt werden)
- `build_msi.py` ⚠️ (muss noch erstellt werden)

---

## 4. PySide6 Dependencies

### requirements.txt (aktuell)

```
PySide6>=6.5.0
qtawesome>=1.2.0
sounddevice
numpy
pynput
pyperclip
pyautogui
groq
Pillow
packaging
psutil
```

### Hinweis zu pystray

**NICHT benötigt!** Die PySide6-Version verwendet `QSystemTrayIcon` (native Qt-Implementierung) statt `pystray`.

---

## 5. Build-Prozess

### Voraussetzungen (einmalig)

```powershell
# WiX v6 installieren
dotnet tool install --global wix

# WiX Extensions
wix extension add WixToolset.Util.wixext
wix extension add WixToolset.UI.wixext
```

### Build-Befehl

```powershell
python build_wix.py
```

### Output

```
actScriber-1.3.7-win64.msi  (~45-50 MB)
```

---

## 6. Checkliste für Updates

- [ ] `VERSION` in `build_wix.py` ändern (z.B. "1.3.8")
- [ ] `APP_VERSION` in `config.py` ändern (gleiche Version!)
- [ ] CHANGELOG.md aktualisieren
- [ ] `python build_wix.py` ausführen
- [ ] MSI testen
- [ ] MSI verteilen

---

## 7. Benutzer-Einstellungen (bleiben bei Updates erhalten)

```
%LOCALAPPDATA%\act Scriber\
├── settings.json    # Hotkey, Modus, API-Key, Custom Buttons, etc.
└── history.db       # SQLite mit allen Transkriptionen
```

Diese Dateien werden **NICHT** vom Installer berührt → Benutzer-Einstellungen überleben Updates.

---

## 8. cx_Freeze Konfiguration für PySide6

```python
build_exe_options = {
    "packages": [
        "os", "sys", "PySide6", "qtawesome", "pynput",
        "groq", "sounddevice", "numpy", "pyperclip",
        "pyautogui", "winreg", "ctypes", "sqlite3", "json",
        "logging", "threading", "time", "datetime", "wave", "struct",
        "psutil", "packaging", "PIL"
    ],
    "include_files": [
        ("icon.ico", "icon.ico"),
        ("act_scriber_transparent.png", "act_scriber_transparent.png"),
        ("act_only_transparent.png", "act_only_transparent.png"),
    ],
    "zip_exclude_packages": [
        "PySide6",            # Qt Plugins, DLLs
        "shiboken6",          # PySide6 Bindings
        "qtawesome",          # Font-Dateien
        "sounddevice",
        "_sounddevice_data",
        "numpy",
        "PIL",
    ],
}
```
