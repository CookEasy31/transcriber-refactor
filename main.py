"""
ACT Scriber - PySide6 Law Firm Edition
Komplette Migration mit allen Features
"""

import sys
import os
import time
import threading
# numpy is lazy-loaded where needed for faster startup
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QTextEdit, QComboBox, QLineEdit,
    QFrame, QScrollArea, QGraphicsDropShadowEffect, QSlider,
    QMessageBox, QSystemTrayIcon, QMenu, QCheckBox, QSpinBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QProgressBar, QDialog, QDialogButtonBox, QFormLayout, QSizePolicy
)
from PySide6.QtCore import Qt, QSize, Signal, QObject, QThread, QTimer
from PySide6.QtGui import QFont, QColor, QIcon, QAction, QPixmap
import qtawesome as qta

# Import existing modules
from config import ConfigManager, LANGUAGES, TARGET_LANGUAGES, APP_NAME, APP_VERSION, APP_DATA_DIR, format_hotkey_name
from audio_handler import AudioRecorder, NO_AUDIO_DETECTED
from api_handler import APIHandler
from data_handler import DataHandler
from updater import check_for_updates, download_update, install_update

# Lazy imports
_pyperclip = None
_pyautogui = None
_pynput_keyboard = None


def _get_pyperclip():
    global _pyperclip
    if _pyperclip is None:
        import pyperclip
        _pyperclip = pyperclip
    return _pyperclip


def _get_pyautogui():
    global _pyautogui
    if _pyautogui is None:
        import pyautogui
        _pyautogui = pyautogui
    return _pyautogui


def _get_pynput():
    global _pynput_keyboard
    if _pynput_keyboard is None:
        from pynput import keyboard
        _pynput_keyboard = keyboard
    return _pynput_keyboard


def get_asset_path(filename):
    """Funktioniert in Dev UND installierter Version"""
    if getattr(sys, 'frozen', False):
        base_path = os.path.dirname(sys.executable)
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, filename)


def get_icon_path():
    return get_asset_path("icon.ico")


def is_dark_mode():
    """Erkennt Windows Dark Mode über Registry"""
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Themes\Personalize"
        )
        value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        winreg.CloseKey(key)
        return value == 0  # 0 = Dark Mode, 1 = Light Mode
    except Exception:
        return False  # Fallback: Light Mode


# Color Schemes - Modern Executive
COLORS_LIGHT = {
    "primary": "#374151",
    "accent": "#DC2626",
    "success": "#059669",
    "warning": "#D97706",
    "text_dark": "#111827",
    "text_light": "#6B7280",
    "bg_sidebar": "#F9FAFB",
    "bg_main": "#FFFFFF",
    "bg_card": "#FFFFFF",
    "bg_input": "#FFFFFF",
    "bg_elevated": "#FAFAFA",
    "border": "#E5E7EB",
    "active_bg": "#F3F4F6",
}

COLORS_DARK = {
    "primary": "#60A5FA",      # Helleres Blau für Dark Mode
    "accent": "#F87171",       # Helleres Rot
    "success": "#34D399",      # Helleres Grün
    "warning": "#FBBF24",      # Helleres Orange
    "text_dark": "#F9FAFB",    # Fast weiß für Text
    "text_light": "#9CA3AF",   # Mittleres Grau
    "bg_sidebar": "#1F2937",   # Dunkles Grau
    "bg_main": "#111827",      # Sehr dunkel
    "bg_card": "#1F2937",      # Dunkle Karten
    "bg_input": "#374151",     # Input-Felder
    "bg_elevated": "#374151",  # Erhöhte Elemente
    "border": "#374151",       # Dunklere Borders
    "active_bg": "#374151",    # Hover-States
}


def get_colors():
    """Gibt das passende Farbschema basierend auf System-Theme zurück"""
    return COLORS_DARK if is_dark_mode() else COLORS_LIGHT


# Legacy-Kompatibilität
COLORS = get_colors()


# ═══════════════════════════════════════════════════════════════
# WORKER THREAD FOR TRANSCRIPTION
# ═══════════════════════════════════════════════════════════════

class TranscriptionWorker(QThread):
    """Worker Thread für Transkription im Hintergrund"""
    finished = Signal(str, str)  # (final_text, raw_transcript)
    error = Signal(str)
    status = Signal(str)

    def __init__(self, api, config, data, audio_file):
        super().__init__()
        self.api = api
        self.config = config
        self.data = data
        self.audio_file = audio_file

    def run(self):
        try:
            self.status.emit("processing")
            print(f"[Worker] Starting transcription for: {self.audio_file}")

            print("[Worker] Calling api.transcribe()...")
            raw = self.api.transcribe(self.audio_file)
            print(f"[Worker] Transcribe returned: {len(raw) if raw else 0} chars")
            
            if not raw:
                raise Exception("Kein Text erkannt")

            mode = self.config.get("mode")
            print(f"[Worker] Calling api.process_llm() with mode: {mode}")
            final = self.api.process_llm(raw, mode)
            print(f"[Worker] process_llm returned: {len(final) if final else 0} chars")

            self.data.save_entry(mode, raw, final)
            print("[Worker] Entry saved to database")

            # Kopiere in Zwischenablage
            _get_pyperclip().copy(final)
            print("[Worker] Text copied to clipboard")

            # WICHTIG: Signal ZUERST emittieren für UI-Update
            self.finished.emit(final, raw)
            print("[Worker] Finished signal emitted")

            # Dann kurz warten und einfügen (im Worker-Thread)
            time.sleep(0.15)
            try:
                _get_pyautogui().hotkey("ctrl", "v")
                print("[Worker] Paste executed")
            except Exception as paste_err:
                print(f"[Worker] Paste failed: {paste_err}")

        except Exception as e:
            print(f"[Worker] ERROR: {e}")
            self.data.log(str(e), "error")
            self.error.emit(str(e))
        finally:
            try:
                if self.audio_file and os.path.exists(self.audio_file):
                    os.remove(self.audio_file)
            except:
                pass


# ═══════════════════════════════════════════════════════════════
# DEVICE LOADING WORKER
# ═══════════════════════════════════════════════════════════════

class DeviceLoadWorker(QThread):
    """Worker Thread für Geräte-Enumeration (blockiert sonst UI)"""
    finished = Signal(list)  # List of devices

    def __init__(self, recorder):
        super().__init__()
        self.recorder = recorder

    def run(self):
        try:
            # test_functionality=False for fast dropdown population
            # Devices are tested when actually used, not during enumeration
            devices = self.recorder.reload_devices(test_functionality=False)
            self.finished.emit(devices)
        except Exception as e:
            print(f"[DeviceLoad] Error: {e}")
            self.finished.emit([])


# ═══════════════════════════════════════════════════════════════
# REFINEMENT WORKER
# ═══════════════════════════════════════════════════════════════

class RefinementWorker(QThread):
    """Worker Thread für Nachbearbeitung"""
    finished = Signal(str)
    error = Signal(str)

    def __init__(self, api, text, style, custom_instruction=None):
        super().__init__()
        self.api = api
        self.text = text
        self.style = style
        self.custom_instruction = custom_instruction

    def run(self):
        try:
            result = self.api.refine_text(self.text, self.style, self.custom_instruction)
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))


# ═══════════════════════════════════════════════════════════════
# UPDATE WORKER
# ═══════════════════════════════════════════════════════════════

class UpdateCheckWorker(QThread):
    """Worker Thread für Update-Check im Hintergrund"""
    finished = Signal(dict)

    def run(self):
        try:
            result = check_for_updates()
            self.finished.emit(result)
        except Exception as e:
            self.finished.emit({'error': str(e), 'update_available': False})


class UpdateDownloadWorker(QThread):
    """Worker Thread für Update-Download"""
    progress = Signal(int)
    finished = Signal(str)  # Pfad zur MSI
    error = Signal(str)

    def __init__(self, url, target_dir):
        super().__init__()
        self.url = url
        self.target_dir = target_dir

    def run(self):
        try:
            path = download_update(
                self.url,
                self.target_dir,
                progress_callback=lambda p: self.progress.emit(p)
            )
            self.finished.emit(path)
        except Exception as e:
            self.error.emit(str(e))


# ═══════════════════════════════════════════════════════════════
# FORCE UPDATE DIALOG
# ═══════════════════════════════════════════════════════════════

class ForceUpdateDialog(QDialog):
    """Modal Dialog für erzwungene Updates - kann nicht geschlossen werden"""

    def __init__(self, parent, version, release_notes):
        super().__init__(parent)
        self.setWindowTitle("Wichtiges Update erforderlich")
        self.setMinimumWidth(450)
        self.setModal(True)
        # Fenster-Schließen verhindern
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowCloseButtonHint)

        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)

        # Header
        header = QLabel(f"Update auf Version {version}")
        header.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        layout.addWidget(header)

        # Info
        info = QLabel("Ein wichtiges Update wird heruntergeladen und installiert.\nDie App wird automatisch neu gestartet.")
        info.setFont(QFont("Segoe UI", 11))
        info.setWordWrap(True)
        layout.addWidget(info)

        # Release Notes (kurz)
        if release_notes:
            notes_preview = release_notes[:200] + "..." if len(release_notes) > 200 else release_notes
            notes_label = QLabel(notes_preview)
            notes_label.setFont(QFont("Segoe UI", 10))
            notes_label.setStyleSheet(f"color: {COLORS['text_light']}; background: {COLORS['active_bg']}; padding: 10px; border-radius: 6px;")
            notes_label.setWordWrap(True)
            layout.addWidget(notes_label)

        # Progress Bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("Herunterladen... %p%")
        layout.addWidget(self.progress_bar)

        # Status Label
        self.status_label = QLabel("Verbinde mit Server...")
        self.status_label.setFont(QFont("Segoe UI", 10))
        self.status_label.setStyleSheet(f"color: {COLORS['text_light']};")
        layout.addWidget(self.status_label)

    def set_progress(self, percent):
        self.progress_bar.setValue(percent)
        if percent >= 100:
            self.status_label.setText("Installation wird gestartet...")
            self.progress_bar.setFormat("Fertig!")

    def closeEvent(self, event):
        # Schließen verhindern
        event.ignore()


# ═══════════════════════════════════════════════════════════════
# CUSTOM BUTTON DIALOG
# ═══════════════════════════════════════════════════════════════

class CustomButtonDialog(QDialog):
    """Dialog zum Erstellen/Bearbeiten von Custom Buttons"""

    def __init__(self, parent=None, button_data=None):
        super().__init__(parent)
        self.setWindowTitle("Custom Button" if not button_data else "Button bearbeiten")
        self.setMinimumWidth(400)

        layout = QVBoxLayout(self)

        form = QFormLayout()

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("z.B. 'Formell umschreiben'")
        if button_data:
            self.name_input.setText(button_data.get("name", ""))
        form.addRow("Button-Name:", self.name_input)

        self.instruction_input = QTextEdit()
        self.instruction_input.setPlaceholderText("z.B. 'Schreibe den Text in einem formellen, geschäftlichen Ton um.'")
        self.instruction_input.setMaximumHeight(100)
        if button_data:
            self.instruction_input.setPlainText(button_data.get("instruction", ""))
        form.addRow("Anweisung:", self.instruction_input)

        self.icon_combo = QComboBox()
        icons = [
            ("fa5s.magic", "Zauberstab"),
            ("fa5s.pen", "Stift"),
            ("fa5s.file-alt", "Dokument"),
            ("fa5s.balance-scale", "Waage"),
            ("fa5s.gavel", "Hammer"),
            ("fa5s.briefcase", "Aktentasche"),
            ("fa5s.user-tie", "Person"),
            ("fa5s.handshake", "Händedruck"),
        ]
        for icon_name, icon_label in icons:
            self.icon_combo.addItem(qta.icon(icon_name, color=COLORS['primary']), icon_label, icon_name)
        if button_data:
            idx = self.icon_combo.findData(button_data.get("icon", "fa5s.magic"))
            if idx >= 0:
                self.icon_combo.setCurrentIndex(idx)
        form.addRow("Icon:", self.icon_combo)

        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_data(self):
        return {
            "name": self.name_input.text().strip(),
            "instruction": self.instruction_input.toPlainText().strip(),
            "icon": self.icon_combo.currentData()
        }


