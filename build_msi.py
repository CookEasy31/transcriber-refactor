
import sys
import os
from cx_Freeze import setup, Executable

# --- KONFIGURATION ---
APP_NAME = "actScriber"
DESCRIPTION = "act Scriber - AI Transcriber"
VERSION = "1.3.7"
AUTHOR = "act legal IT"

# Assets befinden sich im selben Verzeichnis wie dieses Skript
BASE_PATH = os.path.dirname(os.path.abspath(__file__))
ICON_PATH = os.path.join(BASE_PATH, "icon.ico")
LOGO_PATH = os.path.join(BASE_PATH, "act_scriber_transparent.png")
TRAY_ICON_PATH = os.path.join(BASE_PATH, "act_only_transparent.png")

# Dependencies
# PySide6: Qt DLLs werden automatisch inkludiert
build_exe_options = {
    "packages": [
        "os", "sys", "PySide6", "qtawesome", "pynput", 
        "groq", "sounddevice", "numpy", "pyperclip", 
        "pyautogui", "winreg", "ctypes", "sqlite3", "json",
        "logging", "threading", "time", "datetime", "wave", "struct",
        "psutil", "packaging", "PIL"
    ],
    "include_files": [
        (ICON_PATH, "icon.ico"),
        (LOGO_PATH, "act_scriber_transparent.png"),
        (TRAY_ICON_PATH, "act_only_transparent.png"),
    ],
    "excludes": ["tkinter", "unittest", "email", "html", "http", "xml", "pydoc"],
    "zip_exclude_packages": [
        "PySide6",            # Qt Plugins, DLLs
        "shiboken6",          # PySide6 Bindings
        "qtawesome",          # Font-Dateien
        "sounddevice",
        "_sounddevice_data",
        "numpy",
        "PIL"
    ],
}

base = None
if sys.platform == "win32":
    base = "gui"  # cx_Freeze 7.x+ uses "gui" instead of "Win32GUI"

setup(
    name=APP_NAME,
    version=VERSION,
    description=DESCRIPTION,
    author=AUTHOR,
    options={"build_exe": build_exe_options},
    executables=[
        Executable(
            "main.py",
            base=base,
            target_name="actScriber.exe",  # Interner Name ohne Leerzeichen
            icon=ICON_PATH,
            copyright="act legal IT"
        )
    ]
)
