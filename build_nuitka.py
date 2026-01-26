"""
================================================================================
actScriber Build-System mit Nuitka + WiX v6
================================================================================

Features:
- Nuitka kompiliert Python zu C (schneller, kleiner als cx_Freeze)
- Per-User Installation (KEINE Admin-Rechte nötig!)
- GUI Installer (WixUI_InstallDir) mit Willkommens-Dialog
- Auto-Upgrade Logik

VERWENDUNG:
    python build_nuitka.py

VORAUSSETZUNGEN:
    - Python 3.12 (venv)
    - Nuitka: uv pip install nuitka ordered-set zstandard
    - WiX v6: dotnet tool install --global wix
    - Extensions: wix extension add WixToolset.Util.wixext
                  wix extension add WixToolset.UI.wixext
================================================================================
"""

import subprocess
import sys
import os
import shutil
from pathlib import Path
import uuid
import re
import hashlib

# ==============================================================================
# KONFIGURATION
# ==============================================================================

VERSION = "1.4.0"
APP_NAME = "actScriber"
APP_DISPLAY_NAME = "act Scriber"
MANUFACTURER = "act legal IT"
DESCRIPTION = "AI Transcriber for Lawyers"

# WICHTIG: Niemals ändern! Ermöglicht Windows automatische Updates zu erkennen
UPGRADE_CODE = "{848528C6-9E3F-4946-BF92-112233445566}"

# ProductCode: Wird aus Version generiert
def get_product_code(version: str) -> str:
    hash_input = f"{APP_NAME}-{version}".encode('utf-8')
    hash_bytes = hashlib.md5(hash_input).hexdigest()
    return "{" + f"{hash_bytes[:8]}-{hash_bytes[8:12]}-{hash_bytes[12:16]}-{hash_bytes[16:20]}-{hash_bytes[20:32]}".upper() + "}"

PRODUCT_CODE = get_product_code(VERSION)

# Pfade
BASE_PATH = Path(__file__).parent.absolute()
ICON_PATH = BASE_PATH / "icon.ico"
LICENSE_PATH = BASE_PATH / "license.rtf"
MAIN_SCRIPT = BASE_PATH / "main.py"

# Output
OUTPUT_MSI = f"{APP_NAME}-{VERSION}-win64.msi"
BUILD_DIR = BASE_PATH / "build"
NUITKA_OUTPUT = BUILD_DIR / f"{APP_NAME}.dist"

# ==============================================================================
# HILFSFUNKTIONEN
# ==============================================================================

def print_header():
    print("\n" + "=" * 70)
    print(f"  BUILD: {APP_DISPLAY_NAME} v{VERSION} (Nuitka)")
    print("=" * 70)

def print_step(step, msg: str):
    print(f"\n{'-'*60}")
    print(f"  Schritt {step}: {msg}")
    print(f"{'-'*60}")

def sanitize_id(name: str, prefix: str = "") -> str:
    name_hash = hashlib.md5(str(name).encode('utf-8')).hexdigest()[:12]
    clean_name = re.sub(r'[^A-Za-z0-9_]', '_', str(name))
    if clean_name and clean_name[0].isdigit():
        clean_name = "_" + clean_name
    if len(clean_name) > 50:
        clean_name = clean_name[:50]
    return f"{prefix}{clean_name}_{name_hash}"

def generate_guid() -> str:
    return "{" + str(uuid.uuid4()).upper() + "}"

def clean_build():
    print_step(1, "Bereinige alte Builds")

    for item in ["build", "Package.wxs", OUTPUT_MSI, f"{APP_NAME}.build"]:
        path = BASE_PATH / item
        if path.exists():
            try:
                if path.is_dir():
                    shutil.rmtree(path, ignore_errors=False)
                    print(f"   OK {item}/ gelöscht")
                else:
                    path.unlink()
                    print(f"   OK {item} gelöscht")
            except Exception as e:
                print(f"   WARNUNG {item}: {e}")

    print("   OK Bereinigung abgeschlossen")

