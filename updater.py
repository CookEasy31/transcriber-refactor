"""
Update-Modul für actScriber.
Prüft GitHub Releases auf neue Versionen und führt Updates durch.
Unterstützt ZIP-Updates (bevorzugt) und MSI-Updates (Fallback).
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
    Bevorzugt .zip Assets, Fallback auf .msi.

    Returns:
        dict: {
            'update_available': bool,
            'current_version': str,
            'latest_version': str,
            'download_url': str or None,
            'asset_type': 'zip' | 'msi' | None,
            'release_notes': str,
            'error': str or None
        }
    """
    result = {
        'update_available': False,
        'current_version': APP_VERSION,
        'latest_version': APP_VERSION,
        'download_url': None,
        'asset_type': None,
        'release_notes': '',
        'error': None
    }

    try:
        request = urllib.request.Request(
            GITHUB_API_URL,
            headers={
                'User-Agent': USER_AGENT,
                'Accept': 'application/vnd.github.v3+json'
            }
        )

        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
            data = json.loads(response.read().decode('utf-8'))

        latest_version_str = data.get('tag_name', '').lstrip('v')
        result['latest_version'] = latest_version_str
        result['release_notes'] = data.get('body', '') or ''

        # Assets durchsuchen: ZIP bevorzugt, MSI als Fallback
        assets = data.get('assets', [])
        zip_url = None
        msi_url = None
        for asset in assets:
            asset_name = asset.get('name', '')
            if asset_name.endswith('.zip') and 'actScriber' in asset_name:
                zip_url = asset.get('browser_download_url')
            elif asset_name.endswith('.msi') and 'actScriber' in asset_name:
                msi_url = asset.get('browser_download_url')

        if zip_url:
            result['download_url'] = zip_url
            result['asset_type'] = 'zip'
        elif msi_url:
            result['download_url'] = msi_url
            result['asset_type'] = 'msi'

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
    Lädt die Update-Datei von der angegebenen URL herunter.
    Download zuerst nach .tmp, dann atomic rename.

    Args:
        url: Download-URL
        target_dir: Zielverzeichnis für den Download
        progress_callback: Optionale Callback-Funktion für Fortschritt (0-100)

    Returns:
        str: Pfad zur heruntergeladenen Datei

    Raises:
        Exception: Bei Download-Fehlern
    """
    os.makedirs(target_dir, exist_ok=True)

    filename = url.split('/')[-1]
    target_path = os.path.join(target_dir, filename)
    tmp_path = target_path + '.tmp'

    # Alten partiellen Download löschen
    if os.path.exists(tmp_path):
        os.remove(tmp_path)

    try:
        request = urllib.request.Request(
            url,
            headers={'User-Agent': USER_AGENT}
        )

        with urllib.request.urlopen(request) as response:
            total_size = response.headers.get('Content-Length')
            total_size = int(total_size) if total_size else 0

            downloaded = 0
            chunk_size = 65536  # 64KB

            with open(tmp_path, 'wb') as f:
                while True:
                    chunk = response.read(chunk_size)
                    if not chunk:
                        break

                    f.write(chunk)
                    downloaded += len(chunk)

                    if progress_callback and total_size > 0:
                        percent = int((downloaded / total_size) * 100)
                        progress_callback(percent)

        # Atomic rename: tmp -> final
        if os.path.exists(target_path):
            os.remove(target_path)
        os.rename(tmp_path, target_path)

        if progress_callback:
            progress_callback(100)

        return target_path

    except Exception:
        # Cleanup partial download
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise


def install_zip_update(zip_path: str) -> None:
    r"""
    Installiert ein ZIP-Update komplett silent via PowerShell.
    Erstellt ein PowerShell-Script das:
    1. Wartet bis alter Prozess beendet ist (max 30s, danach Force-Kill)
    2. Extrahiert ZIP nach C:\Program Files\actScriber\
    3. Prüft ob actScriber.exe existiert
    4. Startet neue Version
    5. Löscht ZIP + sich selbst
    6. Loggt nach %LOCALAPPDATA%\act Scriber\update.log
    """
    if not os.path.exists(zip_path):
        raise FileNotFoundError(f"ZIP-Datei nicht gefunden: {zip_path}")

    zip_path = os.path.abspath(zip_path)
    install_dir = os.path.join(os.environ.get('PROGRAMFILES', r'C:\Program Files'), 'act Scriber')
    exe_path = os.path.join(install_dir, 'actScriber.exe')
    log_dir = os.path.join(os.environ.get('LOCALAPPDATA', ''), 'act Scriber')
    log_path = os.path.join(log_dir, 'update.log')
    current_pid = os.getpid()

    ps_script = f'''
$ErrorActionPreference = "Stop"
$logDir = "{log_dir}"
$logFile = "{log_path}"
if (-not (Test-Path $logDir)) {{ New-Item -ItemType Directory -Path $logDir -Force | Out-Null }}

function Log($msg) {{
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$ts $msg" | Out-File -Append -FilePath $logFile -Encoding UTF8
}}

Log "=== Update gestartet ==="
Log "PID des alten Prozesses: {current_pid}"
Log "ZIP: {zip_path}"
Log "Ziel: {install_dir}"

# Warte bis alter Prozess beendet ist (max 30 Sekunden)
$waited = 0
while ($waited -lt 30) {{
    try {{
        $proc = Get-Process -Id {current_pid} -ErrorAction SilentlyContinue
        if (-not $proc) {{ break }}
        Start-Sleep -Seconds 1
        $waited++
    }} catch {{ break }}
}}

# Falls immer noch aktiv: Force-Kill
try {{
    $proc = Get-Process -Id {current_pid} -ErrorAction SilentlyContinue
    if ($proc) {{
        Log "Force-Kill nach $waited Sekunden"
        Stop-Process -Id {current_pid} -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 2
    }}
}} catch {{}}

Log "Alter Prozess beendet nach $waited Sekunden"

# ZIP extrahieren
try {{
    Expand-Archive -Path "{zip_path}" -DestinationPath "{install_dir}" -Force
    Log "ZIP erfolgreich extrahiert"
}} catch {{
    Log "FEHLER beim Extrahieren: $_"
    exit 1
}}

# Prüfe ob exe existiert
if (Test-Path "{exe_path}") {{
    Log "actScriber.exe gefunden - starte neue Version"
    Start-Process -FilePath "{exe_path}"
}} else {{
    Log "FEHLER: actScriber.exe nicht gefunden nach Extraktion!"
}}

# Aufräumen
try {{
    Remove-Item -Path "{zip_path}" -Force -ErrorAction SilentlyContinue
    Log "ZIP gelöscht"
}} catch {{
    Log "WARNUNG: ZIP konnte nicht gelöscht werden: $_"
}}

Log "=== Update abgeschlossen ==="

# Script löscht sich selbst
Remove-Item -Path $MyInvocation.MyCommand.Path -Force -ErrorAction SilentlyContinue
'''

    # PowerShell-Script in Temp schreiben
    script_path = os.path.join(tempfile.gettempdir(), 'actscriber_update.ps1')
    with open(script_path, 'w', encoding='utf-8') as f:
        f.write(ps_script)

    # PowerShell komplett unsichtbar starten
    CREATE_NO_WINDOW = 0x08000000
    DETACHED_PROCESS = 0x00000008

    subprocess.Popen(
        [
            'powershell.exe',
            '-ExecutionPolicy', 'Bypass',
            '-NoProfile',
            '-WindowStyle', 'Hidden',
            '-File', script_path
        ],
        creationflags=CREATE_NO_WINDOW | DETACHED_PROCESS,
        close_fds=True
    )


def install_msi_update(msi_path: str) -> None:
    """
    Startet die Installation der MSI-Datei und beendet die aktuelle Anwendung.
    Fallback für Releases ohne ZIP-Asset.
    """
    if not os.path.exists(msi_path):
        raise FileNotFoundError(f"MSI-Datei nicht gefunden: {msi_path}")

    msi_path = os.path.abspath(msi_path)
    install_dir = os.path.join(os.environ.get('PROGRAMFILES', r'C:\Program Files'), 'act Scriber')
    exe_path = os.path.join(install_dir, 'actScriber.exe')

    batch_content = f'''@echo off
start /wait msiexec /i "{msi_path}" /passive
if exist "{exe_path}" (
    start "" "{exe_path}"
)
del "%~f0"
'''

    batch_path = os.path.join(tempfile.gettempdir(), 'actscriber_update.bat')
    with open(batch_path, 'w') as f:
        f.write(batch_content)

    subprocess.Popen(
        ['cmd', '/c', batch_path],
        shell=False,
        creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
    )
