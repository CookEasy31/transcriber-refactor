import json
import os
from dotenv import load_dotenv

# .env Datei laden (falls vorhanden)
load_dotenv()

APP_NAME = "act Scriber"
APP_VERSION = "2.2.0"
APP_DATA_DIR = os.path.join(os.getenv("LOCALAPPDATA"), APP_NAME)
if not os.path.exists(APP_DATA_DIR):
    os.makedirs(APP_DATA_DIR)

CONFIG_FILE = os.path.join(APP_DATA_DIR, "settings.json")

# Eingabesprachen - Top 6 europäische Sprachen zuerst, dann alphabetisch
# Verwendet Listen statt Dictionaries für definierte Reihenfolge
LANGUAGE_CODES = {
    "Deutsch": "de",
    "Automatisch": None,
    "Englisch": "en",
    "Französisch": "fr",
    "Spanisch": "es",
    "Italienisch": "it",
    # --- Rest alphabetisch ---
    "Arabisch": "ar",
    "Bengalisch": "bn",
    "Bulgarisch": "bg",
    "Chinesisch": "zh",
    "Dänisch": "da",
    "Finnisch": "fi",
    "Griechisch": "el",
    "Hebräisch": "he",
    "Hindi": "hi",
    "Indonesisch": "id",
    "Japanisch": "ja",
    "Katalanisch": "ca",
    "Koreanisch": "ko",
    "Kroatisch": "hr",
    "Lettisch": "lv",
    "Litauisch": "lt",
    "Malaiisch": "ms",
    "Niederländisch": "nl",
    "Norwegisch": "no",
    "Persisch": "fa",
    "Polnisch": "pl",
    "Portugiesisch": "pt",
    "Rumänisch": "ro",
    "Russisch": "ru",
    "Schwedisch": "sv",
    "Slowakisch": "sk",
    "Slowenisch": "sl",
    "Tamilisch": "ta",
    "Thailändisch": "th",
    "Tschechisch": "cs",
    "Türkisch": "tr",
    "Ukrainisch": "uk",
    "Ungarisch": "hu",
    "Urdu": "ur",
    "Vietnamesisch": "vi",
}

# Sortierte Listen für Dropdowns (definierte Reihenfolge!)
LANGUAGES = [
    "Deutsch", "Automatisch", "Englisch", "Französisch", "Spanisch", "Italienisch",
    "───────────",  # Trennlinie
    "Arabisch", "Bengalisch", "Bulgarisch", "Chinesisch", "Dänisch", "Finnisch",
    "Griechisch", "Hebräisch", "Hindi", "Indonesisch", "Japanisch", "Katalanisch",
    "Koreanisch", "Kroatisch", "Lettisch", "Litauisch", "Malaiisch", "Niederländisch",
    "Norwegisch", "Persisch", "Polnisch", "Portugiesisch", "Rumänisch", "Russisch",
    "Schwedisch", "Slowakisch", "Slowenisch", "Tamilisch", "Thailändisch", "Tschechisch",
    "Türkisch", "Ukrainisch", "Ungarisch", "Urdu", "Vietnamesisch",
]

# Zielsprachen für Übersetzer (OHNE Automatisch)
TARGET_LANGUAGES = [
    "Deutsch", "Englisch", "Französisch", "Spanisch", "Italienisch", "Niederländisch",
    "───────────",  # Trennlinie
    "Arabisch", "Bengalisch", "Bulgarisch", "Chinesisch", "Dänisch", "Finnisch",
    "Griechisch", "Hebräisch", "Hindi", "Indonesisch", "Japanisch", "Katalanisch",
    "Koreanisch", "Kroatisch", "Lettisch", "Litauisch", "Malaiisch", "Norwegisch",
    "Persisch", "Polnisch", "Portugiesisch", "Rumänisch", "Russisch", "Schwedisch",
    "Slowakisch", "Slowenisch", "Tamilisch", "Thailändisch", "Tschechisch", "Türkisch",
    "Ukrainisch", "Ungarisch", "Urdu", "Vietnamesisch",
]