def run_nuitka():
    print_step(2, "Kompiliere mit Nuitka")

    # Nuitka Kommando
    cmd = [
        sys.executable, "-m", "nuitka",
        "--standalone",
        "--assume-yes-for-downloads",  # Auto-accept dependency downloads
        "--onefile-tempdir-spec=%TEMP%/actScriber",
        f"--output-dir={BUILD_DIR}",
        f"--output-filename={APP_NAME}.exe",

        # Windows GUI App (kein Konsolenfenster)
        "--windows-console-mode=disable",
        f"--windows-icon-from-ico={ICON_PATH}",

        # Company Info
        f"--windows-company-name={MANUFACTURER}",
        f"--windows-product-name={APP_DISPLAY_NAME}",
        f"--windows-file-version={VERSION}",
        f"--windows-product-version={VERSION}",
        f"--windows-file-description={DESCRIPTION}",

        # PySide6 Plugin
        "--enable-plugin=pyside6",

        # Benötigte Module
        "--include-module=pynput",
        "--include-module=pynput.keyboard",
        "--include-module=pynput.keyboard._win32",
        "--include-module=pynput.mouse",
        "--include-module=pynput.mouse._win32",
        "--include-module=sounddevice",
        "--include-module=numpy",
        "--include-module=pyperclip",
        "--include-module=pyautogui",
        "--include-module=groq",
        "--include-module=httpx",
        "--include-module=httpcore",
        "--include-module=h11",
        "--include-module=anyio",
        "--include-module=certifi",
        "--include-module=PIL",
        "--include-module=psutil",
        "--include-module=packaging",
        "--include-module=qtawesome",
        "--include-module=dotenv",

        # Include data files
        f"--include-data-files={ICON_PATH}=icon.ico",
        f"--include-data-files={BASE_PATH / 'act_scriber_transparent.png'}=act_scriber_transparent.png",
        f"--include-data-files={BASE_PATH / 'act_only_transparent.png'}=act_only_transparent.png",

        # Ausschlüsse
        "--nofollow-import-to=tkinter",
        "--nofollow-import-to=test",
        "--nofollow-import-to=PyQt6",
        "--nofollow-import-to=PyQt5",

        # Performance - nutze mehr CPU-Kerne
        "--jobs=12",

        # Main script
        str(MAIN_SCRIPT)
    ]

    print("   Starte Nuitka (kann einige Minuten dauern)...")
    print(f"   Kommando: nuitka --standalone ...")

    result = subprocess.run(cmd, cwd=BASE_PATH, check=False)

    if result.returncode != 0:
        print("   FEHLER: Nuitka build fehlgeschlagen!")
        sys.exit(1)

    # Finde den Output-Ordner
    dist_folder = BASE_PATH / "main.dist"
    if not dist_folder.exists():
        print(f"   FEHLER: Output-Ordner nicht gefunden!")
        print(f"   Suche in: {BUILD_DIR}")
        # Versuche alternative Namen
        for alt in ["main.dist", f"{APP_NAME}.dist", "actScriber.dist"]:
            alt_path = BASE_PATH / alt
            if alt_path.exists():
                dist_folder = alt_path
                break
            alt_path = BUILD_DIR / alt
            if alt_path.exists():
                dist_folder = alt_path
                break

    if not dist_folder.exists():
        print("   FEHLER: Kein dist-Ordner gefunden!")
        sys.exit(1)

    # Verschiebe in build/
    target = BUILD_DIR / f"exe.win-amd64-{sys.version_info.major}.{sys.version_info.minor}"
    if dist_folder != target:
        BUILD_DIR.mkdir(exist_ok=True)
        if target.exists():
            shutil.rmtree(target)
        shutil.move(str(dist_folder), str(target))
        dist_folder = target

    # Prüfe ob exe existiert
    exe_path = dist_folder / f"{APP_NAME}.exe"
    if not exe_path.exists():
        # Versuche main.exe zu finden und umzubenennen
        main_exe = dist_folder / "main.exe"
        if main_exe.exists():
            main_exe.rename(exe_path)

    if not exe_path.exists():
        print(f"   FEHLER: {APP_NAME}.exe nicht gefunden!")
        sys.exit(1)

    print(f"   OK Executable erstellt: {dist_folder.name}")
    return dist_folder

def create_env_file(build_folder: Path):
    """Erstellt .env Datei mit API-Key im Build-Ordner"""
    print_step(3, "Erstelle .env Datei")

    api_key = os.getenv("GROQ_API_KEY", "")
    if not api_key:
        env_path = BASE_PATH / ".env"
        if env_path.exists():
            with open(env_path, "r") as f:
                for line in f:
                    if line.startswith("GROQ_API_KEY="):
                        api_key = line.strip().split("=", 1)[1]
                        break

    if not api_key:
        print("   WARNUNG: Kein GROQ_API_KEY gefunden! .env wird leer sein.")

    env_content = f"GROQ_API_KEY={api_key}\n"
    env_file = build_folder / ".env"
    with open(env_file, "w") as f:
        f.write(env_content)

    print(f"   OK .env erstellt")

def collect_files(build_folder: Path) -> list:
    files = []
    for item in build_folder.rglob("*"):
        if item.is_file():
            rel_path = item.relative_to(build_folder)
            files.append((rel_path, item))
    return files

