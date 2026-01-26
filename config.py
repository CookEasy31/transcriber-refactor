import json
import os
from dotenv import load_dotenv

# .env Datei laden (falls vorhanden)
load_dotenv()

APP_NAME = "act Scriber"
APP_VERSION = "1.3.9"
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