class CustomButtonManagerDialog(QDialog):
    """Dialog zur Verwaltung aller Custom Buttons"""

    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.colors = COLORS  # Global colors reference
        self.setWindowTitle("Buttons verwalten")
        self.setMinimumWidth(500)
        self.setMinimumHeight(400)

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(20, 20, 20, 20)
        self.layout.setSpacing(15)

        title = QLabel("Gespeicherte Buttons")
        title.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        self.layout.addWidget(title)

        # Scroll Area für die Liste
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.list_container = QWidget()
        self.list_layout = QVBoxLayout(self.list_container)
        self.list_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.list_layout.setSpacing(10)
        scroll.setWidget(self.list_container)
        self.layout.addWidget(scroll)

        self.refresh_list()

        # Schließen Button
        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btn_box.rejected.connect(self.accept)
        self.layout.addWidget(btn_box)

    def refresh_list(self):
        """Aktualisiert die Liste der Buttons im Dialog"""
        # Clear layout
        while self.list_layout.count():
            item = self.list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        buttons_data = self.parent.config.get("custom_buttons") or []
        
        if not buttons_data:
            empty_label = QLabel("Keine Custom Buttons vorhanden.")
            empty_label.setStyleSheet(f"color: {self.colors['text_light']}; font-style: italic;")
            self.list_layout.addWidget(empty_label)
            return

        for idx, btn_data in enumerate(buttons_data):
            row = QFrame()
            row.setStyleSheet(f"background: {self.colors['bg_sidebar']}; border-radius: 8px; border: 1px solid {self.colors['border']};")
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(12, 8, 12, 8)

            # Icon + Name
            icon_label = QLabel()
            icon_label.setPixmap(qta.icon(btn_data['icon'], color=COLORS['primary']).pixmap(20, 20))
            row_layout.addWidget(icon_label)

            name_label = QLabel(btn_data['name'])
            name_label.setFont(QFont("Segoe UI", 11, QFont.Weight.Medium))
            row_layout.addWidget(name_label, 1)

            # Edit Button
            edit_btn = QPushButton()
            edit_btn.setIcon(qta.icon('fa5s.edit', color=COLORS['primary']))
            edit_btn.setFixedSize(32, 32)
            edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            edit_btn.setToolTip("Bearbeiten")
            edit_btn.clicked.connect(lambda checked=False, d=btn_data, i=idx: self.edit_button(i, d))
            row_layout.addWidget(edit_btn)

            # Delete Button
            del_btn = QPushButton()
            del_btn.setIcon(qta.icon('fa5s.trash-alt', color=self.colors["accent"]))
            del_btn.setFixedSize(32, 32)
            del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            del_btn.setToolTip("Löschen")
            del_btn.clicked.connect(lambda checked=False, i=idx: self.delete_button(i))
            row_layout.addWidget(del_btn)

            self.list_layout.addWidget(row)

    def edit_button(self, index, data):
        dialog = CustomButtonDialog(self, data)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_data = dialog.get_data()
            if new_data["name"] and new_data["instruction"]:
                buttons_data = self.parent.config.get("custom_buttons")
                buttons_data[index] = new_data
                self.parent.config.set("custom_buttons", buttons_data)
                self.parent.load_custom_buttons() # UI Refresh
                self.refresh_list()

    def delete_button(self, index):
        reply = QMessageBox.question(
            self, "Button löschen",
            "Möchten Sie diesen Button wirklich löschen?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            buttons_data = self.parent.config.get("custom_buttons")
            buttons_data.pop(index)
            self.parent.config.set("custom_buttons", buttons_data)
            self.parent.load_custom_buttons() # UI Refresh
            self.refresh_list()


# ═══════════════════════════════════════════════════════════════
# OVERLAY WINDOW
# ═══════════════════════════════════════════════════════════════

class OverlayWindow(QWidget):
    """Kleines Overlay-Fenster das den Status anzeigt"""

    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(60, 60)

        screen = QApplication.primaryScreen().geometry()
        self.move(screen.width() - 80, screen.height() - 120)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.status_label = QLabel()
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setFixedSize(50, 50)
        layout.addWidget(self.status_label)

        self._current_status = "idle"
        self.set_status("idle")

        self.hide_timer = QTimer()
        self.hide_timer.timeout.connect(self.hide)
        self.hide_timer.setSingleShot(True)

    def set_status(self, status):
        self._current_status = status

        status_config = {
            "idle": {"icon": "fa5s.circle", "color": "#9CA3AF", "bg": "#F3F4F6"},
            "recording": {"icon": "fa5s.microphone", "color": "#FFFFFF", "bg": "#DC2626"},
            "processing": {"icon": "fa5s.spinner", "color": "#FFFFFF", "bg": "#2563EB"},
            "success": {"icon": "fa5s.check", "color": "#FFFFFF", "bg": "#059669"},
            "error": {"icon": "fa5s.exclamation-triangle", "color": "#FFFFFF", "bg": "#DC2626"},
            "aborted": {"icon": "fa5s.times", "color": "#FFFFFF", "bg": "#6B7280"},
        }

        cfg = status_config.get(status, status_config["idle"])

        self.status_label.setStyleSheet(f"""
            background-color: {cfg['bg']};
            border-radius: 25px;
        """)

        icon = qta.icon(cfg['icon'], color=cfg['color'])
        self.status_label.setPixmap(icon.pixmap(24, 24))

        if status in ["recording", "processing"]:
            self.show()
            self.hide_timer.stop()
        elif status in ["success", "error", "aborted"]:
            self.show()
            self.hide_timer.start(2000)
        else:
            self.hide()


# ═══════════════════════════════════════════════════════════════
# MATERIAL CARD
# ═══════════════════════════════════════════════════════════════

class MaterialCard(QFrame):
    """Material Design Card mit Elevation"""
    def __init__(self, elevation=2):
        super().__init__()
        self.setObjectName("MaterialCard")
        
        colors = get_colors()
        shadow_alpha = 10 if is_dark_mode() else 20

        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(elevation * 4)
        shadow.setXOffset(0)
        shadow.setYOffset(elevation * 1.5)
        shadow.setColor(QColor(0, 0, 0, shadow_alpha))
        self.setGraphicsEffect(shadow)

        self.setStyleSheet(f"""
            #MaterialCard {{
                background-color: {colors['bg_card']};
                border-radius: 10px;
                padding: 20px;
                border: 1px solid {colors['border']};
            }}
        """)




# ═══════════════════════════════════════════════════════════════
# MICROPHONE TEST DIALOG
# ═══════════════════════════════════════════════════════════════

class MicrophoneTestDialog(QDialog):
    """Dialog zum Testen aller Mikrofone mit Live-Level-Anzeige.

    - Pausiert Haupt-Stream um Konflikte zu vermeiden
    - Testet alle Geräte PARALLEL
    - Sortiert nach 3 Sekunden: Geräte mit Pegel oben
    """
    def __init__(self, parent=None, main_recorder=None):
        super().__init__(parent)
        self.setWindowTitle("Mikrofone testen")
        self.setMinimumSize(500, 400)
        self.setModal(True)

        self.colors = get_colors()
        self.main_recorder = main_recorder
        self.streams = []
        self.device_data = {}  # {device_id: {'bar': QProgressBar, 'row': QWidget, 'rms': float, 'max_rms': float}}
        self.running = True
        self.sorted = False

        # Pausiere Haupt-Stream SOFORT
        if self.main_recorder and self.main_recorder._unified_stream:
            print("[MicTest] Pausiere Haupt-Audio-Stream...")
            self.main_recorder.stop_monitor()

        self.setup_ui()
        self.load_devices()
        self.start_all_streams()

        # Timer für UI-Updates
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self._update_all_levels)
        self.update_timer.start(50)  # 20 FPS

        # Nach 3 Sekunden sortieren
        QTimer.singleShot(3000, self._sort_by_level)

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Header
        header = QLabel("Sprechen Sie in Ihr Mikrofon um es zu testen")
        header.setFont(QFont("Segoe UI", 12))
        header.setStyleSheet(f"color: {self.colors['text_light']};")
        layout.addWidget(header)

        # Scroll area for devices
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_content = QWidget()
        self.devices_layout = QVBoxLayout(self.scroll_content)
        self.devices_layout.setSpacing(8)
        self.scroll.setWidget(self.scroll_content)
        layout.addWidget(self.scroll)

        # Close button
        close_btn = QPushButton("Schließen")
        close_btn.setObjectName("ActionButton")
        close_btn.setProperty("button_style", "primary")
        close_btn.clicked.connect(self.close)
        close_btn.setMinimumHeight(40)
        layout.addWidget(close_btn)

    def load_devices(self):
        import sounddevice as sd
        devices = sd.query_devices()

        seen_names = set()  # Duplikat-Filter
        for i, dev in enumerate(devices):
            if dev["max_input_channels"] > 0:
                name = dev["name"]
                name_lower = name.lower()

                # Skip irrelevante Geräte
                if any(kw in name_lower for kw in ["stereo mix", "output", "loopback", "virtual"]):
                    continue

                # Skip Duplikate (gleiches Gerät für verschiedene Audio-APIs)
                # Vergleiche nur die ersten 25 Zeichen (Namen werden manchmal abgeschnitten)
                name_key = name[:25]
                if name_key in seen_names:
                    continue
                seen_names.add(name_key)

                row = QWidget()
                row_layout = QHBoxLayout(row)
                row_layout.setContentsMargins(8, 4, 8, 4)

                name_label = QLabel(dev["name"][:40] + ("..." if len(dev["name"]) > 40 else ""))
                name_label.setFont(QFont("Segoe UI", 10))
                name_label.setFixedWidth(250)
                name_label.setToolTip(dev["name"])
                row_layout.addWidget(name_label)

                level_bar = QProgressBar()
                level_bar.setMinimum(0)
                level_bar.setMaximum(100)
                level_bar.setValue(0)
                level_bar.setTextVisible(False)
                level_bar.setMinimumHeight(16)
                level_bar.setStyleSheet(f"""
                    QProgressBar {{
                        border: 1px solid {self.colors['border']};
                        border-radius: 4px;
                        background-color: {self.colors['bg_elevated']};
                    }}
                    QProgressBar::chunk {{
                        background-color: {self.colors['success']};
                        border-radius: 3px;
                    }}
                """)
                row_layout.addWidget(level_bar)

                self.device_data[i] = {
                    'bar': level_bar,
                    'row': row,
                    'name': dev["name"],
                    'rms': 0.0,
                    'max_rms': 0.0
                }
                self.devices_layout.addWidget(row)

        self.devices_layout.addStretch()

    def start_all_streams(self):
        """Startet Streams für alle Geräte parallel"""
        import sounddevice as sd
        import numpy as np

        def make_callback(device_id):
            def callback(indata, frames, time_info, status):
                if self.running and indata.size > 0:
                    rms = float(np.sqrt(np.mean(indata**2)))
                    if device_id in self.device_data:
                        self.device_data[device_id]['rms'] = rms
                        # Track maximum für Sortierung
                        if rms > self.device_data[device_id]['max_rms']:
                            self.device_data[device_id]['max_rms'] = rms
            return callback

        for device_id in self.device_data.keys():
            try:
                stream = sd.InputStream(
                    samplerate=16000,
                    device=device_id,
                    channels=1,
                    blocksize=1024,
                    callback=make_callback(device_id)
                )
                stream.start()
                self.streams.append(stream)
                print(f"[MicTest] Stream gestartet für Device {device_id}")
            except Exception as e:
                print(f"[MicTest] Fehler bei Device {device_id}: {e}")
                bar = self.device_data[device_id]['bar']
                bar.setStyleSheet(f"""
                    QProgressBar {{
                        border: 1px solid {self.colors['accent']};
                        border-radius: 4px;
                        background-color: {self.colors['bg_elevated']};
                    }}
                """)
                bar.setFormat("Nicht verfügbar")
                bar.setTextVisible(True)

    def _update_all_levels(self):
        """Aktualisiert alle Level-Anzeigen"""
        if not self.running:
            return

        for device_id, data in self.device_data.items():
            level = min(int(data['rms'] * 500), 100)
            data['bar'].setValue(level)

    def _sort_by_level(self):
        """Sortiert die Liste nach erkanntem Pegel (höchster oben)"""
        if self.sorted or not self.running:
            return

        self.sorted = True
        print("[MicTest] Sortiere nach Pegel...")

        # Sortiere nach max_rms (absteigend)
        sorted_devices = sorted(
            self.device_data.items(),
            key=lambda x: x[1]['max_rms'],
            reverse=True
        )

        # Entferne alle Widgets aus dem Layout (rückwärts um Index-Probleme zu vermeiden)
        for i in reversed(range(self.devices_layout.count())):
            item = self.devices_layout.itemAt(i)
            if item.widget():
                # Widget vom Layout entfernen ohne zu löschen
                self.devices_layout.removeWidget(item.widget())
            else:
                # Spacer/Stretch entfernen
                self.devices_layout.removeItem(item)

        # Füge in neuer Reihenfolge hinzu
        for device_id, data in sorted_devices:
            self.devices_layout.addWidget(data['row'])
            print(f"[MicTest] Device {device_id} ({data['name'][:20]}): max_rms={data['max_rms']:.4f}")

        self.devices_layout.addStretch()

    def closeEvent(self, event):
        self.running = False
        self.update_timer.stop()

        # Alle Streams schließen
        for stream in self.streams:
            try:
                stream.stop()
                stream.close()
            except:
                pass
        self.streams.clear()

        # Haupt-Recorder Stream wieder starten
        if self.main_recorder:
            print("[MicTest] Starte Haupt-Audio-Stream wieder...")
            parent = self.parent()
            if parent and hasattr(parent, 'config'):
                device_index = parent.config.get("device_index")
                device_name = parent.config.get("device_name")
                self.main_recorder.start_monitor(device_index, device_name)

        super().closeEvent(event)


# ═══════════════════════════════════════════════════════════════
# MAIN APPLICATION
# ═══════════════════════════════════════════════════════════════