def build_directory_tree(directories: set) -> dict:
    tree = {"": []}

    for dir_path in sorted(directories, key=lambda p: len(p.parts)):
        parent = dir_path.parent
        parent_key = str(parent) if parent != Path(".") else ""

        if parent_key not in tree:
            tree[parent_key] = []

        tree[parent_key].append(dir_path)

        if str(dir_path) not in tree:
            tree[str(dir_path)] = []

    return tree

def generate_directory_xml(tree: dict, dir_refs: dict, parent_key: str = "", indent: int = 8) -> str:
    xml_parts = []
    spaces = " " * indent

    for child_path in tree.get(parent_key, []):
        dir_id = sanitize_id(str(child_path), "D_")
        dir_refs[child_path] = dir_id

        child_key = str(child_path)
        children_xml = generate_directory_xml(tree, dir_refs, child_key, indent + 2)

        if children_xml:
            xml_parts.append(f'{spaces}<Directory Id="{dir_id}" Name="{child_path.name}">')
            xml_parts.append(children_xml)
            xml_parts.append(f'{spaces}</Directory>')
        else:
            xml_parts.append(f'{spaces}<Directory Id="{dir_id}" Name="{child_path.name}" />')

    return "\n".join(xml_parts)

def generate_wxs(build_folder: Path) -> str:
    print_step(4, "Generiere WiX-Konfiguration")

    files = collect_files(build_folder)
    print(f"   OK {len(files)} Dateien gefunden")

    directories = set()
    for rel_path, _ in files:
        parent = rel_path.parent
        while parent != Path("."):
            directories.add(parent)
            parent = parent.parent

    print(f"   OK {len(directories)} Verzeichnisse")

    dir_refs = {}
    tree = build_directory_tree(directories)
    dir_elements = generate_directory_xml(tree, dir_refs)

    component_elements = []
    component_refs = []

    for rel_path, full_path in files:
        original_path = str(rel_path)
        file_id = sanitize_id(original_path, "F_")
        comp_id = sanitize_id(original_path, "C_")
        guid = generate_guid()

        dir_id = "INSTALLFOLDER"
        if rel_path.parent != Path("."):
            dir_id = dir_refs.get(rel_path.parent, "INSTALLFOLDER")

        source = str(rel_path).replace("\\", "/")

        component_elements.append(f'''
      <Component Id="{comp_id}" Directory="{dir_id}" Guid="{guid}">
        <File Id="{file_id}" Source="{source}" KeyPath="yes" />
      </Component>''')

        component_refs.append(f'        <ComponentRef Id="{comp_id}" />')

    # WXS mit perUser Installation
    wxs_content = f'''<?xml version="1.0" encoding="utf-8"?>
<Wix xmlns="http://wixtoolset.org/schemas/v4/wxs"
     xmlns:util="http://wixtoolset.org/schemas/v4/wxs/util"
     xmlns:ui="http://wixtoolset.org/schemas/v4/wxs/ui">

  <Package
    Name="{APP_DISPLAY_NAME}"
    Manufacturer="{MANUFACTURER}"
    Version="{VERSION}"
    UpgradeCode="{UPGRADE_CODE}"
    ProductCode="{PRODUCT_CODE}"
    Scope="perUser"
    Compressed="yes"
    Language="1031">

    <MajorUpgrade
      DowngradeErrorMessage="Eine neuere Version von {APP_DISPLAY_NAME} ist bereits installiert."
      Schedule="afterInstallInitialize" />

    <MediaTemplate EmbedCab="yes" CompressionLevel="high" />

    <ui:WixUI Id="WixUI_InstallDir" InstallDirectory="INSTALLFOLDER" />
    <WixVariable Id="WixUILicenseRtf" Value="license.rtf" />

    <util:CloseApplication
      Id="CloseActScriber"
      Target="{APP_NAME}.exe"
      Description="{APP_DISPLAY_NAME} wird geschlossen."
      CloseMessage="yes"
      ElevatedCloseMessage="yes"
      Timeout="10"
      TerminateProcess="0"
      RebootPrompt="no" />

    <Feature Id="MainFeature" Title="{APP_DISPLAY_NAME}" Level="1">
      <ComponentGroupRef Id="AppComponents" />
      <ComponentRef Id="StartMenuShortcut" />
      <ComponentRef Id="DesktopShortcut" />
    </Feature>

    <Icon Id="AppIcon.ico" SourceFile="icon.ico" />
    <Property Id="ARPPRODUCTICON" Value="AppIcon.ico" />
    <Property Id="ARPHELPLINK" Value="https://www.actlegal.com" />

  </Package>

  <Fragment>
    <StandardDirectory Id="LocalAppDataFolder">
      <Directory Id="INSTALLFOLDER" Name="{APP_NAME}">
{dir_elements}
      </Directory>
    </StandardDirectory>

    <StandardDirectory Id="ProgramMenuFolder">
      <Directory Id="AppMenuFolder" Name="{APP_DISPLAY_NAME}" />
    </StandardDirectory>

    <StandardDirectory Id="DesktopFolder" />
  </Fragment>

  <Fragment>
    <Component Id="StartMenuShortcut" Directory="AppMenuFolder" Guid="{generate_guid()}">
      <Shortcut
        Id="StartMenuShortcutMain"
        Name="{APP_DISPLAY_NAME}"
        Target="[INSTALLFOLDER]{APP_NAME}.exe"
        WorkingDirectory="INSTALLFOLDER"
        Icon="AppIcon.ico" />
      <RemoveFolder Id="RemoveAppMenuFolder" On="uninstall" />
      <RegistryValue
        Root="HKCU"
        Key="Software\\{MANUFACTURER}\\{APP_NAME}"
        Name="StartMenuShortcut"
        Type="integer"
        Value="1"
        KeyPath="yes" />
    </Component>

    <Component Id="DesktopShortcut" Directory="DesktopFolder" Guid="{generate_guid()}">
      <Shortcut
        Id="DesktopShortcutMain"
        Name="{APP_DISPLAY_NAME}"
        Target="[INSTALLFOLDER]{APP_NAME}.exe"
        WorkingDirectory="INSTALLFOLDER"
        Icon="AppIcon.ico" />
      <RegistryValue
        Root="HKCU"
        Key="Software\\{MANUFACTURER}\\{APP_NAME}"
        Name="DesktopShortcut"
        Type="integer"
        Value="1"
        KeyPath="yes" />
    </Component>
  </Fragment>

  <Fragment>
    <ComponentGroup Id="AppComponents">
{chr(10).join(component_refs)}
    </ComponentGroup>
    {''.join(component_elements)}
  </Fragment>

</Wix>
'''

    wxs_path = BASE_PATH / "Package.wxs"
    with open(wxs_path, "w", encoding="utf-8") as f:
        f.write(wxs_content)

    print(f"   OK Package.wxs generiert")
    return str(wxs_path)

