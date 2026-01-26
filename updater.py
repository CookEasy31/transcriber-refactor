"""
Update-Modul für actScriber.
Prüft GitHub Releases auf neue Versionen und führt Updates durch.
"""

import json
import os
import sys
import subprocess
import tempfile
import urllib.request
import urllib.error
from typing import Optional, Callable

from packaging import version

from config import APP_VERSION

# GitHub API Konfiguration
GITHUB_REPO = "CookEasy31/transcriber-refactor"
GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
USER_AGENT = "actScriber-Updater/1.0"
REQUEST_TIMEOUT = 5  # Sekunden


def check_for_updates() -> dict:
    """
    Prüft ob eine neue Version auf GitHub verfügbar ist.

    Returns:
        dict: {
            'update_available': bool,
            'current_version': str,
            'latest_version': str,
            'is_force': bool,
            'download_url': str or None,  # URL zur .msi Datei
            'release_notes': str,
            'error': str or None
        }
    """
    result = {
        'update_available': False,
        'current_version': APP_VERSION,
        'latest_version': APP_VERSION,
        'is_force': False,
        'download_url': None,
        'release_notes': '',
        'error': None
    }

    try:
        # Request erstellen mit User-Agent Header
        request = urllib.request.Request(
            GITHUB_API_URL,
            headers={
                'User-Agent': USER_AGENT,
                'Accept': 'application/vnd.github.v3+json'
            }
        )

        # API abfragen
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
            data = json.loads(response.read().decode('utf-8'))

        # Version aus tag_name extrahieren (z.B. "v1.2.3" -> "1.2.3")
        latest_version_str = data.get('tag_name', '').lstrip('v')
        result['latest_version'] = latest_version_str

        # Release Notes
        result['release_notes'] = data.get('body', '') or ''

        # Force-Update prüfen (im Titel)
        release_title = data.get('name', '') or ''
        if '[FORCE]' in release_title.upper() or '[REQUIRED]' in release_title.upper():
            result['is_force'] = True

        # MSI Download-URL suchen
        assets = data.get('assets', [])
        for asset in assets:
            asset_name = asset.get('name', '')
            # Pattern: actScriber-X.X.X-win64.msi
            if asset_name.endswith('.msi') and 'actScriber' in asset_name:
                result['download_url'] = asset.get('browser_download_url')
                break

        # Versionen vergleichen
        try:
            current = version.parse(APP_VERSION)
            latest = version.parse(latest_version_str)

            if latest > current:
                result['update_available'] = True
        except version.InvalidVersion as e:
            result['error'] = f"Ungültiges Versionsformat: {e}"

    except urllib.error.URLError as e:
        result['error'] = f"Netzwerkfehler: {e.reason}"
    except urllib.error.HTTPError as e:
        result['error'] = f"HTTP-Fehler {e.code}: {e.reason}"
    except json.JSONDecodeError as e:
        result['error'] = f"Ungültige API-Antwort: {e}"
    except TimeoutError:
        result['error'] = "Zeitüberschreitung bei der Verbindung zu GitHub"
    except Exception as e:
        result['error'] = f"Unerwarteter Fehler: {e}"

    return result


def download_update(
    url: str,
    target_dir: str,
    progress_callback: Optional[Callable[[int], None]] = None
) -> str:
    """
    Lädt die MSI-Datei von der angegebenen URL herunter.

    Args:
        url: Download-URL der MSI-Datei
        target_dir: Zielverzeichnis für den Download
        progress_callback: Optionale Callback-Funktion für Fortschritt (0-100)

    Returns:
        str: Pfad zur heruntergeladenen Datei

    Raises:
        Exception: Bei Download-Fehlern
    """
    # Zielverzeichnis erstellen falls nicht vorhanden
    os.makedirs(target_dir, exist_ok=True)

    # Dateiname aus URL extrahieren
    filename = url.split('/')[-1]
    target_path = os.path.join(target_dir, filename)

    try:
        # Request erstellen
        request = urllib.request.Request(
            url,
            headers={'User-Agent': USER_AGENT}
        )

        with urllib.request.urlopen(request) as response:
            # Dateigröße ermitteln
            total_size = response.headers.get('Content-Length')
            total_size = int(total_size) if total_size else 0

            downloaded = 0
            chunk_size = 8192

            with open(target_path, 'wb') as f:
                while True:
                    chunk = response.read(chunk_size)
                    if not chunk:
                        break

                    f.write(chunk)
                    downloaded += len(chunk)

                    # Fortschritt melden
                    if progress_callback and total_size > 0:
                        percent = int((downloaded / total_size) * 100)
                        progress_callback(percent)

        # Finalen Fortschritt melden
        if progress_callback:
            progress_callback(100)

        return target_path

    except urllib.error.URLError as e:
        raise Exception(f"Download fehlgeschlagen: {e.reason}")
    except urllib.error.HTTPError as e:
        raise Exception(f"HTTP-Fehler {e.code}: {e.reason}")
    except IOError as e:
        raise Exception(f"Dateifehler: {e}")


def install_update(msi_path: str) -> None:
    """
    Startet die Installation der MSI-Datei und beendet die aktuelle Anwendung.
    Nach der Installation wird die App automatisch neu gestartet.

    Args:
        msi_path: Pfad zur MSI-Installationsdatei

    Raises:
        FileNotFoundError: Wenn die MSI-Datei nicht existiert
        Exception: Bei Installationsfehlern
    """
    if not os.path.exists(msi_path):
        raise FileNotFoundError(f"MSI-Datei nicht gefunden: {msi_path}")

    # Absoluten Pfad sicherstellen
    msi_path = os.path.abspath(msi_path)

    # Installationspfad der neuen Version (per-user installation)
    install_dir = os.path.join(os.environ.get('LOCALAPPDATA', ''), 'actScriber')
    exe_path = os.path.join(install_dir, 'actScriber.exe')

    try:
        # Batch-Script erstellen, das:
        # 1. Auf MSI-Installation wartet
        # 2. App neu startet
        batch_content = f'''@echo off
start /wait msiexec /i "{msi_path}" /passive
if exist "{exe_path}" (
    start "" "{exe_path}"
)
del "%~f0"
'''

        # Batch-Datei im Temp-Verzeichnis erstellen
        batch_path = os.path.join(tempfile.gettempdir(), 'actscriber_update.bat')
        with open(batch_path, 'w') as f:
            f.write(batch_content)

        # Batch-Script starten (im Hintergrund, versteckt)
        subprocess.Popen(
            ['cmd', '/c', batch_path],
            shell=False,
            creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
        )

        # Anwendung beenden
        sys.exit(0)

    except Exception as e:
        raise Exception(f"Installation konnte nicht gestartet werden: {e}")
