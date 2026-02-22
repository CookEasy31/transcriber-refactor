
import sys
import os
from cx_Freeze import setup, Executable

# --- KONFIGURATION ---
APP_NAME = "actScriber"
DESCRIPTION = "act Scriber - AI Transcriber"
VERSION = "2.2.0"
AUTHOR = "act legal IT"

# Assets befinden sich im selben Verzeichnis wie dieses Skript
BASE_PATH = os.path.dirname(os.path.abspath(__file__))
ICON_PATH = os.path.join(BASE_PATH, "icon.ico")
LOGO_PATH = os.path.join(BASE_PATH, "act_scriber_transparent.png")
TRAY_ICON_PATH = os.path.join(BASE_PATH, "act_only_transparent.png")

# Dependencies - VOLLSTAENDIG fuer UI-Test (keine Optimierung)
build_exe_options = {
    "packages": [
        "os", "sys", "PySide6.QtCore", "PySide6.QtGui", "PySide6.QtWidgets",
        "PySide6.QtSvg", "PySide6.QtNetwork",
        "qtawesome", "pynput",
        "groq", "sounddevice", "numpy", "pyperclip",
        "pyautogui", "winreg", "ctypes", "sqlite3", "json",
        "logging", "threading", "time", "datetime", "wave", "struct",
        "psutil", "packaging", "PIL",
        "pydantic", "pydantic_core", "httpx", "httpcore", "h11", "anyio", "certifi"
    ],
    "include_files": [
        (ICON_PATH, "icon.ico"),
        (LOGO_PATH, "act_scriber_transparent.png"),
        (TRAY_ICON_PATH, "act_only_transparent.png"),
    ],
    "excludes": [
        # Nur absolut unnoetige Module
        "tkinter", "test", "PyQt6", "PyQt5",
    ],
    "zip_exclude_packages": [
        "PySide6",
        "shiboken6",
        "qtawesome",
        "sounddevice",
        "_sounddevice_data",
        "numpy",
        "PIL"
    ],
}

base = None
if sys.platform == "win32":
    base = "gui"

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
            target_name="actScriber.exe",
            icon=ICON_PATH,
            copyright="act legal IT"
        )
    ]
)