class ACTScriber(QMainWindow):
    # Signals for thread-safe UI updates from hotkey listener
    hotkey_set_signal = Signal(str)
    overlay_status_signal = Signal(str)
    transcription_signal = Signal(str)  # For starting transcription from hotkey thread
    no_audio_warning_signal = Signal()
    # Signals for auto-updater
    update_available_signal = Signal(dict)
    force_update_signal = Signal(dict)

    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)  # Just "act Scriber", no version
        self.setGeometry(100, 100, 1100, 700)
        
        # Set window/taskbar icon
        icon_path = get_icon_path()
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        
        # Connect signals for thread-safe UI updates
        self.hotkey_set_signal.connect(self._on_hotkey_set)
        self.overlay_status_signal.connect(self._on_overlay_status)
        self.transcription_signal.connect(self._on_start_transcription)
        self.no_audio_warning_signal.connect(self.show_no_audio_warning)

        # Core Components
        self.config = ConfigManager()
        self.data = DataHandler()
        self.api = APIHandler(self.config, self.data)
        self.recorder = AudioRecorder(
            device_index=self.config.get("device_index"),
            audio_sensitivity=self.config.get("audio_sensitivity")
        )

        # State
        self.is_setting_hotkey = False
        self.hotkey_lock = threading.Lock()
        self.current_worker = None
        self.colors = COLORS
        self.custom_buttons = []  # UI Buttons für Custom Instructions
        self._last_raw_transcript = None  # For repeat functionality
        self._audio_warning_shown = False  # Anti-loop: nur einmal warnen
        self._last_no_audio_warning_time = 0  # Cooldown fuer Audio-Warnung

        # Setup UI
        self.setup_ui()
        self.apply_color_scheme()

        # Setup Hotkey Listener
        self.setup_hotkey_listener()

        # Setup System Tray
        self.setup_system_tray()

        # Setup Overlay
        self.overlay = OverlayWindow()

        # Setup Audio Level Monitor
        self.setup_audio_monitor()

        # Load last entry if exists
        self.load_last_text()

        # Load custom buttons from config
        self.load_custom_buttons()

        # Setup Auto-Updater
        self.setup_auto_updater()

        # Start audio stream immediately for instant recording (fills pre-buffer)
        QTimer.singleShot(500, self._start_audio_monitor_delayed)

        # Show support page after update (What's New)
        QTimer.singleShot(100, self._check_show_whats_new)

    def _check_show_whats_new(self):
        """Shows support page if app was updated"""
        last_seen = self.config.get("last_seen_version")
        if last_seen != APP_VERSION:
            self.switch_view("help")
            self.config.set("last_seen_version", APP_VERSION)

    def _start_audio_monitor_delayed(self):
        """Starts audio monitoring after app is fully loaded"""
        device_index = self.config.get("device_index")
        device_name = self.config.get("device_name")
        self.recorder.start_monitor(device_index, device_name)

    def setup_auto_updater(self):
        """Initialisiert das Auto-Update-System"""
        self.pending_update = None  # Speichert verfügbares Update
        self.update_check_worker = None
        self.update_download_worker = None
        self.force_update_dialog = None

        # Signals verbinden
        self.update_available_signal.connect(self._on_update_available)
        self.force_update_signal.connect(self._on_force_update)

        # Erster Update-Check nach 3 Sekunden (App erst starten lassen)
        QTimer.singleShot(3000, self.check_for_updates_async)

        # Regelmäßiger Update-Check jede Minute
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.check_for_updates_async)
        self.update_timer.start(60 * 1000)  # 1 Minute in ms

    def check_for_updates_async(self):
        """Startet Update-Check im Hintergrund"""
        if self.update_check_worker and self.update_check_worker.isRunning():
            return  # Bereits ein Check aktiv

        self.update_check_worker = UpdateCheckWorker()
        self.update_check_worker.finished.connect(self._on_update_check_finished)
        self.update_check_worker.start()

    def _on_update_check_finished(self, result):
        """Callback wenn Update-Check abgeschlossen"""
        if result.get('error'):
            print(f"[Updater] Check failed: {result['error']}")
            return

        if not result.get('update_available'):
            print(f"[Updater] No update available (current: {result['current_version']})")
            return

        print(f"[Updater] Update available: {result['current_version']} -> {result['latest_version']}")

        self.pending_update = result

        # Alle Updates werden automatisch installiert (kein User-Klick nötig)
        self.force_update_signal.emit(result)

    def _on_update_available(self, update_info):
        """Optionales Update verfügbar - UI in Settings aktualisieren"""
        if hasattr(self, 'update_status_label'):
            version = update_info.get('latest_version', '?')
            self.update_status_label.setText(f"Version {version} verfügbar!")
            self.update_status_label.setStyleSheet(f"color: {self.colors['success']}; font-weight: bold;")
            self.update_btn.setVisible(True)
            self.update_btn.setEnabled(True)

    def _on_force_update(self, update_info):
        """Force Update - Dialog zeigen und Update starten"""
        if not update_info.get('download_url'):
            QMessageBox.warning(self, "Update-Fehler", "Keine Download-URL gefunden.")
            return

        # Force Update Dialog erstellen
        self.force_update_dialog = ForceUpdateDialog(
            self,
            update_info.get('latest_version', '?'),
            update_info.get('release_notes', '')
        )
        self.force_update_dialog.show()

        # Download starten
        self._start_update_download(update_info['download_url'])

    def _start_update_download(self, url):
        """Startet den Update-Download"""
        target_dir = os.path.join(APP_DATA_DIR, "updates")

        self.update_download_worker = UpdateDownloadWorker(url, target_dir)
        self.update_download_worker.progress.connect(self._on_download_progress)
        self.update_download_worker.finished.connect(self._on_download_finished)
        self.update_download_worker.error.connect(self._on_download_error)
        self.update_download_worker.start()

    def _on_download_progress(self, percent):
        """Download-Fortschritt aktualisieren"""
        if self.force_update_dialog:
            self.force_update_dialog.set_progress(percent)

    def _on_download_finished(self, msi_path):
        """Download abgeschlossen - Installation starten"""
        print(f"[Updater] Download complete: {msi_path}")
        if self.force_update_dialog:
            self.force_update_dialog.set_progress(100)

        # Kurz warten, dann Installation starten
        QTimer.singleShot(1000, lambda: self._install_update(msi_path))

    def _on_download_error(self, error):
        """Download-Fehler behandeln"""
        print(f"[Updater] Download error: {error}")
        if self.force_update_dialog:
            self.force_update_dialog.close()
        QMessageBox.critical(self, "Update-Fehler", f"Download fehlgeschlagen:\n{error}")

    def _install_update(self, msi_path):
        """Startet die MSI-Installation und beendet die App"""
        try:
            install_update(msi_path)
        except Exception as e:
            QMessageBox.critical(self, "Update-Fehler", f"Installation fehlgeschlagen:\n{e}")

    def start_manual_update(self):
        """Manuelles Update aus den Einstellungen starten"""
        if not self.pending_update or not self.pending_update.get('download_url'):
            return

        # Button deaktivieren
        self.update_btn.setEnabled(False)
        self.update_btn.setText("Wird heruntergeladen...")

        # Progress-Dialog für manuelles Update
        self.force_update_dialog = ForceUpdateDialog(
            self,
            self.pending_update.get('latest_version', '?'),
            self.pending_update.get('release_notes', '')
        )
        self.force_update_dialog.setWindowFlags(
            self.force_update_dialog.windowFlags() | Qt.WindowType.WindowCloseButtonHint
        )  # Schließen erlauben bei manuellem Update
        self.force_update_dialog.show()

        self._start_update_download(self.pending_update['download_url'])

    def setup_ui(self):
        """Erstellt die UI"""
        central = QWidget()
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Sidebar
        self.sidebar = self.create_sidebar()
        main_layout.addWidget(self.sidebar)

        # Divider
        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.VLine)
        divider.setObjectName("Divider")
        divider.setFixedWidth(1)
        main_layout.addWidget(divider)

        # Content Area - responsive layout
        content_scroll = QScrollArea()
        content_scroll.setWidgetResizable(True)
        content_scroll.setFrameShape(QFrame.Shape.NoFrame)
        content_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        self.content_stack = QWidget()
        self.content_stack.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding
        )
        self.content_layout = QVBoxLayout(self.content_stack)
        self.content_layout.setContentsMargins(0, 0, 0, 0)

        # Create all views
        self.home_view = self.create_home_view()
        self.history_view = self.create_history_view()
        self.settings_view = self.create_settings_view()
        self.help_view = self.create_help_view()

        # Add views
        self.content_layout.addWidget(self.home_view)
        self.content_layout.addWidget(self.history_view)
        self.content_layout.addWidget(self.settings_view)
        self.content_layout.addWidget(self.help_view)

        # Initial visibility
        self.home_view.setVisible(True)
        self.history_view.setVisible(False)
        self.settings_view.setVisible(False)
        self.help_view.setVisible(False)

        content_scroll.setWidget(self.content_stack)
        main_layout.addWidget(content_scroll, 1)

        self.setCentralWidget(central)

    def create_sidebar(self):
        """Erstellt die Navigations-Sidebar"""
        sidebar = QWidget()
        sidebar.setFixedWidth(200)
        sidebar.setObjectName("Sidebar")

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(16, 24, 16, 24)
        layout.setSpacing(6)

        # Logo
        logo_container = QWidget()
        logo_layout = QVBoxLayout(logo_container)
        logo_layout.setContentsMargins(0, 0, 0, 16)
        logo_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)

        # Add full-size logo image (no text) - HiDPI aware scaling
        logo_image_path = get_asset_path("act_scriber_transparent.png")
        if os.path.exists(logo_image_path):
            logo_pixmap = QPixmap(logo_image_path)  # Load original (1024x1024)
            
            # HiDPI Support: Calculate actual pixel size based on display scaling
            target_size = 150
            dpr = self.devicePixelRatio()  # e.g., 1.25, 1.5, 2.0 on scaled displays
            actual_size = int(target_size * dpr)
            
            # Scale to actual native pixels for crisp rendering
            scaled_logo = logo_pixmap.scaled(
                actual_size, actual_size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            # Set DPR so Qt knows this is a high-res image for the logical size
            scaled_logo.setDevicePixelRatio(dpr)
            
            logo_icon = QLabel()
            logo_icon.setPixmap(scaled_logo)
            logo_icon.setFixedSize(target_size, target_size)  # Logical size
            logo_layout.addWidget(logo_icon)
        else:
            # Fallback to text if image not found
            logo_label = QLabel("act Scriber")
            logo_label.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))
            logo_label.setObjectName("LogoLabel")
            logo_layout.addWidget(logo_label)

        layout.addWidget(logo_container)

        # Navigation Buttons - Icons 50% größer (15 → 22)
        nav_items = [
            ("Transkription", "fa5s.home", "home"),
            ("Verlauf", "fa5s.clock", "history"),
            ("Einstellungen", "fa5s.cog", "settings"),
            ("Support", "fa5s.life-ring", "help"),
        ]

        self.nav_buttons = {}
        for label, icon_name, view_id in nav_items:
            btn = QPushButton(f"  {label}")
            btn.setProperty("nav_active", view_id == "home")
            btn.setProperty("icon_name", icon_name)
            btn.setProperty("view_id", view_id)
            btn.setIconSize(QSize(22, 22))  # 50% größer
            btn.setMinimumHeight(42)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFont(QFont("Segoe UI", 11))
            btn.setObjectName("NavButton")
            btn.clicked.connect(lambda checked, v=view_id: self.switch_view(v))
            self.nav_buttons[view_id] = btn
            layout.addWidget(btn)

        layout.addStretch()

        # Version Info
        version_label = QLabel(f"Version {APP_VERSION}")
        version_label.setFont(QFont("Segoe UI", 8))
        version_label.setObjectName("VersionLabel")
        layout.addWidget(version_label)

        self.update_nav_icons()
        return sidebar

    def switch_view(self, view_id):
        """Wechselt zwischen Views"""
        self.home_view.setVisible(view_id == "home")
        self.history_view.setVisible(view_id == "history")
        self.settings_view.setVisible(view_id == "settings")
        self.help_view.setVisible(view_id == "help")

        for vid, btn in self.nav_buttons.items():
            is_active = vid == view_id
            btn.setProperty("nav_active", is_active)
            # Force style update for each button
            btn.style().unpolish(btn)
            btn.style().polish(btn)

        if view_id == "history":
            self.refresh_history()

        self.update_nav_icons()

        # In Settings: Geräteliste aktualisieren (Stream läuft bereits im Hintergrund)
        if view_id == "settings":
            self.refresh_devices()
            # Stream läuft bereits seit App-Start, nur sicherstellen dass er aktiv ist
            if not self.recorder._unified_stream:
                self.recorder.start_monitor(
                    device_index=self.config.get("device_index"),
                    device_name=self.config.get("device_name")
                )
        # WICHTIG: Stream NICHT stoppen - wird für Pre-Buffer benötigt!

    def _select_mode_and_go_home(self, mode_value):
        """Wählt einen Modus und wechselt zur Hauptseite"""
        self.mode_combo.setCurrentText(mode_value)
        self.switch_view("home")

    # ═══════════════════════════════════════════════════════════════
    # HOME VIEW
    # ═══════════════════════════════════════════════════════════════

    def create_home_view(self):
        """Erstellt die Home View"""
        view = QWidget()
        layout = QVBoxLayout(view)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(20)

        # Header
        header_label = QLabel("Bereit zur Aufnahme")
        header_label.setFont(QFont("Segoe UI", 24, QFont.Weight.Bold))
        header_label.setObjectName("HeaderLabel")
        layout.addWidget(header_label)

        # Hotkey Info
        hotkey_container = QWidget()
        hotkey_layout = QHBoxLayout(hotkey_container)
        hotkey_layout.setContentsMargins(0, 0, 0, 0)
        hotkey_layout.setSpacing(10)

        subtitle = QLabel("Aufnahme-Taste:")
        subtitle.setFont(QFont("Segoe UI", 11))
        subtitle.setObjectName("SubtitleText")
        hotkey_layout.addWidget(subtitle)

        current_hotkey = format_hotkey_name(self.config.get("hotkey"))
        self.hotkey_badge = QLabel(current_hotkey)
        self.hotkey_badge.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self.hotkey_badge.setObjectName("HotkeyBadge")
        hotkey_layout.addWidget(self.hotkey_badge)

        hint_label = QLabel("(mindestens 2 Sekunden gedrückt halten)")
        hint_label.setFont(QFont("Segoe UI", 10))
        hint_label.setObjectName("HintText")
        hotkey_layout.addWidget(hint_label)

        hotkey_layout.addStretch()
        layout.addWidget(hotkey_container)

        # Dropdowns Container
        dropdowns_container = QWidget()
        dropdowns_layout = QHBoxLayout(dropdowns_container)
        dropdowns_layout.setContentsMargins(0, 0, 0, 0)
        dropdowns_layout.setSpacing(16)

        # Mode Dropdown - ohne "Transkription"
        mode_container = QWidget()
        mode_layout = QVBoxLayout(mode_container)
        mode_layout.setContentsMargins(0, 0, 0, 0)
        mode_layout.setSpacing(6)

        mode_label = QLabel("Modus auswählen:")
        mode_label.setFont(QFont("Segoe UI", 10, QFont.Weight.Medium))
        mode_label.setObjectName("DropdownLabel")
        mode_layout.addWidget(mode_label)

        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["Diktat", "Dynamisches Diktat", "Übersetzer"])
        current_mode = self.config.get("mode")
        if current_mode == "Transkription":
            current_mode = "Diktat"
        self.mode_combo.setCurrentText(current_mode)
        self.mode_combo.setMinimumHeight(38)
        self.mode_combo.setFixedWidth(250)
        self.mode_combo.setObjectName("StyledCombo")
        self.mode_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        self.mode_combo.setFont(QFont("Segoe UI", 11))
        self.mode_combo.setMaxVisibleItems(8)
        self.mode_combo.currentTextChanged.connect(self.on_mode_changed)
        mode_layout.addWidget(self.mode_combo)
        dropdowns_layout.addWidget(mode_container)

        # Language Dropdown
        lang_container = QWidget()
        lang_layout = QVBoxLayout(lang_container)
        lang_layout.setContentsMargins(0, 0, 0, 0)
        lang_layout.setSpacing(6)

        lang_label = QLabel("Eingabesprache:")
        lang_label.setFont(QFont("Segoe UI", 10, QFont.Weight.Medium))
        lang_label.setObjectName("DropdownLabel")
        lang_layout.addWidget(lang_label)

        self.lang_combo = QComboBox()
        self.lang_combo.addItems(LANGUAGES)
        self.lang_combo.setCurrentText(self.config.get("language"))
        self.lang_combo.setMinimumHeight(38)
        self.lang_combo.setFixedWidth(250)
        self.lang_combo.setObjectName("StyledCombo")
        self.lang_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        self.lang_combo.setFont(QFont("Segoe UI", 11))
        self.lang_combo.setMaxVisibleItems(8)
        self.lang_combo.currentTextChanged.connect(self.on_language_changed)
        lang_layout.addWidget(self.lang_combo)
        dropdowns_layout.addWidget(lang_container)

        # Target Language (nur bei Übersetzer)
        self.target_lang_container = QWidget()
        target_lang_layout = QVBoxLayout(self.target_lang_container)
        target_lang_layout.setContentsMargins(0, 0, 0, 0)
        target_lang_layout.setSpacing(6)

        target_label = QLabel("Zielsprache:")
        target_label.setFont(QFont("Segoe UI", 10, QFont.Weight.Medium))
        target_label.setObjectName("DropdownLabel")
        target_lang_layout.addWidget(target_label)

        self.target_lang_combo = QComboBox()
        self.target_lang_combo.addItems(TARGET_LANGUAGES)
        self.target_lang_combo.setCurrentText(self.config.get("target_language"))
        self.target_lang_combo.setMinimumHeight(38)
        self.target_lang_combo.setFixedWidth(200)
        self.target_lang_combo.setObjectName("StyledCombo")
        self.target_lang_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        self.target_lang_combo.setFont(QFont("Segoe UI", 11))
        self.target_lang_combo.setMaxVisibleItems(8)
        self.target_lang_combo.currentTextChanged.connect(self.on_target_language_changed)
        target_lang_layout.addWidget(self.target_lang_combo)
        dropdowns_layout.addWidget(self.target_lang_container)

        self.target_lang_container.setVisible(self.config.get("mode") == "Übersetzer")

        dropdowns_layout.addStretch()
        layout.addWidget(dropdowns_container)

        # Nachbearbeitung Card
        refinement_card = MaterialCard(elevation=2)
        refinement_layout = QVBoxLayout(refinement_card)
        refinement_layout.setSpacing(16)

        card_header = QHBoxLayout()
        card_title = QLabel("Nachbearbeitung")
        card_title.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))
        card_title.setObjectName("CardTitle")
        card_header.addWidget(card_title)

        card_header.addStretch()

        # Button zum Hinzufügen neuer Custom Buttons
        add_btn = QPushButton()
        add_btn.setIcon(qta.icon('fa5s.plus', color=COLORS['primary']))
        add_btn.setIconSize(QSize(14, 14))
        add_btn.setFixedSize(32, 32)
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.setToolTip("Neuen Button hinzufügen")
        add_btn.setObjectName("AddButton")
        add_btn.clicked.connect(self.add_custom_button)
        card_header.addWidget(add_btn)

        # Button zum Verwalten der Custom Buttons (Zahnrad)
        manage_btn = QPushButton()
        manage_btn.setIcon(qta.icon('fa5s.cog', color=COLORS['primary']))
        manage_btn.setIconSize(QSize(14, 14))
        manage_btn.setFixedSize(32, 32)
        manage_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        manage_btn.setToolTip("Buttons verwalten")
        manage_btn.setObjectName("AddButton") # Reuse style
        manage_btn.clicked.connect(self.manage_custom_buttons)
        card_header.addWidget(manage_btn)

        refinement_layout.addLayout(card_header)

        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setObjectName("CardDivider")
        divider.setFixedHeight(1)
        refinement_layout.addWidget(divider)

        # Quick Buttons Container
        self.quick_buttons_layout = QHBoxLayout()
        self.quick_buttons_layout.setSpacing(10)

        self.email_btn = self.create_action_button("Als E-Mail formatieren", "fa5s.envelope", "success")
        self.email_btn.clicked.connect(lambda: self.refine_text("email"))
        self.quick_buttons_layout.addWidget(self.email_btn)

        self.compact_btn = self.create_action_button("Text straffen", "fa5s.compress-alt", "outline")
        self.compact_btn.clicked.connect(lambda: self.refine_text("compact"))
        self.quick_buttons_layout.addWidget(self.compact_btn)

        # Platzhalter für Custom Buttons
        self.custom_buttons_container = QWidget()
        self.custom_buttons_inner_layout = QHBoxLayout(self.custom_buttons_container)
        self.custom_buttons_inner_layout.setContentsMargins(0, 0, 0, 0)
        self.custom_buttons_inner_layout.setSpacing(10)
        self.quick_buttons_layout.addWidget(self.custom_buttons_container)

        self.quick_buttons_layout.addStretch()
        refinement_layout.addLayout(self.quick_buttons_layout)

        # Custom Instruction
        instruction_label = QLabel("Individuelle Anweisung:")
        instruction_label.setFont(QFont("Segoe UI", 10, QFont.Weight.Medium))
        instruction_label.setObjectName("InstructionLabel")
        refinement_layout.addWidget(instruction_label)

        instruction_row = QHBoxLayout()
        instruction_row.setSpacing(10)

        self.instruction_input = QLineEdit()
        self.instruction_input.setPlaceholderText('z.B. "In juristische Fachsprache umwandeln"')
        self.instruction_input.setMinimumHeight(38)
        self.instruction_input.setObjectName("InstructionInput")
        instruction_row.addWidget(self.instruction_input)

        apply_custom_btn = QPushButton()
        apply_custom_btn.setIcon(qta.icon('fa5s.check', color='white'))
        apply_custom_btn.setIconSize(QSize(16, 16))
        apply_custom_btn.setFixedSize(42, 42)
        apply_custom_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        apply_custom_btn.setObjectName("MicButton")
        apply_custom_btn.setToolTip("Individuelle Anweisung anwenden")
        apply_custom_btn.clicked.connect(self.apply_custom_instruction)
        instruction_row.addWidget(apply_custom_btn)

        refinement_layout.addLayout(instruction_row)
        layout.addWidget(refinement_card)

        # Transkription Card
        transcript_card = MaterialCard(elevation=2)
        transcript_layout = QVBoxLayout(transcript_card)
        transcript_layout.setSpacing(16)

        transcript_header = QHBoxLayout()
        transcript_title = QLabel("Aktuelle Transkription")
        transcript_title.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))
        transcript_title.setObjectName("CardTitle")
        transcript_header.addWidget(transcript_title)

        transcript_header.addStretch()

        self.repeat_btn = self.create_action_button("Wiederholen", "fa5s.redo", "ghost")
        self.repeat_btn.clicked.connect(self.repeat_last_transcription)
        self.repeat_btn.setEnabled(False)  # Initially disabled until first transcription
        transcript_header.addWidget(self.repeat_btn)

        copy_btn = self.create_action_button("Kopieren", "fa5s.copy", "ghost")
        copy_btn.clicked.connect(self.copy_transcript)
        transcript_header.addWidget(copy_btn)

        transcript_layout.addLayout(transcript_header)

        divider2 = QFrame()
        divider2.setFrameShape(QFrame.Shape.HLine)
        divider2.setObjectName("CardDivider")
        divider2.setFixedHeight(1)
        transcript_layout.addWidget(divider2)

        self.transcript_text = QTextEdit()
        self.transcript_text.setPlaceholderText("Die transkribierte Aufnahme erscheint hier...")
        self.transcript_text.setMinimumHeight(180)
        self.transcript_text.setObjectName("TranscriptText")
        transcript_layout.addWidget(self.transcript_text)

        layout.addWidget(transcript_card)
        layout.addStretch()

        return view

    # ═══════════════════════════════════════════════════════════════
    # CUSTOM BUTTONS
    # ═══════════════════════════════════════════════════════════════

    def load_custom_buttons(self):
        """Lädt Custom Buttons aus Config"""
        # Clear existing buttons in UI
        if hasattr(self, 'custom_buttons_inner_layout'):
            while self.custom_buttons_inner_layout.count():
                item = self.custom_buttons_inner_layout.takeAt(0)
                if item and item.widget():
                    item.widget().deleteLater()
        
        self.custom_buttons = []
        buttons_data = self.config.get("custom_buttons") or []
        for btn_data in buttons_data:
            self.create_custom_button_ui(btn_data)

    def manage_custom_buttons(self):
        """Öffnet den Verwaltungs-Dialog für Custom Buttons"""
        dialog = CustomButtonManagerDialog(self)
        dialog.exec()

    def save_custom_buttons_to_config(self):
        """Speichert Custom Buttons in Config"""
        buttons_data = []
        for btn_info in self.custom_buttons:
            buttons_data.append(btn_info["data"])
        self.config.set("custom_buttons", buttons_data)

    def add_custom_button(self):
        """Öffnet Dialog zum Hinzufügen eines neuen Custom Buttons"""
        dialog = CustomButtonDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            data = dialog.get_data()
            if data["name"] and data["instruction"]:
                self.create_custom_button_ui(data)
                self.save_custom_buttons_to_config()

    def create_custom_button_ui(self, data):
        """Erstellt UI für einen Custom Button"""
        btn = QPushButton(f"  {data['name']}")
        btn.setIcon(qta.icon(data['icon'], color=COLORS['primary']))
        btn.setIconSize(QSize(14, 14))
        btn.setMinimumHeight(36)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFont(QFont("Segoe UI", 11, QFont.Weight.Medium))
        btn.setObjectName("ActionButton")
        btn.setProperty("button_style", "outline")

        # Kontextmenü für Bearbeiten/Löschen
        btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        btn.customContextMenuRequested.connect(lambda pos, b=btn, d=data: self.show_custom_button_menu(b, d, pos))

        # Click-Handler
        btn.clicked.connect(lambda: self.refine_text("custom", data['instruction']))

        self.custom_buttons_inner_layout.addWidget(btn)
        self.custom_buttons.append({"button": btn, "data": data})

    def show_custom_button_menu(self, btn, data, pos):
        """Zeigt Kontextmenü für Custom Button"""
        menu = QMenu(self)

        edit_action = QAction("Bearbeiten", self)
        edit_action.triggered.connect(lambda: self.edit_custom_button(btn, data))
        menu.addAction(edit_action)

        delete_action = QAction("Löschen", self)
        delete_action.triggered.connect(lambda: self.delete_custom_button(btn))
        menu.addAction(delete_action)

        menu.exec(btn.mapToGlobal(pos))

    def edit_custom_button(self, btn, data):
        """Bearbeitet einen Custom Button"""
        dialog = CustomButtonDialog(self, data)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_data = dialog.get_data()
            if new_data["name"] and new_data["instruction"]:
                # Update Button
                btn.setText(f"  {new_data['name']}")
                btn.setIcon(qta.icon(new_data['icon'], color=COLORS['primary']))

                # Update in Liste
                for btn_info in self.custom_buttons:
                    if btn_info["button"] == btn:
                        btn_info["data"] = new_data
                        # Update Click-Handler
                        btn.clicked.disconnect()
                        btn.clicked.connect(lambda: self.refine_text("custom", new_data['instruction']))
                        break

                self.save_custom_buttons_to_config()

    def delete_custom_button(self, btn):
        """Löscht einen Custom Button"""
        reply = QMessageBox.question(
            self, "Button löschen",
            "Möchten Sie diesen Button wirklich löschen?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            # Aus Liste entfernen
            self.custom_buttons = [b for b in self.custom_buttons if b["button"] != btn]
            # UI entfernen
            btn.setParent(None)
            btn.deleteLater()
            # Config speichern
            self.save_custom_buttons_to_config()

    # ═══════════════════════════════════════════════════════════════
    # HISTORY VIEW
    # ═══════════════════════════════════════════════════════════════

    def create_history_view(self):
        """Erstellt die History View"""
        view = QWidget()
        layout = QVBoxLayout(view)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(20)

        header = QHBoxLayout()
        label = QLabel("Verlauf")
        label.setFont(QFont("Segoe UI", 24, QFont.Weight.Bold))
        label.setObjectName("HeaderLabel")
        header.addWidget(label)

        header.addStretch()

        refresh_btn = self.create_action_button("Aktualisieren", "fa5s.sync", "outline")
        refresh_btn.clicked.connect(self.refresh_history)
        header.addWidget(refresh_btn)

        layout.addLayout(header)

        self.history_table = QTableWidget()
        self.history_table.setColumnCount(4)
        self.history_table.setHorizontalHeaderLabels(["Datum/Zeit", "Modus", "Original", "Formatiert"])
        self.history_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.history_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.history_table.setColumnWidth(0, 150)
        self.history_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.history_table.setColumnWidth(1, 120)
        self.history_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.history_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.history_table.setObjectName("HistoryTable")
        self.history_table.doubleClicked.connect(self.load_history_entry)
        layout.addWidget(self.history_table)

        return view

    def refresh_history(self):
        """Lädt Historie neu"""
        entries = self.data.get_last_entries(50)
        self.history_table.setRowCount(len(entries))

        for row, entry in enumerate(entries):
            self.history_table.setItem(row, 0, QTableWidgetItem(entry[1]))
            self.history_table.setItem(row, 1, QTableWidgetItem(entry[2]))
            self.history_table.setItem(row, 2, QTableWidgetItem(entry[3][:100] + "..." if len(entry[3]) > 100 else entry[3]))
            self.history_table.setItem(row, 3, QTableWidgetItem(entry[4][:100] + "..." if len(entry[4]) > 100 else entry[4]))

    def load_history_entry(self, index):
        """Lädt einen Historie-Eintrag in die Home View"""
        entries = self.data.get_last_entries(50)
        if index.row() < len(entries):
            entry = entries[index.row()]
            # Restore state
            mode = entry[2]
            original_text = entry[3]
            formatted_text = entry[4]

            # Set UI
            self.mode_combo.setCurrentText(mode)
            self.target_lang_container.setVisible(mode == "Übersetzer")
            self.transcript_text.setPlainText(formatted_text)
            
            # Note: We don't know the exact language from DB (not stored), 
            # but we restore the text and mode correctly.
            
            self.switch_view("home")

    # ═══════════════════════════════════════════════════════════════
    # SETTINGS VIEW
    # ═══════════════════════════════════════════════════════════════

    def create_settings_view(self):
        """Erstellt die Settings View"""
        view = QWidget()
        layout = QVBoxLayout(view)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(20)

        label = QLabel("Einstellungen")
        label.setFont(QFont("Segoe UI", 24, QFont.Weight.Bold))
        label.setObjectName("HeaderLabel")
        layout.addWidget(label)

        # Container Widget for content with max width
        content_container = QWidget()
        content_container.setMaximumWidth(850)
        content_container.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        content_layout = QVBoxLayout(content_container)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(20)

        # API Key Card
        api_card = MaterialCard(elevation=2)
        api_layout = QVBoxLayout(api_card)
        api_layout.setSpacing(12)

        api_title = QLabel("API-Konfiguration")
        api_title.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        api_layout.addWidget(api_title)

        api_row = QHBoxLayout()
        api_label = QLabel("Groq API Key:")
        api_label.setFont(QFont("Segoe UI", 11))
        api_label.setFixedWidth(140)
        api_row.addWidget(api_label)

        self.api_key_input = QLineEdit()
        self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_input.setText(self.config.get("api_key") or "")
        self.api_key_input.setPlaceholderText("gsk_...")
        self.api_key_input.setMinimumHeight(36)
        self.api_key_input.setMaximumWidth(250)  # Width constraint
        self.api_key_input.setObjectName("SettingsInput")
        api_row.addWidget(self.api_key_input)

        save_api_btn = self.create_action_button("Speichern", "fa5s.save", "primary")
        save_api_btn.clicked.connect(self.save_api_key)
        api_row.addWidget(save_api_btn)
        api_row.addStretch()  # Keep it compact

        api_layout.addLayout(api_row)
        content_layout.addWidget(api_card)

        # Audio Card
        audio_card = MaterialCard(elevation=2)
        audio_layout = QVBoxLayout(audio_card)
        audio_layout.setSpacing(12)

        audio_title = QLabel("Audio-Einstellungen")
        audio_title.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        audio_layout.addWidget(audio_title)

        # Mikrofon
        mic_row = QHBoxLayout()
        mic_label = QLabel("Mikrofon:")
        mic_label.setFixedWidth(140)
        mic_row.addWidget(mic_label)

        self.mic_combo = QComboBox()
        self.mic_combo.setMinimumHeight(36)
        self.mic_combo.setMaximumWidth(400) # Capped but flexible
        self.mic_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.mic_combo.setObjectName("StyledCombo")
        self.mic_combo.currentIndexChanged.connect(self.save_microphone)
        mic_row.addWidget(self.mic_combo)
        
        # Refresh Button
        refresh_mic_btn = QPushButton()
        refresh_mic_btn.setIcon(qta.icon('fa5s.sync', color=self.colors['primary']))
        refresh_mic_btn.setIconSize(QSize(14, 14))
        refresh_mic_btn.setFixedSize(36, 36)
        refresh_mic_btn.setToolTip("Geräteliste aktualisieren")
        refresh_mic_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh_mic_btn.setObjectName("HotkeyButton")  # Reuse style
        refresh_mic_btn.clicked.connect(self.refresh_devices)
        mic_row.addWidget(refresh_mic_btn)
        
        # Test All Button
        test_all_btn = QPushButton("Alle testen")
        test_all_btn.setIcon(qta.icon('fa5s.volume-up', color=self.colors['primary']))
        test_all_btn.setIconSize(QSize(14, 14))
        test_all_btn.setMinimumHeight(36)
        test_all_btn.setToolTip("Alle Mikrofone gleichzeitig testen")
        test_all_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        test_all_btn.setObjectName("HotkeyButton")
        test_all_btn.clicked.connect(self.show_mic_test_dialog)
        mic_row.addWidget(test_all_btn)
        mic_row.addStretch()  # Keep it compact
        
        audio_layout.addLayout(mic_row)
        
        # Initial Device Load with Name Recovery
        self.refresh_devices()

        # Live Pegel Anzeige
        level_row = QHBoxLayout()
        level_label = QLabel("Mikrofon-Pegel:")
        level_label.setFont(QFont("Segoe UI", 11))
        level_label.setFixedWidth(140)
        level_row.addWidget(level_label)

        self.audio_level_bar = QProgressBar()
        self.audio_level_bar.setMinimum(0)
        self.audio_level_bar.setMaximum(100)
        self.audio_level_bar.setValue(0)
        self.audio_level_bar.setTextVisible(False)
        self.audio_level_bar.setMinimumHeight(20)
        self.audio_level_bar.setMaximumWidth(400) # Capped but flexible
        self.audio_level_bar.setObjectName("AudioLevelBar")
        level_row.addWidget(self.audio_level_bar)
        level_row.addStretch()

        audio_layout.addLayout(level_row)

        # Sensitivität
        sens_row = QHBoxLayout()
        sens_label = QLabel("Sensitivität:")
        sens_label.setFont(QFont("Segoe UI", 11))
        sens_label.setFixedWidth(140)
        sens_row.addWidget(sens_label)

        self.sens_slider = QSlider(Qt.Orientation.Horizontal)
        self.sens_slider.setMinimum(1)
        self.sens_slider.setMaximum(100)
        self.sens_slider.setMaximumWidth(400) # Capped but flexible
        current_sens = self.config.get("audio_sensitivity")
        current_sens_val = int((current_sens or 0.005) * 10000)
        self.sens_slider.setValue(current_sens_val)
        self.sens_slider.setObjectName("SettingsSlider")
        self.sens_slider.valueChanged.connect(self.save_sensitivity)
        sens_row.addWidget(self.sens_slider)

        self.sens_value_label = QLabel(f"{self.config.get('audio_sensitivity'):.4f}")
        self.sens_value_label.setFont(QFont("Segoe UI", 10))
        self.sens_value_label.setFixedWidth(60)
        sens_row.addWidget(self.sens_value_label)
        sens_row.addStretch()

        audio_layout.addLayout(sens_row)

        # Sensitivitäts-Hinweis
        sens_hint = QLabel("(Niedrigerer Wert = empfindlicher, höherer Wert = weniger empfindlich)")
        sens_hint.setFont(QFont("Segoe UI", 9))
        sens_hint.setObjectName("HintText")
        audio_layout.addWidget(sens_hint)

        content_layout.addWidget(audio_card)

        # Hotkey Card
        hotkey_card = MaterialCard(elevation=2)
        hotkey_layout = QVBoxLayout(hotkey_card)
        hotkey_layout.setSpacing(12)

        hotkey_title = QLabel("Hotkey-Einstellungen")
        hotkey_title.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        hotkey_layout.addWidget(hotkey_title)

        hotkey_row = QHBoxLayout()
        hotkey_label = QLabel("Aufnahme-Taste:")
        hotkey_label.setFont(QFont("Segoe UI", 11))
        hotkey_label.setFixedWidth(140)
        hotkey_row.addWidget(hotkey_label)

        current_hk = format_hotkey_name(self.config.get("hotkey"))
        self.hotkey_btn = QPushButton(f"Aktuell: {current_hk}")
        self.hotkey_btn.setMinimumHeight(36)
        self.hotkey_btn.setMinimumWidth(150)
        self.hotkey_btn.setMaximumWidth(250)
        self.hotkey_btn.setObjectName("HotkeyButton")
        self.hotkey_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.hotkey_btn.clicked.connect(self.start_hotkey_capture)
        hotkey_row.addWidget(self.hotkey_btn)
        hotkey_row.addStretch()

        hotkey_layout.addLayout(hotkey_row)

        self.hotkey_info_label = QLabel("")
        self.hotkey_info_label.setFont(QFont("Segoe UI", 10))
        self.hotkey_info_label.setObjectName("HotkeyInfoLabel")
        hotkey_layout.addWidget(self.hotkey_info_label)

        content_layout.addWidget(hotkey_card)

        # Custom Instructions Card
        custom_card = MaterialCard(elevation=2)
        custom_layout = QVBoxLayout(custom_card)
        custom_layout.setSpacing(12)

        custom_title = QLabel("Globale Anweisungen")
        custom_title.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        custom_layout.addWidget(custom_title)

        custom_info = QLabel("Diese Anweisungen werden bei jeder Transkription berücksichtigt:")
        custom_info.setFont(QFont("Segoe UI", 10))
        custom_info.setObjectName("SubtitleText")
        custom_layout.addWidget(custom_info)

        self.custom_instructions_input = QTextEdit()
        self.custom_instructions_input.setPlaceholderText('z.B. "Verwende immer die formelle Anrede Sie"')
        self.custom_instructions_input.setMaximumHeight(100)
        self.custom_instructions_input.setPlainText(self.config.get("custom_instructions") or "")
        self.custom_instructions_input.setObjectName("TranscriptText")
        custom_layout.addWidget(self.custom_instructions_input)

        save_custom_btn = self.create_action_button("Speichern", "fa5s.save", "primary")
        save_custom_btn.clicked.connect(self.save_custom_instructions)
        custom_layout.addWidget(save_custom_btn, alignment=Qt.AlignmentFlag.AlignRight)

        content_layout.addWidget(custom_card)

        # Update Card
        update_card = MaterialCard(elevation=2)
        update_layout = QVBoxLayout(update_card)
        update_layout.setSpacing(12)

        update_title = QLabel("Software-Updates")
        update_title.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        update_layout.addWidget(update_title)

        update_row = QHBoxLayout()
        version_label = QLabel(f"Aktuelle Version: {APP_VERSION}")
        version_label.setFont(QFont("Segoe UI", 11))
        update_row.addWidget(version_label)

        self.update_status_label = QLabel("Keine Updates verfügbar")
        self.update_status_label.setFont(QFont("Segoe UI", 11))
        self.update_status_label.setStyleSheet(f"color: {self.colors['text_light']};")
        update_row.addWidget(self.update_status_label)

        update_row.addStretch()

        check_update_btn = self.create_action_button("Jetzt prüfen", "fa5s.sync", "outline")
        check_update_btn.clicked.connect(self.check_for_updates_async)
        update_row.addWidget(check_update_btn)

        self.update_btn = self.create_action_button("Jetzt updaten", "fa5s.download", "success")
        self.update_btn.clicked.connect(self.start_manual_update)
        self.update_btn.setVisible(False)  # Erst sichtbar wenn Update verfügbar
        update_row.addWidget(self.update_btn)

        update_layout.addLayout(update_row)

        content_layout.addWidget(update_card)

        # Add container to main layout (Stretches up to 850px, respects margins)
        layout.addWidget(content_container)
        layout.addStretch()

        return view

    # ═══════════════════════════════════════════════════════════════
    # AUDIO LEVEL MONITOR
    # ═══════════════════════════════════════════════════════════════

    def setup_audio_monitor(self):
        """Richtet den Audio-Pegel Monitor ein"""
        self.audio_monitor_timer = QTimer()
        self.audio_monitor_timer.timeout.connect(self.update_audio_level)
        self.audio_monitor_timer.start(50)  # 20 FPS

        # Device Health Check Timer (für Energiesparmodus-Recovery)
        self.device_health_timer = QTimer()
        self.device_health_timer.timeout.connect(self.check_audio_device_health)
        self.device_health_timer.start(10000)  # Alle 10 Sekunden

    def check_audio_device_health(self):
        """Prueft periodisch ob das Audio-Device noch funktioniert (Energiesparmodus-Recovery)"""
        if not hasattr(self, 'recorder') or self.recorder is None:
            return

        # Nicht pruefen waehrend aktiver Aufnahme
        if self.recorder.is_recording:
            return

        try:
            result = self.recorder.check_device_health()

            if result['recovered']:
                # Device wurde gewechselt - Log und UI-Update
                self._audio_warning_shown = False  # Reset: Mic ist wieder OK
                self.data.log(
                    f"[Audio] Device automatisch wiederhergestellt: {result['message']}",
                    "info"
                )
                if hasattr(self, 'status_label'):
                    self.status_label.setText(f"Mikrofon wiederhergestellt")

            elif result['healthy']:
                # Alles OK - Reset warning flag
                if self._audio_warning_shown:
                    self._audio_warning_shown = False
                    if hasattr(self, 'status_label'):
                        self.status_label.setText("")

            elif not result['healthy']:
                # Problem erkannt aber nicht behoben - NUR EINMAL warnen
                if not self._audio_warning_shown:
                    self._audio_warning_shown = True
                    self.data.log(
                        f"[Audio] Device-Problem: {result['message']}",
                        "warning"
                    )
                    if hasattr(self, 'status_label'):
                        self.status_label.setText("Mikrofon nicht verfuegbar")
                # KEIN QMessageBox! Kein Dialog! Nur Statustext.

        except Exception as e:
            self.data.log(f"[Audio] Health check error: {e}", "error")

    def update_audio_level(self):
        """Aktualisiert die Audio-Pegel Anzeige (Live + Recording)"""
        if hasattr(self, 'audio_level_bar'):
            try:
                rms = getattr(self.recorder, 'current_rms', 0)
                # Normalisiere auf 0-100 (logarithmische Skala-Gefühl)
                level = min(100, int(rms * 5000))
                self.audio_level_bar.setValue(level)
            except:
                pass

    # ═══════════════════════════════════════════════════════════════
    # HELP VIEW
    # ═══════════════════════════════════════════════════════════════

    def create_help_view(self):
        """Erstellt die Help View - einfach und visuell für Anwälte"""
        view = QWidget()
        layout = QVBoxLayout(view)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(24)

        label = QLabel("So funktioniert's")
        label.setFont(QFont("Segoe UI", 24, QFont.Weight.Bold))
        label.setObjectName("HeaderLabel")
        layout.addWidget(label)

        # ══════════════════════════════════════════════════════════
        # HAUPTANLEITUNG - Clean wie Modi-Karten
        # ══════════════════════════════════════════════════════════
        hotkey_name = format_hotkey_name(self.config.get("hotkey"))

        main_card = QFrame()
        main_card.setStyleSheet(f"""
            QFrame#mainCard {{
                background: {self.colors['bg_card']};
                border-radius: 12px;
            }}
        """)
        main_card.setObjectName("mainCard")
        main_layout = QVBoxLayout(main_card)
        main_layout.setContentsMargins(24, 20, 24, 16)
        main_layout.setSpacing(12)

        # Step 1
        step1_container = QFrame()
        step1_container.setStyleSheet(f"""
            QFrame {{
                background: {self.colors['bg_elevated']};
                border-radius: 8px;
            }}
        """)
        step1 = QHBoxLayout(step1_container)
        step1.setContentsMargins(14, 10, 14, 10)
        step1_num = QLabel("1.")
        step1_num.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        step1_num.setStyleSheet(f"color: {self.colors['primary']};")
        step1_num.setFixedWidth(24)
        step1.addWidget(step1_num)
        step1_text = QLabel("Ins Textfeld klicken")
        step1_text.setFont(QFont("Segoe UI", 13))
        step1.addWidget(step1_text)
        step1_hint = QLabel("Cursor muss blinken")
        step1_hint.setFont(QFont("Segoe UI", 11))
        step1_hint.setStyleSheet(f"color: {self.colors['text_light']};")
        step1.addWidget(step1_hint)
        step1.addStretch()
        main_layout.addWidget(step1_container)

        # Step 2
        step2_container = QFrame()
        step2_container.setStyleSheet(f"""
            QFrame {{
                background: {self.colors['bg_elevated']};
                border-radius: 8px;
            }}
        """)
        step2 = QHBoxLayout(step2_container)
        step2.setContentsMargins(14, 10, 14, 10)
        step2_num = QLabel("2.")
        step2_num.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        step2_num.setStyleSheet(f"color: {self.colors['primary']};")
        step2_num.setFixedWidth(24)
        step2.addWidget(step2_num)

        self._hotkey_badge_large = QLabel(hotkey_name)
        self._hotkey_badge_large.setFont(QFont("Consolas", 11, QFont.Weight.Bold))
        self._hotkey_badge_large.setStyleSheet(f"""
            background: {self.colors['bg_input']};
            color: {self.colors['text_dark']};
            padding: 5px 12px;
            border-radius: 5px;
            border: 1px solid {self.colors['border']};
            border-bottom: 2px solid {self.colors['border']};
        """)
        step2.addWidget(self._hotkey_badge_large)

        step2_text = QLabel("halten + sprechen")
        step2_text.setFont(QFont("Segoe UI", 13))
        step2.addWidget(step2_text)
        step2.addStretch()
        main_layout.addWidget(step2_container)

        # Step 3
        step3_container = QFrame()
        step3_container.setStyleSheet(f"""
            QFrame {{
                background: {self.colors['bg_elevated']};
                border-radius: 8px;
            }}
        """)
        step3 = QHBoxLayout(step3_container)
        step3.setContentsMargins(14, 10, 14, 10)
        step3_num = QLabel("3.")
        step3_num.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        step3_num.setStyleSheet(f"color: {self.colors['primary']};")
        step3_num.setFixedWidth(24)
        step3.addWidget(step3_num)
        step3_text = QLabel("Loslassen")
        step3_text.setFont(QFont("Segoe UI", 13))
        step3.addWidget(step3_text)
        step3_result = QLabel("→ Text erscheint (2-3 Sek.)")
        step3_result.setFont(QFont("Segoe UI", 11))
        step3_result.setStyleSheet(f"color: {self.colors['text_light']};")
        step3.addWidget(step3_result)
        step3.addStretch()
        main_layout.addWidget(step3_container)

        # Hint
        hint = QHBoxLayout()
        hint_icon = QLabel()
        hint_icon.setPixmap(qta.icon('fa5s.info-circle', color=self.colors['text_light']).pixmap(14, 14))
        hint.addWidget(hint_icon)
        hint_text = QLabel("Falls Text nicht erscheint: Strg+V (Zwischenablage)")
        hint_text.setFont(QFont("Segoe UI", 10))
        hint_text.setStyleSheet(f"color: {self.colors['text_light']};")
        hint.addWidget(hint_text)
        hint.addStretch()
        main_layout.addLayout(hint)

        layout.addWidget(main_card)

        # ══════════════════════════════════════════════════════════
        # DIE DREI MODI - Bunte Karten nebeneinander
        # ══════════════════════════════════════════════════════════
        modi_title = QLabel("Wählen Sie Ihren Modus")
        modi_title.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        layout.addWidget(modi_title)

        modi_row = QHBoxLayout()
        modi_row.setSpacing(16)

        modes = [
            {
                "name": "Diktat",
                "mode_value": "Diktat",
                "color": "#F59E0B",  # Amber/Orange
                "icon": "fa5s.bolt",
                "speed": "Am schnellsten",
                "desc": "Sprache zu Text.\nKeine Nachbearbeitung.",
                "best_for": "Schnelle Notizen",
            },
            {
                "name": "Dynamisch",
                "mode_value": "Dynamisches Diktat",
                "color": self.colors['primary'],
                "icon": "fa5s.magic",
                "speed": "Normal",
                "desc": "KI formatiert den Text.\nSatzbau, Grammatik, Struktur.",
                "best_for": "Professionelle Texte",
            },
            {
                "name": "Übersetzer",
                "mode_value": "Übersetzer",
                "color": "#10B981",  # Green
                "icon": "fa5s.language",
                "speed": "Normal",
                "desc": "Deutsch sprechen,\nEnglisch schreiben.",
                "best_for": "International",
            },
        ]

        for mode in modes:
            card = QFrame()
            card.setCursor(Qt.CursorShape.PointingHandCursor)
            card.setStyleSheet(f"""
                QFrame {{
                    background: {self.colors['bg_card']};
                    border: 2px solid {mode['color']};
                    border-radius: 12px;
                    padding: 16px;
                }}
                QFrame:hover {{
                    background: {self.colors['bg_sidebar']};
                }}
            """)
            # Make clickable
            card.mousePressEvent = lambda event, m=mode['mode_value']: self._select_mode_and_go_home(m)
            card.setMinimumWidth(200)
            card_layout = QVBoxLayout(card)
            card_layout.setSpacing(10)

            # Icon + Name
            header = QHBoxLayout()
            icon = QLabel()
            icon.setPixmap(qta.icon(mode['icon'], color=mode['color']).pixmap(24, 24))
            header.addWidget(icon)
            name = QLabel(mode['name'])
            name.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
            header.addWidget(name)
            header.addStretch()
            card_layout.addLayout(header)

            # Speed Badge
            speed_badge = QLabel(mode['speed'])
            speed_badge.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            speed_badge.setStyleSheet(f"""
                background: {mode['color']};
                color: white;
                padding: 4px 8px;
                border-radius: 4px;
            """)
            speed_badge.setFixedWidth(110)
            speed_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            card_layout.addWidget(speed_badge)

            # Description
            desc = QLabel(mode['desc'])
            desc.setFont(QFont("Segoe UI", 10))
            desc.setStyleSheet(f"color: {self.colors['text_light']};")
            card_layout.addWidget(desc)

            # Best for
            best = QLabel(f"Ideal für: {mode['best_for']}")
            best.setFont(QFont("Segoe UI", 9))
            best.setStyleSheet(f"color: {mode['color']}; font-weight: bold;")
            card_layout.addWidget(best)

            card_layout.addStretch()
            modi_row.addWidget(card)

        layout.addLayout(modi_row)

        # ══════════════════════════════════════════════════════════
        # PROFI-TIPPS - Einfache Liste
        # ══════════════════════════════════════════════════════════
        tips_card = MaterialCard(elevation=1)
        tips_layout = QVBoxLayout(tips_card)
        tips_layout.setSpacing(10)

        tips_title = QLabel("Profi-Tipps")
        tips_title.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        tips_layout.addWidget(tips_title)

        tips = [
            ("Automatisch", "Text wird direkt eingefügt UND in die Zwischenablage kopiert (Strg+V)"),
            ("Stichpunkte", "Sagen Sie \"Stichpunkte\" am Anfang für eine Aufzählung"),
            ("Paragraphen", "\"Paragraf vier drei drei BGB\" wird zu § 433 BGB"),
            ("Wiederholen", "Der Wiederholen-Button verarbeitet die letzte Aufnahme nochmal"),
        ]

        for title, desc in tips:
            tip_row = QHBoxLayout()
            title_label = QLabel(f"{title}:")
            title_label.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
            title_label.setFixedWidth(100)
            tip_row.addWidget(title_label)

            desc_label = QLabel(desc)
            desc_label.setFont(QFont("Segoe UI", 10))
            desc_label.setStyleSheet(f"color: {self.colors['text_light']};")
            tip_row.addWidget(desc_label)
            tip_row.addStretch()

            tips_layout.addLayout(tip_row)

        layout.addWidget(tips_card)

        # ══════════════════════════════════════════════════════════
        # DEBUG-LOG - Versteckt/Kompakt
        # ══════════════════════════════════════════════════════════
        log_card = MaterialCard(elevation=1)
        log_layout = QVBoxLayout(log_card)
        log_layout.setSpacing(8)

        log_header = QHBoxLayout()
        log_title = QLabel("Technisches Log")
        log_title.setFont(QFont("Segoe UI", 11))
        log_title.setStyleSheet(f"color: {self.colors['text_light']};")
        log_header.addWidget(log_title)
        log_header.addStretch()

        refresh_log_btn = self.create_action_button("Aktualisieren", "fa5s.sync", "ghost")
        refresh_log_btn.clicked.connect(self.refresh_log)
        log_header.addWidget(refresh_log_btn)
        log_layout.addLayout(log_header)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(100)
        self.log_text.setObjectName("TranscriptText")
        self.log_text.setFont(QFont("Consolas", 8))
        log_layout.addWidget(self.log_text)

        layout.addWidget(log_card)
        layout.addStretch()

        self.refresh_log()

        return view

    def refresh_log(self):
        """Lädt Log-Inhalt"""
        log_content = self.data.get_log_content(50)
        self.log_text.setPlainText(log_content)

    # ═══════════════════════════════════════════════════════════════
    # HELPER METHODS
    # ═══════════════════════════════════════════════════════════════

    def create_action_button(self, text, icon_name, style):
        """Erstellt einen Action Button"""
        btn = QPushButton(f"  {text}")
        btn.setProperty("button_style", style)

        if style in ["primary", "success"]:
            icon_color = 'white'
        else:
            icon_color = self.colors['primary']

        btn.setIcon(qta.icon(icon_name, color=icon_color))
        btn.setIconSize(QSize(14, 14))
        btn.setMinimumHeight(36)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFont(QFont("Segoe UI", 11, QFont.Weight.Medium))
        btn.setObjectName("ActionButton")
        return btn

    def update_nav_icons(self):
        """Aktualisiert Navigation Icons"""
        for view_id, btn in self.nav_buttons.items():
            icon_name = btn.property("icon_name")
            is_active = btn.property("nav_active")

            if is_active:
                btn.setIcon(qta.icon(icon_name, color='#FFFFFF'))
            else:
                btn.setIcon(qta.icon(icon_name, color=self.colors['text_light']))

    # ═══════════════════════════════════════════════════════════════
    # EVENT HANDLERS
    # ═══════════════════════════════════════════════════════════════

    def on_mode_changed(self, mode):
        """Handler für Modus-Wechsel"""
        self.config.set("mode", mode)
        self.target_lang_container.setVisible(mode == "Übersetzer")

    def on_language_changed(self, language):
        """Handler für Sprach-Wechsel"""
        if language != "───────────":
            self.config.set("language", language)

    def on_target_language_changed(self, language):
        """Handler für Zielsprach-Wechsel"""
        self.config.set("target_language", language)

    def copy_transcript(self):
        """Kopiert Transkription in Clipboard"""
        text = self.transcript_text.toPlainText()
        if text:
            _get_pyperclip().copy(text)

    def repeat_last_transcription(self):
        """Re-runs full transcription + LLM processing on last audio"""
        last_audio = self.recorder.get_last_recording()
        if not last_audio:
            self.data.log("No last recording available", "warning")
            return

        self.repeat_btn.setEnabled(False)
        self.overlay.set_status("processing")

        # Create a copy of the audio file so it doesn't get deleted
        import shutil
        temp_copy = last_audio.replace("last_recording", "repeat_temp")
        try:
            shutil.copy2(last_audio, temp_copy)
        except Exception as e:
            self.data.log(f"Could not copy audio: {e}", "error")
            self.repeat_btn.setEnabled(True)
            return

        # Reuse the existing TranscriptionWorker
        worker = TranscriptionWorker(self.api, self.config, self.data, temp_copy)
        worker.finished.connect(self._on_repeat_finished)
        worker.error.connect(self._on_repeat_error)
        worker.start()
        self._repeat_worker = worker

    def _on_repeat_finished(self, text, raw_transcript=None):
        """Handler for repeat transcription completion"""
        self.transcript_text.setPlainText(text)
        if raw_transcript:
            self._last_raw_transcript = raw_transcript
        self.overlay.set_status("success")
        self.repeat_btn.setEnabled(True)

    def _on_repeat_error(self, error):
        """Handler for repeat transcription error"""
        self.data.log(f"Repeat error: {error}", "error")
        self.overlay.set_status("error")
        self.repeat_btn.setEnabled(True)

    def refine_text(self, style, custom_instruction=None):
        """Startet Nachbearbeitung"""
        text = self.transcript_text.toPlainText()
        if not text:
            return

        self.email_btn.setEnabled(False)
        self.compact_btn.setEnabled(False)

        worker = RefinementWorker(self.api, text, style, custom_instruction)
        worker.finished.connect(self.on_refinement_finished)
        worker.error.connect(self.on_refinement_error)
        worker.start()

        self.current_refinement_worker = worker

    def apply_custom_instruction(self):
        """Wendet individuelle Anweisung an"""
        text = self.transcript_text.toPlainText()
        instruction = self.instruction_input.text()
        if not text or not instruction:
            return

        self.refine_text("custom", instruction)

    def on_refinement_finished(self, text):
        """Handler für fertige Nachbearbeitung"""
        self.transcript_text.setPlainText(text)
        self.email_btn.setEnabled(True)
        self.compact_btn.setEnabled(True)
        _get_pyperclip().copy(text)

    def on_refinement_error(self, error):
        """Handler für Nachbearbeitung-Fehler"""
        self.email_btn.setEnabled(True)
        self.compact_btn.setEnabled(True)
        QMessageBox.warning(self, "Fehler", f"Nachbearbeitung fehlgeschlagen: {error}")

    def save_api_key(self):
        """Speichert API Key"""
        key = self.api_key_input.text().strip()
        self.config.set("api_key", key)
        QMessageBox.information(self, "Gespeichert", "API Key wurde gespeichert.")

    def save_microphone(self, index):
        """Speichert Mikrofon-Auswahl (ID + Name)"""
        if index < 0: return
        
        device_id = self.mic_combo.itemData(index)
        device_name = self.mic_combo.itemText(index)
        
        self.config.set("device_index", device_id)
        self.config.set("device_name", device_name)
        
        # Monitor neu starten mit neuem Gerät falls aktiv
        if self.settings_view.isVisible():
            self.recorder.stop_monitor()
            self.recorder.start_monitor(device_index=device_id, device_name=self.config.get("device_name"))

    def refresh_devices(self):
        """Lädt Geräteliste neu im Hintergrund (blockiert UI nicht)"""
        # Show loading state
        self.mic_combo.blockSignals(True)
        self.mic_combo.clear()
        self.mic_combo.addItem("Lade Geräte...", None)
        self.mic_combo.setEnabled(False)
        self.mic_combo.blockSignals(False)

        # Start background worker
        self._device_worker = DeviceLoadWorker(self.recorder)
        self._device_worker.finished.connect(self._on_devices_loaded)
        self._device_worker.start()

    def _on_devices_loaded(self, devices):
        """Callback wenn Geräte geladen wurden"""
        self.mic_combo.blockSignals(True)
        self.mic_combo.clear()
        self.mic_combo.setEnabled(True)

        # Gespeicherte Werte
        saved_id = self.config.get("device_index")
        saved_name = self.config.get("device_name")

        target_index = -1

        for dev in devices:
            self.mic_combo.addItem(dev["name"], dev["id"])

            # Match Logic:
            # 1. Exact Name Match (Best for Docking Station)
            if saved_name and dev["name"] == saved_name:
                target_index = self.mic_combo.count() - 1
            # 2. ID Match (Fallback if name changed but ID kept)
            elif target_index == -1 and saved_id is not None and dev["id"] == saved_id:
                target_index = self.mic_combo.count() - 1

        # Set Selection
        if target_index >= 0:
            self.mic_combo.setCurrentIndex(target_index)
            # Update ID if it changed (drift fix)
            new_id = self.mic_combo.itemData(target_index)
            if new_id != saved_id:
                print(f"[Device] ID Changed for Same Device ({saved_id} -> {new_id}). Updating Config.")
                self.config.set("device_index", new_id)

        self.mic_combo.blockSignals(False)

    def show_mic_test_dialog(self):
        """Öffnet den Dialog zum Testen aller Mikrofone"""
        dialog = MicrophoneTestDialog(self, main_recorder=self.recorder)
        dialog.exec()


    def save_sensitivity(self, value):
        """Speichert Audio-Sensitivität"""
        sens = value / 10000.0
        self.sens_value_label.setText(f"{sens:.4f}")
        self.config.set("audio_sensitivity", sens)
        self.recorder.audio_sensitivity = sens

    def save_custom_instructions(self):
        """Speichert globale Anweisungen"""
        instructions = self.custom_instructions_input.toPlainText()
        self.config.set("custom_instructions", instructions)
        QMessageBox.information(self, "Gespeichert", "Globale Anweisungen wurden gespeichert.")

    def start_hotkey_capture(self):
        """Startet Hotkey-Erfassung"""
        with self.hotkey_lock:
            self.is_setting_hotkey = True
        self.hotkey_btn.setText("Drücke eine Taste...")
        self.hotkey_info_label.setText("Warte auf Tastendruck...")
        self.hotkey_info_label.setStyleSheet(f"color: {self.colors['primary']};")

    # ═══════════════════════════════════════════════════════════════
    # HOTKEY LISTENER
    # ═══════════════════════════════════════════════════════════════

    def setup_hotkey_listener(self):
        """Richtet den globalen Hotkey-Listener ein"""
        try:
            keyboard = _get_pynput()
            print("[Hotkey] Starting listener...")

            def get_key_name(key):
                try:
                    if hasattr(key, 'char') and key.char:
                        return key.char.lower()
                    elif hasattr(key, 'name'):
                        return key.name.lower()
                except:
                    pass
                return str(key).replace("Key.", "").lower()

            def on_press(key):
                key_name = get_key_name(key)
                # print(f"[Hotkey] Key pressed: {key_name}") # Disabled for privacy

                with self.hotkey_lock:
                    if self.is_setting_hotkey:
                        self.config.set("hotkey", key_name)
                        self.is_setting_hotkey = False
                        # Use signal for thread-safe UI update
                        self.hotkey_set_signal.emit(key_name)
                        print(f"[Hotkey] New hotkey set: {key_name}")
                        return

                target_key = self.config.get("hotkey")
                if key_name == target_key and not self.recorder.is_recording:
                    print(f"[Hotkey] Recording started with key: {key_name}")
                    self.overlay_status_signal.emit("recording")

                    # Auto-Recovery: Prüfe ob Mikrofon noch verfügbar (Docking Station Szenario)
                    dev_idx = self.config.get("device_index")
                    dev_name = self.config.get("device_name")
                    recovered_idx, needs_restart = self.recorder.ensure_device_available(dev_idx, dev_name)

                    if recovered_idx != dev_idx and recovered_idx is not None:
                        # Gerät hat neue ID bekommen - Config aktualisieren
                        print(f"[Hotkey] Device ID changed: {dev_idx} -> {recovered_idx}")
                        self.config.set("device_index", recovered_idx)
                        dev_idx = recovered_idx

                    if needs_restart and self.recorder._unified_stream:
                        # Stream neu starten mit korrektem Geraet
                        self.recorder.stop_monitor()
                        new_dev = self.recorder._start_unified_stream(dev_idx, dev_name)
                        if new_dev is None:
                            # Kein Geraet verfuegbar - Statustext, kein Crash
                            print("[Hotkey] No audio device available after switch")
                            self.overlay_status_signal.emit("error")
                            return

                    self.recorder.start_recording(device_index=dev_idx)

            def on_release(key):
                key_name = get_key_name(key)
                target_key = self.config.get("hotkey")

                with self.hotkey_lock:
                    if self.is_setting_hotkey:
                        return

                if key_name == target_key and self.recorder.is_recording:
                    print(f"[Hotkey] Recording stopped with key: {key_name}")
                    file_path = self.recorder.stop_recording()

                    if file_path == NO_AUDIO_DETECTED:
                        self.overlay_status_signal.emit("error")
                        # Use signal for thread-safe warning (with cooldown in handler)
                        self.no_audio_warning_signal.emit()
                    elif file_path:
                        # Validation: Check file size (at least 8KB for valid wav + audio data)
                        file_size = os.path.getsize(file_path) if os.path.exists(file_path) else 0
                        print(f"[Hotkey] File path: {file_path}, size: {file_size}")
                        if file_size > 8000:
                            self.overlay_status_signal.emit("processing")
                            # Use signal instead of QTimer for thread-safety
                            self.transcription_signal.emit(file_path)
                        else:
                            print(f"[Audio] Warning: Recording file too small or missing ({file_path})")
                            self.overlay_status_signal.emit("error")
                            self.no_audio_warning_signal.emit()
                    else:
                        print("[Hotkey] No file returned from stop_recording")
                        self.overlay_status_signal.emit("aborted")

            self.listener = keyboard.Listener(on_press=on_press, on_release=on_release)
            self.listener.start()
            print("[Hotkey] Listener started successfully")
        except Exception as e:
            print(f"[Hotkey] Error setting up listener: {e}")

    def _on_hotkey_set(self, key_name):
        """Signal handler for hotkey being set - runs in main thread"""
        display_name = format_hotkey_name(key_name)
        self.hotkey_btn.setText(f"Aktuell: {display_name}")
        self.hotkey_info_label.setText("Gespeichert!")
        self.hotkey_info_label.setStyleSheet(f"color: {self.colors['success']};")
        self.hotkey_badge.setText(display_name)
        # Update support page hotkey display (large keyboard badge)
        if hasattr(self, '_hotkey_badge_large') and self._hotkey_badge_large:
            self._hotkey_badge_large.setText(display_name)

    def _on_overlay_status(self, status):
        """Signal handler for overlay status - runs in main thread"""
        self.overlay.set_status(status)

    def _on_start_transcription(self, file_path):
        """Signal handler for starting transcription - runs in main thread"""
        print(f"[Signal] _on_start_transcription received: {file_path}")
        self.start_transcription(file_path)

    def show_no_audio_warning(self):
        """Zeigt Warnung bei fehlendem Audio mit huebschem Dialog (max 1x pro 30s)"""
        # Cooldown: Maximal 1 Dialog pro 30 Sekunden
        now = time.time()
        if now - self._last_no_audio_warning_time < 30:
            print("[Audio] No-audio warning suppressed (cooldown)")
            return
        self._last_no_audio_warning_time = now

        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setWindowTitle("Kein Audio erkannt")
        msg.setText(
            f"<h3 style='color: {self.colors['accent']};'><b>Keine Audiosignale erkannt</b></h3>"
            "<p>Die Aufnahme enthielt keinen erkennbaren Ton.</p>"
        )
        msg.setInformativeText(
            "<b>Moegliche Ursachen:</b><br>"
            "- Falsches Mikrofon in den Einstellungen ausgewaehlt<br>"
            "- Mikrofon ist stummgeschaltet oder defekt<br>"
            "- Audio-Sensitivitaet zu niedrig eingestellt<br><br>"
            "<b>Tipp:</b> Oeffne die Einstellungen und pruefe, ob der Pegel-Balken "
            "sich bewegt, wenn du sprichst."
        )
        msg.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg.setDefaultButton(QMessageBox.StandardButton.Ok)
        msg.exec()

    def start_transcription(self, audio_file):
        """Startet Transkription im Worker Thread"""
        worker = TranscriptionWorker(self.api, self.config, self.data, audio_file)
        worker.finished.connect(self.on_transcription_finished)
        worker.error.connect(self.on_transcription_error)
        worker.start()

        self.current_worker = worker

    def on_transcription_finished(self, text, raw_transcript=None):
        """Handler für fertige Transkription"""
        self.transcript_text.setPlainText(text)
        if raw_transcript:
            self._last_raw_transcript = raw_transcript
        # Enable repeat button if last recording exists
        if self.recorder.get_last_recording():
            self.repeat_btn.setEnabled(True)
        self.overlay.set_status("success")
        # Update-Check im Hintergrund nach erfolgreicher Transkription
        QTimer.singleShot(2000, self.check_for_updates_async)

    def on_transcription_error(self, error):
        """Handler für Transkription-Fehler"""
        self.overlay.set_status("error")

    # ═══════════════════════════════════════════════════════════════
    # SYSTEM TRAY
    # ═══════════════════════════════════════════════════════════════

    def setup_system_tray(self):
        """Richtet System Tray Icon ein"""
        self.tray_icon = QSystemTrayIcon(self)

        icon_path = get_icon_path()
        if os.path.exists(icon_path):
            self.tray_icon.setIcon(QIcon(icon_path))
        else:
            self.tray_icon.setIcon(qta.icon('fa5s.microphone', color='#374151'))

        tray_menu = QMenu()

        show_action = QAction("Anzeigen", self)
        show_action.triggered.connect(self.show_window)
        tray_menu.addAction(show_action)

        tray_menu.addSeparator()

        quit_action = QAction("Beenden", self)
        quit_action.triggered.connect(self.quit_app)
        tray_menu.addAction(quit_action)

        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self.on_tray_activated)
        self.tray_icon.show()

    def on_tray_activated(self, reason):
        """Handler für Tray-Klick"""
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show_window()

    def show_window(self):
        """Zeigt Hauptfenster"""
        self.showNormal()
        self.activateWindow()
        self.raise_()

    def hide_window(self):
        """Versteckt Hauptfenster"""
        self.hide()

    def closeEvent(self, event):
        """Override Close Event - in Tray minimieren"""
        event.ignore()
        self.hide_window()

    def quit_app(self):
        """Beendet die App komplett"""
        try:
            if hasattr(self, 'audio_monitor_timer'):
                self.audio_monitor_timer.stop()
            if hasattr(self, 'device_health_timer'):
                self.device_health_timer.stop()
            if hasattr(self, 'listener') and self.listener:
                self.listener.stop()
            if hasattr(self, 'tray_icon') and self.tray_icon:
                self.tray_icon.hide()
            # Worker-Thread sauber beenden
            if hasattr(self, 'current_worker') and self.current_worker and self.current_worker.isRunning():
                print("[App] Waiting for worker thread to finish...")
                self.current_worker.quit()
                self.current_worker.wait(3000)  # Max 3 Sekunden warten
            if hasattr(self, 'recorder') and self.recorder:
                self.recorder.close()
            if hasattr(self, 'data') and self.data:
                self.data.close()
            if hasattr(self, 'overlay') and self.overlay:
                self.overlay.close()
        except:
            pass
        finally:
            QApplication.quit()
            os._exit(0)

    def load_last_text(self):
        """Lädt letzten Eintrag aus der Historie"""
        entries = self.data.get_last_entries(1)
        if entries:
            self.transcript_text.setPlainText(entries[0][4])

    # ═══════════════════════════════════════════════════════════════
    # STYLING
    # ═══════════════════════════════════════════════════════════════

    def apply_color_scheme(self):
        """Wendet Color Scheme an"""
        c = self.colors

        stylesheet = f"""
            QMainWindow {{
                background-color: {c['bg_main']};
            }}

            #Sidebar {{
                background-color: {c['bg_sidebar']};
            }}

            #Divider {{
                background-color: {c['border']};
            }}

            #LogoLabel {{
                color: {c['primary']};
            }}
            #SubtitleLabel {{
                color: {c['text_light']};
                letter-spacing: 1px;
                text-transform: uppercase;
            }}

            #NavButton {{
                background-color: transparent;
                color: {c['text_light']};
                border: none;
                border-radius: 10px;
                padding: 12px 16px;
                text-align: left;
                font-weight: 500;
            }}
            #NavButton[nav_active="true"] {{
                background-color: {c['primary']};
                color: white;
                font-weight: 600;
            }}
            #NavButton[nav_active="false"]:hover {{
                background-color: {c['active_bg']};
                color: {c['primary']};
            }}

            #VersionLabel {{
                color: {c['text_light']};
            }}

            #HeaderLabel {{
                color: {c['text_dark']};
            }}
            #SubtitleText {{
                color: {c['text_light']};
            }}
            #HotkeyBadge {{
                background-color: {c['primary']};
                color: white;
                padding: 4px 12px;
                border-radius: 5px;
            }}
            #HintText {{
                color: {c['text_light']};
                font-style: italic;
            }}

            #DropdownLabel {{
                color: {c['text_dark']};
            }}

            #StyledCombo {{
                border: 1px solid {c['border']};
                border-radius: 8px;
                padding: 10px 14px;
                padding-right: 36px;
                background-color: {c['bg_input']};
                color: {c['text_dark']};
            }}
            #StyledCombo:hover {{
                border-color: {c['primary']};
                background-color: {c['active_bg']};
            }}
            #StyledCombo::drop-down {{
                subcontrol-origin: padding;
                subcontrol-position: center right;
                width: 30px;
                border: none;
                background: transparent;
            }}
            #StyledCombo::down-arrow {{
                image: none;
                width: 0;
                height: 0;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 6px solid {c['text_light']};
            }}
            #StyledCombo:hover::down-arrow {{
                border-top-color: {c['primary']};
            }}

            #CardTitle {{
                color: {c['text_dark']};
            }}
            #CardDivider {{
                background-color: {c['border']};
            }}

            #InstructionLabel {{
                color: {c['text_dark']};
            }}
            #InstructionInput, #SettingsInput {{
                border: 1px solid {c['border']};
                border-radius: 8px;
                padding: 10px 12px;
                background-color: {c['bg_input']};
                color: {c['text_dark']};
            }}
            #InstructionInput:focus, #SettingsInput:focus {{
                border-color: {c['primary']};
                border-width: 2px;
            }}

            #MicButton {{
                background-color: {c['primary']};
                border: none;
                border-radius: 21px;
            }}
            #MicButton:hover {{
                background-color: {c['accent']};
            }}

            #AddButton {{
                background-color: transparent;
                border: 1px solid {c['border']};
                border-radius: 16px;
            }}
            #AddButton:hover {{
                background-color: {c['active_bg']};
                border-color: {c['primary']};
            }}

            #ActionButton[button_style="primary"] {{
                background-color: {c['primary']};
                color: white;
                border: none;
                border-radius: 8px;
                padding: 10px 20px;
            }}
            #ActionButton[button_style="primary"]:hover {{
                background-color: {c['accent']};
            }}

            #ActionButton[button_style="success"] {{
                background-color: {c['success']};
                color: white;
                border: none;
                border-radius: 8px;
                padding: 10px 20px;
            }}

            #ActionButton[button_style="outline"] {{
                background-color: transparent;
                color: {c['primary']};
                border: 2px solid {c['primary']};
                border-radius: 8px;
                padding: 9px 19px;
            }}
            #ActionButton[button_style="outline"]:hover {{
                background-color: {c['active_bg']};
            }}

            #ActionButton[button_style="ghost"] {{
                background-color: transparent;
                color: {c['primary']};
                border: none;
                border-radius: 8px;
                padding: 10px 20px;
            }}
            #ActionButton[button_style="ghost"]:hover {{
                background-color: {c['active_bg']};
            }}

            #TranscriptText {{
                border: 1px solid {c['border']};
                border-radius: 8px;
                padding: 12px;
                background-color: {c['bg_elevated']};
                color: {c['text_dark']};
                line-height: 1.5;
            }}

            #HotkeyButton {{
                background-color: {c['bg_input']};
                color: {c['text_dark']};
                border: 1px solid {c['border']};
                border-radius: 8px;
                padding: 10px 20px;
            }}
            #HotkeyButton:hover {{
                border-color: {c['primary']};
                background-color: {c['active_bg']};
            }}

            #HotkeyInfoLabel {{
                color: {c['text_light']};
            }}

            #HistoryTable {{
                border: 1px solid {c['border']};
                border-radius: 8px;
                background-color: {c['bg_input']};
            }}
            #HistoryTable::item {{
                padding: 8px;
            }}
            #HistoryTable::item:selected {{
                background-color: {c['active_bg']};
                color: {c['text_dark']};
            }}

            QSlider::groove:horizontal {{
                border: 1px solid {c['border']};
                height: 8px;
                background: {c['active_bg']};
                border-radius: 4px;
            }}
            QSlider::handle:horizontal {{
                background: {c['primary']};
                border: none;
                width: 18px;
                margin: -5px 0;
                border-radius: 9px;
            }}
            QSlider::handle:horizontal:hover {{
                background: {c['accent']};
            }}

            #AudioLevelBar {{
                border: 1px solid {c['border']};
                border-radius: 4px;
                background-color: {c['active_bg']};
            }}
            #AudioLevelBar::chunk {{
                background-color: {c['success']};
                border-radius: 3px;
            }}
        """

        self.setStyleSheet(stylesheet)


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    # Single Instance Lock
    LOCK_FILE = os.path.join(APP_DATA_DIR, ".lock")
    if os.path.exists(LOCK_FILE):
        try:
            # Check if process is still running
            with open(LOCK_FILE, "r") as f:
                old_pid = int(f.read().strip())
                import psutil
                if psutil.pid_exists(old_pid):
                    print(f"[System] App already running (PID {old_pid}). Exiting.")
                    sys.exit(0)
        except:
             pass # Old lock or psutil not found, proceed and overwrite

    with open(LOCK_FILE, "w") as f:
        f.write(str(os.getpid()))

    app = QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 11))
    app.setQuitOnLastWindowClosed(False)

    window = ACTScriber()
    window.show()

    exit_code = app.exec()
    
    # Cleanup Lock
    if os.path.exists(LOCK_FILE):
        os.remove(LOCK_FILE)
        
    sys.exit(exit_code)
