"""
================================================================================
actScriber Build-System mit cx_Freeze + WiX v6 (OPTIMIERT)
================================================================================

Features:
- GUI Installer (WixUI_InstallDir) mit Willkommens-Dialog
- ZIP-Kompression für schnelle Installation
- Auto-Upgrade Logik
- CloseApplication für laufende Instanzen

VERWENDUNG:
    python build_wix.py

VORAUSSETZUNGEN:
    - Python 3.12 (venv)
    - WiX v6: dotnet tool install --global wix
    - Extensions: wix extension add WixToolset.Util.wixext
                  wix extension add WixToolset.UI.wixext

FÜR UPDATES:
    1. VERSION hier ändern
    2. python build_wix.py
    3. Fertig!
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
# KONFIGURATION - NUR HIER ÄNDERN FÜR UPDATES!
# ==============================================================================

VERSION = "1.3.7"                          # <- Für Updates: Nur diese Zeile ändern!
APP_NAME = "actScriber"                    # Interner Name (keine Leerzeichen)
APP_DISPLAY_NAME = "act Scriber"           # Anzeigename
MANUFACTURER = "act legal IT"
DESCRIPTION = "AI Transcriber for Lawyers"

# WICHTIG: Niemals ändern! Ermöglicht Windows automatische Updates zu erkennen
UPGRADE_CODE = "{848528C6-9E3F-4946-BF92-112233445566}"

# ProductCode: Wird aus Version generiert - gleiche Version = gleicher Code
# Das verhindert doppelte Installationen bei Re-Builds
def get_product_code(version: str) -> str:
    """Generiert einen deterministischen ProductCode basierend auf der Version."""
    import hashlib
    # Erzeuge einen Hash aus App-Name + Version
    hash_input = f"{APP_NAME}-{version}".encode('utf-8')
    hash_bytes = hashlib.md5(hash_input).hexdigest()
    # Formatiere als GUID
    return "{" + f"{hash_bytes[:8]}-{hash_bytes[8:12]}-{hash_bytes[12:16]}-{hash_bytes[16:20]}-{hash_bytes[20:32]}".upper() + "}"

PRODUCT_CODE = get_product_code(VERSION)

# Pfade
BASE_PATH = Path(__file__).parent.absolute()
ICON_PATH = BASE_PATH / "icon.ico"
LICENSE_PATH = BASE_PATH / "license.rtf"

# Output
OUTPUT_MSI = f"{APP_NAME}-{VERSION}-win64.msi"

# ==============================================================================
# HILFSFUNKTIONEN
# ==============================================================================

def print_header():
    print("\n" + "=" * 70)
    print(f"  BUILD: {APP_DISPLAY_NAME} v{VERSION}")
    print("=" * 70)

def print_step(step: int, msg: str):
    print(f"\n{'-'*60}")
    print(f"  Schritt {step}: {msg}")
    print(f"{'-'*60}")

def sanitize_id(name: str, prefix: str = "") -> str:
    """
    Erstellt stabile, eindeutige WiX-IDs aus Dateinamen.
    Verwendet MD5-Hash für Eindeutigkeit bei langen Pfaden.
    """
    clean_name = re.sub(r'[^A-Za-z0-9_]', '_', str(name))
    name_hash = hashlib.md5(str(name).encode('utf-8')).hexdigest()[:8]
    
    # ID darf nicht mit Zahl beginnen
    if clean_name and clean_name[0].isdigit():
        clean_name = "_" + clean_name
    
    # Max 60 Zeichen + 8 Hash = 68 (unter 72 Limit)
    if len(clean_name) > 50:
        clean_name = clean_name[:50]
    
    return f"{prefix}{clean_name}_{name_hash}"

def generate_guid() -> str:
    return "{" + str(uuid.uuid4()).upper() + "}"

def clean_build():
    print_step(1, "Bereinige alte Builds")
    
    for item in ["build", "Package.wxs", OUTPUT_MSI]:
        path = BASE_PATH / item
        if path.exists():
            try:
                if path.is_dir():
                    shutil.rmtree(path, ignore_errors=False)
                    print(f"   OK {item}/ geloescht")
                else:
                    path.unlink()
                    print(f"   OK {item} geloescht")
            except Exception as e:
                print(f"   WARNUNG {item}: {e}")
    
    print("   OK Bereinigung abgeschlossen")

def run_cx_freeze():
    print_step(2, "Erstelle Executable (cx_Freeze)")
    
    result = subprocess.run(
        [sys.executable, "build_msi.py", "build_exe"],
        cwd=BASE_PATH,
        check=False
    )
    
    if result.returncode != 0:
        print("   FEHLER: cx_Freeze fehlgeschlagen!")
        sys.exit(1)
    
    print("   OK Executable erstellt")

def create_env_file(build_folder: Path):
    """Erstellt .env Datei mit API-Key im Build-Ordner"""
    print_step(3, "Erstelle .env Datei")

    # API Key - NUR lokal beim Build, NICHT im Git-Repo!
    api_key = os.getenv("GROQ_API_KEY", "")
    if not api_key:
        # Fallback: Aus lokaler .env lesen
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

    print(f"   OK .env erstellt (Key: {'*' * 10}...)")

def find_build_folder() -> Path:
    build_dir = BASE_PATH / "build"
    
    if not build_dir.exists():
        print("   FEHLER: build/ nicht gefunden!")
        sys.exit(1)
    
    # Finde alle exe.win-* Ordner und nimm den mit der hoechsten Python-Version
    exe_folders = [f for f in build_dir.iterdir() if f.is_dir() and f.name.startswith("exe.win")]
    
    if not exe_folders:
        print("   FEHLER: Kein exe.win-* Ordner!")
        sys.exit(1)
    
    # Sortiere nach Name (3.13 > 3.12) und nimm den neuesten
    exe_folders.sort(key=lambda x: x.name, reverse=True)
    folder = exe_folders[0]
    
    # Pruefe ob actScriber.exe existiert
    exe_path = folder / f"{APP_NAME}.exe"
    if not exe_path.exists():
        print(f"   FEHLER: {APP_NAME}.exe nicht in {folder.name} gefunden!")
        sys.exit(1)
    
    print(f"   OK Build-Ordner: {folder.name}")
    return folder

def collect_files(build_folder: Path) -> list:
    """Sammelt alle Dateien aus dem Build-Ordner."""
    files = []
    for item in build_folder.rglob("*"):
        if item.is_file():
            rel_path = item.relative_to(build_folder)
            files.append((rel_path, item))
    return files

def build_directory_tree(directories: set) -> dict:
    """Baut einen hierarchischen Verzeichnisbaum."""
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
    """Generiert rekursiv die XML-Directory-Struktur."""
    xml_parts = []
    spaces = " " * indent
    
    for child_path in tree.get(parent_key, []):
        dir_id = sanitize_id(str(child_path).replace("/", "_").replace("\\", "_"), "D_")
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
    
    # Sammle alle Verzeichnisse
    directories = set()
    for rel_path, _ in files:
        parent = rel_path.parent
        while parent != Path("."):
            directories.add(parent)
            parent = parent.parent
    
    print(f"   OK {len(directories)} Verzeichnisse")
    
    # Baue Verzeichnisbaum
    dir_refs = {}
    tree = build_directory_tree(directories)
    dir_elements = generate_directory_xml(tree, dir_refs)
    
    # Generiere Component-Elemente
    component_elements = []
    component_refs = []
    
    for rel_path, full_path in files:
        path_str = str(rel_path).replace("/", "_").replace("\\", "_")
        file_id = sanitize_id(path_str, "F_")
        comp_id = sanitize_id(path_str, "C_")
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
    
    # Erstelle die komplette WXS-Datei mit UI
    wxs_content = f'''<?xml version="1.0" encoding="utf-8"?>
<!--
================================================================================
  actScriber WiX Package Definition (MIT GUI)
  Automatisch generiert - NICHT MANUELL BEARBEITEN!
  Version: {VERSION}
================================================================================
-->
<Wix xmlns="http://wixtoolset.org/schemas/v4/wxs"
     xmlns:util="http://wixtoolset.org/schemas/v4/wxs/util"
     xmlns:ui="http://wixtoolset.org/schemas/v4/wxs/ui">
  
  <Package
    Name="{APP_DISPLAY_NAME}"
    Manufacturer="{MANUFACTURER}"
    Version="{VERSION}"
    UpgradeCode="{UPGRADE_CODE}"
    ProductCode="{PRODUCT_CODE}"
    Scope="perMachine"
    Compressed="yes"
    Language="1031">
    
    <!-- ================================================================== -->
    <!-- UPGRADE-LOGIK                                                      -->
    <!-- ================================================================== -->
    <MajorUpgrade 
      DowngradeErrorMessage="Eine neuere Version von {APP_DISPLAY_NAME} ist bereits installiert."
      Schedule="afterInstallInitialize" />
    
    <!-- Hohe Kompression für kleinere MSI -->
    <MediaTemplate EmbedCab="yes" CompressionLevel="high" />
    
    <!-- ================================================================== -->
    <!-- GUI: Installer-Oberfläche                                         -->
    <!-- ================================================================== -->
    <ui:WixUI Id="WixUI_InstallDir" InstallDirectory="INSTALLFOLDER" />
    <WixVariable Id="WixUILicenseRtf" Value="license.rtf" />
    
    <!-- ================================================================== -->
    <!-- CLOSE APPLICATION (funktioniert auch im Silent-Modus!)            -->
    <!-- ================================================================== -->
    <!-- 
      - CloseMessage: Sendet WM_CLOSE fuer benutzerfreundliches Schliessen
      - ElevatedCloseMessage: Funktioniert auch mit Admin-Rechten
      - Timeout: Max. 10 Sekunden warten
      - TerminateProcess: 0 = nicht erzwingen (sicherer)
      - Automatisches Scheduling in UI + Execute Sequence
    -->
    <util:CloseApplication
      Id="CloseActScriber"
      Target="{APP_NAME}.exe"
      Description="{APP_DISPLAY_NAME} wird geschlossen, um das Update zu installieren."
      CloseMessage="yes"
      ElevatedCloseMessage="yes"
      Timeout="10"
      TerminateProcess="0"
      RebootPrompt="no" />
    
    <!-- ================================================================== -->
    <!-- FEATURES                                                           -->
    <!-- ================================================================== -->
    <Feature Id="MainFeature" Title="{APP_DISPLAY_NAME}" Level="1">
      <ComponentGroupRef Id="AppComponents" />
      <ComponentRef Id="StartMenuShortcut" />
      <ComponentRef Id="DesktopShortcut" />
    </Feature>
    
    <!-- ================================================================== -->
    <!-- ICONS                                                              -->
    <!-- ================================================================== -->
    <Icon Id="AppIcon.ico" SourceFile="icon.ico" />
    <Property Id="ARPPRODUCTICON" Value="AppIcon.ico" />
    <Property Id="ARPHELPLINK" Value="https://www.actlegal.com" />
    
  </Package>
  
  <!-- ====================================================================== -->
  <!-- VERZEICHNISSTRUKTUR                                                   -->
  <!-- ====================================================================== -->
  <Fragment>
    <StandardDirectory Id="ProgramFilesFolder">
      <Directory Id="INSTALLFOLDER" Name="{APP_NAME}">
{dir_elements}
      </Directory>
    </StandardDirectory>
    
    <StandardDirectory Id="ProgramMenuFolder">
      <Directory Id="AppMenuFolder" Name="{APP_DISPLAY_NAME}" />
    </StandardDirectory>
    
    <StandardDirectory Id="DesktopFolder" />
  </Fragment>
  
  <!-- ====================================================================== -->
  <!-- VERKNÜPFUNGEN                                                         -->
  <!-- ====================================================================== -->
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
  
  <!-- ====================================================================== -->
  <!-- ALLE ANWENDUNGSDATEIEN                                               -->
  <!-- ====================================================================== -->
  <Fragment>
    <ComponentGroup Id="AppComponents">
{chr(10).join(component_refs)}
    </ComponentGroup>
    {''.join(component_elements)}
  </Fragment>
  
</Wix>
'''
    
    # Speichere WXS-Datei
    wxs_path = BASE_PATH / "Package.wxs"
    with open(wxs_path, "w", encoding="utf-8") as f:
        f.write(wxs_content)
    
    print(f"   OK Package.wxs generiert")
    return str(wxs_path)

def run_wix_build(build_folder: Path):
    print_step(5, "Erstelle MSI (WiX)")
    
    # WiX build Command mit UI Extension
    cmd = [
        "wix", "build",
        "Package.wxs",
        "-arch", "x64",
        "-ext", "WixToolset.Util.wixext",
        "-ext", "WixToolset.UI.wixext",
        "-b", str(build_folder),  # bindpath: cx_Freeze Output
        "-b", str(BASE_PATH),     # für icon.ico und license.rtf
        "-o", str(BASE_PATH / OUTPUT_MSI)
    ]
    
    print(f"   Kommando: wix build Package.wxs ...")
    
    result = subprocess.run(cmd, cwd=BASE_PATH, check=False, capture_output=True, text=True)
    
    if result.returncode != 0:
        print("   FEHLER: WiX build fehlgeschlagen!")
        print("\n   STDERR:")
        print(result.stderr[:2000] if result.stderr else "(leer)")
        sys.exit(1)
    
    # Prüfe ob MSI erstellt wurde
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
     - GUI-Installer mit Willkommens-Dialog
     - Lizenzvereinbarung
     - Installationspfad-Auswahl
     - Fortschrittsanzeige
     - Automatisches Schliessen der App bei Updates
     - Startmenue + Desktop Verknuepfung
     - Systemsteuerungs-Eintrag mit Icon

  Installation:
     Doppelklick auf {OUTPUT_MSI}
     
  Silent Install (fuer IT):
     msiexec /i "{OUTPUT_MSI}" /qn
""")

def main():
    print_header()
    
    # Pruefe Voraussetzungen
    if not LICENSE_PATH.exists():
        print(f"   WARNUNG: license.rtf nicht gefunden - wird fuer WixUI benoetigt!")
        sys.exit(1)
    
    # 1. Clean
    clean_build()
    
    # 2. cx_Freeze
    run_cx_freeze()
    
    # Finde Build-Ordner
    build_folder = find_build_folder()

    # 3. Erstelle .env Datei
    create_env_file(build_folder)

    # 4. Generiere WXS
    generate_wxs(build_folder)

    # 5. WiX Build
    run_wix_build(build_folder)

    # Zusammenfassung
    print_summary()

if __name__ == "__main__":
    main()