def run_wix_build(build_folder: Path):
    print_step(5, "Erstelle MSI (WiX)")

    cmd = [
        "wix", "build",
        "Package.wxs",
        "-arch", "x64",
        "-ext", "WixToolset.Util.wixext",
        "-ext", "WixToolset.UI.wixext",
        "-b", str(build_folder),
        "-b", str(BASE_PATH),
        "-o", str(BASE_PATH / OUTPUT_MSI)
    ]

    print(f"   Kommando: wix build Package.wxs ...")

    result = subprocess.run(cmd, cwd=BASE_PATH, check=False, capture_output=True, text=True)

    if result.returncode != 0:
        print("   FEHLER: WiX build fehlgeschlagen!")
        print("\n   STDERR:")
        print(result.stderr[:2000] if result.stderr else "(leer)")
        sys.exit(1)

    msi_path = BASE_PATH / OUTPUT_MSI
    if not msi_path.exists():
        print("   FEHLER: MSI wurde nicht erstellt!")
        sys.exit(1)

    size_mb = msi_path.stat().st_size / (1024 * 1024)
    print(f"   OK MSI erstellt: {OUTPUT_MSI} ({size_mb:.1f} MB)")

def print_summary():
    msi_path = BASE_PATH / OUTPUT_MSI

    print("\n" + "=" * 70)
    print("  BUILD ERFOLGREICH!")
    print("=" * 70)
    print(f"""
  Erstellte Datei:
     {msi_path}

  Features dieser MSI:
     - Per-User Installation (KEINE Admin-Rechte nötig!)
     - Installiert nach: %LOCALAPPDATA%\\{APP_NAME}\\
     - Kompiliert mit Nuitka (schneller als cx_Freeze)
     - GUI-Installer mit Willkommens-Dialog
     - Automatisches Schließen der App bei Updates
     - Auto-Updates ohne IT-Support möglich!

  Installation:
     Doppelklick auf {OUTPUT_MSI}

  Silent Install:
     msiexec /i "{OUTPUT_MSI}" /qn
""")

def main():
    print_header()

    if not LICENSE_PATH.exists():
        print(f"   WARNUNG: license.rtf nicht gefunden!")
        sys.exit(1)

    clean_build()
    build_folder = run_nuitka()
    create_env_file(build_folder)
    generate_wxs(build_folder)
    run_wix_build(build_folder)
    print_summary()

if __name__ == "__main__":
    main()
