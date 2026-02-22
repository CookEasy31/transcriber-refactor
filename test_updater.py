"""
Updater-Simulation: Testet den kompletten Update-Flow lokal ohne GitHub.

Startet einen lokalen HTTP-Server, simuliert ein GitHub Release mit ZIP-Asset,
und durchlaeuft alle Schritte: check -> download -> install (dry-run).

Ausfuehren:  python test_updater.py
"""

import http.server
import json
import os
import sys
import tempfile
import threading
import zipfile
import shutil
import time

# ──────────────────────────────────────────────────────────────
# Test-Konfiguration
# ──────────────────────────────────────────────────────────────

FAKE_CURRENT_VERSION = "2.2.0"
FAKE_LATEST_VERSION = "2.3.0"
SERVER_PORT = 18927  # ungewoehnlicher Port um Konflikte zu vermeiden
FAKE_ZIP_NAME = f"actScriber-{FAKE_LATEST_VERSION}-win64.zip"
FAKE_MSI_NAME = f"actScriber-{FAKE_LATEST_VERSION}-win64.msi"

# ──────────────────────────────────────────────────────────────
# Hilfs-Funktionen
# ──────────────────────────────────────────────────────────────

def create_fake_zip(directory: str) -> str:
    """Erstellt ein Fake-ZIP mit einer dummy actScriber.exe"""
    zip_path = os.path.join(directory, FAKE_ZIP_NAME)
    with zipfile.ZipFile(zip_path, 'w') as zf:
        # Fake exe (einfach eine Textdatei)
        zf.writestr("actScriber.exe", "FAKE_EXE_v" + FAKE_LATEST_VERSION)
        zf.writestr("config.dll", "FAKE_DLL")
        zf.writestr("PySide6/Qt6Core.dll", "FAKE_QT")
    return zip_path


def create_fake_release_json(zip_url: str, msi_url: str) -> dict:
    """Erstellt ein Fake GitHub Release JSON"""
    return {
        "tag_name": f"v{FAKE_LATEST_VERSION}",
        "name": f"Release {FAKE_LATEST_VERSION}",
        "body": "- Bug fixes\n- Performance improvements\n- Neue Features",
        "assets": [
            {
                "name": FAKE_ZIP_NAME,
                "browser_download_url": zip_url
            },
            {
                "name": FAKE_MSI_NAME,
                "browser_download_url": msi_url
            }
        ]
    }


class FakeGitHubHandler(http.server.BaseHTTPRequestHandler):
    """HTTP Handler der GitHub API + File-Downloads simuliert"""

    release_json = None
    serve_dir = None

    def log_message(self, format, *args):
        # Stille Logs
        pass

    def do_GET(self):
        if self.path == "/api/releases/latest":
            # GitHub API Response
            data = json.dumps(self.release_json).encode('utf-8')
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        elif self.path.startswith("/download/"):
            # File download
            filename = self.path.split("/")[-1]
            filepath = os.path.join(self.serve_dir, filename)
            if os.path.exists(filepath):
                size = os.path.getsize(filepath)
                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Length", str(size))
                self.end_headers()
                with open(filepath, 'rb') as f:
                    self.wfile.write(f.read())
            else:
                self.send_response(404)
                self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()


# ──────────────────────────────────────────────────────────────
# Test-Runner
# ──────────────────────────────────────────────────────────────

def header(text):
    print(f"\n{'='*60}")
    print(f"  {text}")
    print(f"{'='*60}")


def step(num, text):
    print(f"\n--- Test {num}: {text} ---")


def ok(msg):
    print(f"  [OK] {msg}")


def fail(msg):
    print(f"  [FAIL] {msg}")


def warn(msg):
    print(f"  [WARN] {msg}")


