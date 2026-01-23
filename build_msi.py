
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

# Dependencies - OPTIMIERT für kleine Dateigröße
build_exe_options = {
    "packages": [
        "os", "sys", "PySide6.QtCore", "PySide6.QtGui", "PySide6.QtWidgets",
        "PySide6.QtSvg", "PySide6.QtNetwork",
        "qtawesome", "pynput",
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
    "excludes": [
        # Nicht benötigte Standard-Module
        "tkinter", "unittest", "email", "html", "http", "xml", "pydoc",
        "test", "distutils", "setuptools", "pip",
        # PyQt6 - wir nutzen PySide6!
        "PyQt6", "PyQt5",
        # Nicht benötigte PySide6 Module (WebEngine, 3D, QML, etc.)
        "PySide6.QtWebEngine", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets",
        "PySide6.QtWebChannel", "PySide6.QtWebSockets",
        "PySide6.QtQuick", "PySide6.QtQuickWidgets", "PySide6.QtQml",
        "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.Qt3DInput",
        "PySide6.Qt3DLogic", "PySide6.Qt3DAnimation", "PySide6.Qt3DExtras",
        "PySide6.QtCharts", "PySide6.QtDataVisualization",
        "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets",
        "PySide6.QtBluetooth", "PySide6.QtNfc", "PySide6.QtPositioning",
        "PySide6.QtLocation", "PySide6.QtSensors", "PySide6.QtSerialPort",
        "PySide6.QtDesigner", "PySide6.QtHelp", "PySide6.QtPdf",
        "PySide6.QtRemoteObjects", "PySide6.QtScxml", "PySide6.QtSql",
        "PySide6.QtTest", "PySide6.QtXml",
    ],
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
