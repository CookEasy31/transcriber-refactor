import sqlite3
import logging
from logging.handlers import TimedRotatingFileHandler
import os
import threading
from config import APP_DATA_DIR

LOG_DIR = os.path.join(APP_DATA_DIR, "logs")
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

DB_FILE = os.path.join(APP_DATA_DIR, "history.db")

class DataHandler:
    def __init__(self):
        self.db_lock = threading.Lock()
        self.setup_logging()
        self.init_db()

    def setup_logging(self):
        self.logger = logging.getLogger("actScribe")
        self.logger.setLevel(logging.INFO)
        
        log_file = os.path.join(LOG_DIR, "app_log.log")
        # Rotation um Mitternacht, behalte 30 Tage
        handler = TimedRotatingFileHandler(log_file, when="midnight", interval=1, backupCount=30, encoding='utf-8')
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        
        if not self.logger.handlers:
            self.logger.addHandler(handler)

    def log(self, message, level="info"):
        if level == "info": self.logger.info(message)
        elif level == "error": self.logger.error(message)
        elif level == "warning": self.logger.warning(message)
        
        # Force Flush
        for h in self.logger.handlers:
            h.flush()
            
        print(f"[{level.upper()}] {message}")

    def init_db(self):
        try:
            self.conn = sqlite3.connect(DB_FILE, check_same_thread=False)
            with self.db_lock:
                cursor = self.conn.cursor()
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                        mode TEXT,
                        original_text TEXT,
                        formatted_text TEXT
                    )
                ''')
                self.conn.commit()
        except Exception as e:
            self.log(f"DB Init Error: {e}", "error")

    def save_entry(self, mode, original, formatted):
        try:
            with self.db_lock:
                cursor = self.conn.cursor()
                cursor.execute(
                    'INSERT INTO history (mode, original_text, formatted_text) VALUES (?, ?, ?)',
                    (mode, original, formatted)
                )
                self.conn.commit()
        except Exception as e:
            self.log(f"DB Save Error: {e}", "error")

    def get_last_entries(self, limit=10):
        try:
            with self.db_lock:
                cursor = self.conn.cursor()
                cursor.execute('SELECT * FROM history ORDER BY timestamp DESC LIMIT ?', (limit,))
                return cursor.fetchall()
        except Exception as e:
            self.log(f"DB Fetch Error: {e}", "error")
            return []

    def get_log_content(self, lines=100):
        """Liest die letzten N Zeilen aus der Log-Datei"""
        log_file = os.path.join(LOG_DIR, "app_log.log")
        try:
            if os.path.exists(log_file):
                with open(log_file, 'r', encoding='utf-8') as f:
                    all_lines = f.readlines()
                    return ''.join(all_lines[-lines:])
            return "Keine Log-Datei gefunden."
        except Exception as e:
            return f"Fehler beim Lesen der Logs: {e}"

    def get_log_file_path(self):
        """Gibt den Pfad zur Log-Datei zurück"""
        return os.path.join(LOG_DIR, "app_log.log")

    def close(self):
        with self.db_lock:
            self.conn.close()