DEFAULT_CONFIG = {
    "hotkey": "ctrl_r",
    "device_index": None,
    "device_name": None,  # Robustheit gegen ID-Änderungen (Docking Station)
    "mode": "Dynamisches Diktat",
    "language": "Deutsch",
    "target_language": "Englisch",  # Zielsprache für Übersetzer-Modus
    "audio_sensitivity": 0.005,  # Mindest-Audiopegel (RMS) für Aufnahme
    # API Key wird aus .env oder Umgebungsvariable geladen
    "api_key": os.getenv("GROQ_API_KEY", ""),
    "custom_instructions": "",  # Persönliche Präferenzen für alle LLM-Aufrufe
    "custom_buttons": [],  # Benutzerdefinierte Schnell-Buttons (max. 4)
    "last_seen_version": None,  # Zeigt Support-Seite nach Update
}

class ConfigManager:
    def __init__(self):
        self.config = DEFAULT_CONFIG.copy()
        self.load_config()

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r") as f:
                    loaded = json.load(f)
                    self.config.update(loaded)
            except Exception as e:
                print(f"Config Load Error: {e}")
        # Optionaler Fallback: Umgebungsvariable GROQ_API_KEY
        if not self.config.get("api_key"):
            env_key = os.getenv("GROQ_API_KEY")
            if env_key:
                self.config["api_key"] = env_key

    def save_config(self):
        try:
            with open(CONFIG_FILE, "w") as f:
                json.dump(self.config, f, indent=4)
        except Exception as e:
            print(f"Config Save Error: {e}")

    def get(self, key):
        return self.config.get(key, DEFAULT_CONFIG.get(key))

    def set(self, key, value):
        self.config[key] = value
        self.save_config()

    def get_language_code(self):
        lang_name = self.get("language")
        return LANGUAGE_CODES.get(lang_name, "de")

    def get_hotkey_display_name(self):
        """Gibt lesbaren Namen für den aktuellen Hotkey zurück"""
        return format_hotkey_name(self.get("hotkey"))


def format_hotkey_name(hotkey_code):
    """Wandelt internen Hotkey-Code in lesbaren deutschen Namen um"""
    if not hotkey_code:
        return "Nicht gesetzt"

    # Mapping für spezielle Tasten
    HOTKEY_NAMES = {
        # Strg-Tasten
        "ctrl_r": "Rechte Strg-Taste",
        "ctrl_l": "Linke Strg-Taste",
        # Alt-Tasten
        "alt_r": "Rechte Alt-Taste",
        "alt_l": "Linke Alt-Taste",
        "alt_gr": "AltGr-Taste",
        # Shift-Tasten
        "shift_r": "Rechte Shift-Taste",
        "shift_l": "Linke Shift-Taste",
        # Windows-Tasten
        "cmd_r": "Rechte Windows-Taste",
        "cmd_l": "Linke Windows-Taste",
        "cmd": "Windows-Taste",
        # Sondertasten
        "caps_lock": "Feststelltaste",
        "scroll_lock": "Rollen-Taste",
        "pause": "Pause-Taste",
        "insert": "Einfg-Taste",
        "delete": "Entf-Taste",
        "home": "Pos1-Taste",
        "end": "Ende-Taste",
        "page_up": "Bild↑-Taste",
        "page_down": "Bild↓-Taste",
        "print_screen": "Druck-Taste",
        "num_lock": "Num-Taste",
        # Funktionstasten
        "f1": "F1", "f2": "F2", "f3": "F3", "f4": "F4",
        "f5": "F5", "f6": "F6", "f7": "F7", "f8": "F8",
        "f9": "F9", "f10": "F10", "f11": "F11", "f12": "F12",
        # Escape
        "esc": "Escape-Taste",
        "escape": "Escape-Taste",
        # Tab
        "tab": "Tab-Taste",
        # Space
        "space": "Leertaste",
    }

    key = hotkey_code.lower()

    # Direkte Übersetzung wenn vorhanden
    if key in HOTKEY_NAMES:
        return HOTKEY_NAMES[key]

    # Fallback: Formatiere als "Taste X"
    return f"Taste {hotkey_code.upper()}"