def main():
    header("UPDATER SIMULATION")
    print(f"  Simuliere Update: {FAKE_CURRENT_VERSION} -> {FAKE_LATEST_VERSION}")
    print(f"  Lokaler Server: http://localhost:{SERVER_PORT}")

    # Temp-Verzeichnisse
    serve_dir = tempfile.mkdtemp(prefix="updater_test_serve_")
    download_dir = tempfile.mkdtemp(prefix="updater_test_dl_")
    extract_dir = tempfile.mkdtemp(prefix="updater_test_extract_")

    try:
        # ── Fake-Dateien erstellen ──
        fake_zip = create_fake_zip(serve_dir)
        ok(f"Fake ZIP erstellt: {os.path.getsize(fake_zip)} bytes")

        # Fake MSI (leere Datei)
        fake_msi = os.path.join(serve_dir, FAKE_MSI_NAME)
        with open(fake_msi, 'wb') as f:
            f.write(b"FAKE_MSI_CONTENT")
        ok(f"Fake MSI erstellt: {os.path.getsize(fake_msi)} bytes")

        # ── Server starten ──
        base_url = f"http://localhost:{SERVER_PORT}"
        zip_url = f"{base_url}/download/{FAKE_ZIP_NAME}"
        msi_url = f"{base_url}/download/{FAKE_MSI_NAME}"

        FakeGitHubHandler.release_json = create_fake_release_json(zip_url, msi_url)
        FakeGitHubHandler.serve_dir = serve_dir

        server = http.server.HTTPServer(("localhost", SERVER_PORT), FakeGitHubHandler)
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()
        ok(f"HTTP-Server laeuft auf Port {SERVER_PORT}")

        # ── Updater importieren und patchen ──
        import updater

        original_api_url = updater.GITHUB_API_URL
        original_version = updater.APP_VERSION
        updater.GITHUB_API_URL = f"{base_url}/api/releases/latest"

        # Monkey-patch APP_VERSION fuer den Test
        import config
        original_config_version = config.APP_VERSION
        config.APP_VERSION = FAKE_CURRENT_VERSION
        # updater liest APP_VERSION bei import, also auch dort patchen
        updater.__dict__['APP_VERSION'] = FAKE_CURRENT_VERSION

        # ════════════════════════════════════════════════════════════
        # TEST 1: check_for_updates()
        # ════════════════════════════════════════════════════════════
        step(1, "check_for_updates()")

        # Patch: check_for_updates liest APP_VERSION aus config,
        # also muessen wir sicherstellen dass es FAKE_CURRENT_VERSION nutzt
        # Wir re-definieren die Funktion-lokale Variable durch reload
        from importlib import reload
        reload(updater)
        updater.GITHUB_API_URL = f"{base_url}/api/releases/latest"

        result = updater.check_for_updates()

        if result.get('error'):
            fail(f"Fehler: {result['error']}")
            return

        print(f"  current_version: {result['current_version']}")
        print(f"  latest_version:  {result['latest_version']}")
        print(f"  update_available: {result['update_available']}")
        print(f"  asset_type:      {result['asset_type']}")
        print(f"  download_url:    {result['download_url']}")
        print(f"  release_notes:   {result['release_notes'][:50]}...")

        if result['update_available']:
            ok("Update korrekt erkannt")
        else:
            fail("Update NICHT erkannt!")
            return

        if result['asset_type'] == 'zip':
            ok("ZIP-Asset bevorzugt (korrekt)")
        elif result['asset_type'] == 'msi':
            warn("MSI-Asset gewaehlt (ZIP sollte bevorzugt werden)")
        else:
            fail("Kein Asset gefunden!")
            return

        # ════════════════════════════════════════════════════════════
        # TEST 2: check_for_updates() — kein Update
        # ════════════════════════════════════════════════════════════
        step(2, "check_for_updates() - gleiche Version (kein Update)")

        # Setze Version gleich
        FakeGitHubHandler.release_json["tag_name"] = f"v{FAKE_CURRENT_VERSION}"
        result_no_update = updater.check_for_updates()

        if not result_no_update['update_available']:
            ok("Korrekt: Kein Update bei gleicher Version")
        else:
            fail("Falsch-positiv: Update erkannt obwohl Version gleich!")

        # Zuruecksetzen
        FakeGitHubHandler.release_json["tag_name"] = f"v{FAKE_LATEST_VERSION}"

        # ════════════════════════════════════════════════════════════
        # TEST 3: check_for_updates() — nur MSI (kein ZIP)
        # ════════════════════════════════════════════════════════════
        step(3, "check_for_updates() - nur MSI-Asset (Fallback)")

        # ZIP-Asset temporaer entfernen
        original_assets = FakeGitHubHandler.release_json["assets"]
        FakeGitHubHandler.release_json["assets"] = [a for a in original_assets if a["name"].endswith(".msi")]

        result_msi = updater.check_for_updates()
        if result_msi['asset_type'] == 'msi':
            ok("MSI-Fallback funktioniert")
        else:
            fail(f"Erwartet 'msi', bekommen: {result_msi['asset_type']}")

        # Zuruecksetzen
        FakeGitHubHandler.release_json["assets"] = original_assets

        # ════════════════════════════════════════════════════════════
        # TEST 4: download_update() — ZIP herunterladen
        # ════════════════════════════════════════════════════════════
        step(4, "download_update() - ZIP herunterladen")

        progress_values = []
        def on_progress(p):
            progress_values.append(p)

        downloaded_path = updater.download_update(
            url=zip_url,
            target_dir=download_dir,
            progress_callback=on_progress
        )

        if os.path.exists(downloaded_path):
            size = os.path.getsize(downloaded_path)
            ok(f"Download erfolgreich: {downloaded_path} ({size} bytes)")
        else:
            fail("Download-Datei nicht gefunden!")
            return

        # Kein .tmp uebrig?
        tmp_path = downloaded_path + '.tmp'
        if os.path.exists(tmp_path):
            fail(f".tmp Datei nicht aufgeraeumt: {tmp_path}")
        else:
            ok("Atomic rename: keine .tmp Datei uebrig")

        if progress_values and progress_values[-1] == 100:
            ok(f"Progress-Callback: {len(progress_values)} Updates, letzter Wert = 100")
        else:
            warn(f"Progress-Callback: {progress_values}")

        # ════════════════════════════════════════════════════════════
        # TEST 5: download_update() — erneuter Download (Ueberschreiben)
        # ════════════════════════════════════════════════════════════
        step(5, "download_update() - erneuter Download (ueberschreibt alte Datei)")

        downloaded_path2 = updater.download_update(
            url=zip_url,
            target_dir=download_dir
        )

        if os.path.exists(downloaded_path2):
            ok("Re-Download erfolgreich (alte Datei ueberschrieben)")
        else:
            fail("Re-Download fehlgeschlagen!")

        # ════════════════════════════════════════════════════════════
        # TEST 6: ZIP-Inhalt verifizieren
        # ════════════════════════════════════════════════════════════
        step(6, "ZIP-Inhalt verifizieren")

        with zipfile.ZipFile(downloaded_path, 'r') as zf:
            names = zf.namelist()
            print(f"  ZIP-Inhalt: {names}")

            if "actScriber.exe" in names:
                ok("actScriber.exe im ZIP gefunden")
            else:
                fail("actScriber.exe NICHT im ZIP!")

            # Extrahieren zum Testen
            zf.extractall(extract_dir)

        exe_path = os.path.join(extract_dir, "actScriber.exe")
        if os.path.exists(exe_path):
            with open(exe_path, 'r') as f:
                content = f.read()
            ok(f"Extrahierte exe: '{content}'")
        else:
            fail("Extraktion fehlgeschlagen!")

        # ════════════════════════════════════════════════════════════
        # TEST 7: install_zip_update() — Dry-Run (PS1 generieren)
        # ════════════════════════════════════════════════════════════
        step(7, "install_zip_update() - PowerShell-Script Generierung (DRY-RUN)")

        # Wir wollen install_zip_update NICHT wirklich ausfuehren,
        # da es subprocess.Popen startet. Stattdessen patchen wir Popen.
        import unittest.mock
        with unittest.mock.patch('updater.subprocess.Popen') as mock_popen:
            updater.install_zip_update(downloaded_path)

            # Pruefen was Popen aufgerufen wurde
            if mock_popen.called:
                call_args = mock_popen.call_args
                cmd = call_args[0][0]  # erstes positional arg
                print(f"  PowerShell-Kommando: {' '.join(cmd[:4])}...")
                ok("subprocess.Popen wurde korrekt aufgerufen")

                # Flags pruefen
                creation_flags = call_args[1].get('creationflags', 0)
                CREATE_NO_WINDOW = 0x08000000
                DETACHED_PROCESS = 0x00000008
                if creation_flags & CREATE_NO_WINDOW and creation_flags & DETACHED_PROCESS:
                    ok("CREATE_NO_WINDOW + DETACHED_PROCESS Flags gesetzt")
                else:
                    fail(f"Falsche Flags: {hex(creation_flags)}")

                # PS1 Script pruefen
                ps1_path = cmd[-1]  # letztes Argument = Script-Pfad
                if os.path.exists(ps1_path):
                    with open(ps1_path, 'r', encoding='utf-8') as f:
                        script = f.read()

                    checks = {
                        "Expand-Archive": "Expand-Archive Kommando",
                        "actScriber.exe": "exe-Pruefung",
                        "update.log": "Logging",
                        "Remove-Item": "Cleanup (ZIP + Self-Delete)",
                        "Get-Process": "Prozess-Warte-Logik",
                        "Stop-Process": "Force-Kill Logik",
                        str(os.getpid()): "Aktuelle PID eingebettet",
                    }

                    for pattern, desc in checks.items():
                        if pattern in script:
                            ok(f"PS1 enthaelt: {desc}")
                        else:
                            fail(f"PS1 fehlt: {desc}")

                    print(f"\n  --- PS1 Script Preview (erste 500 Zeichen) ---")
                    print(script[:500])
                    print("  --- Ende Preview ---")
                else:
                    fail(f"PS1 Script nicht gefunden: {ps1_path}")
            else:
                fail("subprocess.Popen wurde NICHT aufgerufen!")

        # ════════════════════════════════════════════════════════════
        # TEST 8: install_msi_update() — Dry-Run
        # ════════════════════════════════════════════════════════════
        step(8, "install_msi_update() - Batch-Script Generierung (DRY-RUN)")

        # Fake MSI in download_dir
        fake_msi_dl = os.path.join(download_dir, FAKE_MSI_NAME)
        with open(fake_msi_dl, 'wb') as f:
            f.write(b"FAKE_MSI")

        with unittest.mock.patch('updater.subprocess.Popen') as mock_popen:
            updater.install_msi_update(fake_msi_dl)

            if mock_popen.called:
                cmd = mock_popen.call_args[0][0]
                ok(f"Batch gestartet: {cmd}")

                batch_path = cmd[-1]
                if os.path.exists(batch_path):
                    with open(batch_path, 'r') as f:
                        batch = f.read()
                    if "msiexec" in batch and "actScriber.exe" in batch:
                        ok("Batch-Script korrekt (msiexec + exe restart)")
                    else:
                        fail("Batch-Script unvollstaendig")
                else:
                    fail(f"Batch nicht gefunden: {batch_path}")
            else:
                fail("Popen nicht aufgerufen")

        # ════════════════════════════════════════════════════════════
        # TEST 9: Fehlerbehandlung — ungueltige URL
        # ════════════════════════════════════════════════════════════
        step(9, "download_update() - Fehlerbehandlung (ungueltige URL)")

        try:
            updater.download_update(
                url=f"{base_url}/download/nicht_vorhanden.zip",
                target_dir=download_dir
            )
            fail("Keine Exception bei 404!")
        except Exception as e:
            ok(f"Exception korrekt geworfen: {type(e).__name__}")

        # Kein .tmp uebrig nach Fehler?
        leftover_tmp = [f for f in os.listdir(download_dir) if f.endswith('.tmp')]
        if not leftover_tmp:
            ok("Keine .tmp Dateien nach fehlgeschlagenem Download")
        else:
            fail(f".tmp Dateien uebrig: {leftover_tmp}")

        # ════════════════════════════════════════════════════════════
        # TEST 10: install_zip_update() — nicht existierende ZIP
        # ════════════════════════════════════════════════════════════
        step(10, "install_zip_update() - FileNotFoundError")

        try:
            updater.install_zip_update("C:/nicht/vorhanden.zip")
            fail("Keine Exception!")
        except FileNotFoundError:
            ok("FileNotFoundError korrekt geworfen")

        # ════════════════════════════════════════════════════════════
        # TEST 11: Windows Mutex (Single Instance)
        # ════════════════════════════════════════════════════════════
        step(11, "Windows Named Mutex (Single Instance)")

        import ctypes
        kernel32 = ctypes.windll.kernel32
        ERROR_ALREADY_EXISTS = 183

        # Mutex erstellen
        mutex_name = "Global\\actScriber_Test_SingleInstance"
        mutex1 = kernel32.CreateMutexW(None, False, mutex_name)
        err1 = kernel32.GetLastError()
        ok(f"Mutex erstellt: handle={mutex1}, error={err1}")

        if err1 == 0:
            ok("Erster Mutex: kein Konflikt (korrekt)")
        else:
            warn(f"Erster Mutex unerwartet: error={err1}")

        # Zweiten Mutex mit gleichem Namen
        mutex2 = kernel32.CreateMutexW(None, False, mutex_name)
        err2 = kernel32.GetLastError()

        if err2 == ERROR_ALREADY_EXISTS:
            ok(f"Zweiter Mutex: ERROR_ALREADY_EXISTS ({err2}) - Single Instance funktioniert!")
        else:
            fail(f"Zweiter Mutex: error={err2} (erwartet: {ERROR_ALREADY_EXISTS})")

        # Cleanup
        kernel32.CloseHandle(mutex1)
        kernel32.CloseHandle(mutex2)
        ok("Mutexes freigegeben")

        # ════════════════════════════════════════════════════════════
        # ZUSAMMENFASSUNG
        # ════════════════════════════════════════════════════════════
        header("ALLE TESTS ABGESCHLOSSEN")

        # Aufraeumen
        server.shutdown()

    finally:
        # Temp-Verzeichnisse aufraeumen
        for d in [serve_dir, download_dir, extract_dir]:
            try:
                shutil.rmtree(d, ignore_errors=True)
            except:
                pass


if __name__ == "__main__":
    main()
