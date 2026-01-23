"""Audio-Handler mit optimierten Lazy Imports für schnelleren App-Start"""
import os
import time
import wave
import struct
from config import APP_DATA_DIR

MAX_DURATION_SECONDS = 600
MIN_DURATION_SECONDS = 2.0
MIN_AUDIO_RMS = 0.005  # Mindest-Audiopegel (RMS) - unter diesem Wert gilt als "kein Audio"

# Spezielle Rückgabewerte
NO_AUDIO_DETECTED = "__NO_AUDIO_DETECTED__"

# Lazy-loaded modules (erst bei Bedarf laden)
_sd = None
_np = None


def _get_sounddevice():
    """Lazy import für sounddevice"""
    global _sd
    if _sd is None:
        import sounddevice
        _sd = sounddevice
    return _sd


def _get_numpy():
    """Lazy import für numpy"""
    global _np
    if _np is None:
        import numpy
        _np = numpy
    return _np


class AudioRecorder:
    def __init__(self, device_index=None, audio_sensitivity=None):
        self.recording = []
        self.stream = None
        self.sample_rate = 16000
        self.is_recording = False
        self.start_time = 0
        self.filename = os.path.join(APP_DATA_DIR, "temp_recording.wav")
        self._devices_cache = None
        self.device_index = device_index
        self.audio_sensitivity = audio_sensitivity if audio_sensitivity else MIN_AUDIO_RMS
        self.current_rms = 0
        self.monitor_stream = None
        # Unified stream for zero-latency recording
        self._unified_stream = None
        self._current_device_index = None
        # Für automatische Geräte-Wiederherstellung
        self._last_device_name = None

    def get_input_devices(self):
        """Gibt eine gefilterte Liste relevanter Eingabegeräte zurück: [{'id': 1, 'name': 'Mic X'}]"""
        # Cache verwenden für schnelleren wiederholten Zugriff
        if self._devices_cache is not None:
            return self._devices_cache
        
        sd = _get_sounddevice()
        devices = sd.query_devices()
        
        # Begriffe die auf irrelevante Geräte hinweisen (lowercase für Vergleich)
        exclude_keywords = [
            "stereomix", "stereo mix", "wave out", "what u hear",
            "output", "lautsprecher", "speaker", "playback",
            "loopback", "virtual", "cable",
        ]
        
        # Leere oder nutzlose Namen-Muster
        exclude_patterns = [
            "()",  # Leere Klammern wie "Mikrofonarray 1 ()"
        ]
        
        input_devices = []
        seen_names = set()  # Für Duplikat-Erkennung
        
        for i, dev in enumerate(devices):
            if dev["max_input_channels"] > 0:
                name = dev["name"]
                name_lower = name.lower()
                
                # Duplikate überspringen (exakt gleicher Name)
                if name in seen_names:
                    continue
                
                # Ausschluss-Keywords prüfen
                if any(kw in name_lower for kw in exclude_keywords):
                    continue
                
                # Leere/nutzlose Namen-Muster prüfen
                if any(pattern in name for pattern in exclude_patterns):
                    continue
                
                # Sehr kurze oder leere Namen überspringen
                if len(name.strip()) < 3:
                    continue
                
                seen_names.add(name)
                input_devices.append({"id": i, "name": name})
        
        self._devices_cache = input_devices
        return input_devices

    def reload_devices(self):
        """Löscht den Cache und zwingt zum erneuten Einlesen der Geräte"""
        self._devices_cache = None

        # Force sounddevice to refresh its internal device list
        sd = _get_sounddevice()
        try:
            # This forces sounddevice to re-query the host API
            sd._terminate()
            sd._initialize()
        except:
            pass  # Some versions don't have these methods

        return self.get_input_devices()

    def is_device_available(self, device_index):
        """Prüft, ob ein Gerät mit der gegebenen ID noch verfügbar und funktionsfähig ist"""
        if device_index is None:
            return True  # Default device

        sd = _get_sounddevice()
        try:
            devices = sd.query_devices()
            if device_index >= len(devices):
                return False
            dev = devices[device_index]
            return dev["max_input_channels"] > 0
        except:
            return False

    def find_device_by_name(self, device_name):
        """Sucht ein Gerät anhand des Namens und gibt die aktuelle ID zurück"""
        if not device_name:
            return None

        devices = self.reload_devices()  # Frische Liste holen
        for dev in devices:
            if dev["name"] == device_name:
                print(f"[Audio] Device '{device_name}' found with new ID: {dev['id']}")
                return dev["id"]
        return None

    def ensure_device_available(self, device_index, device_name=None):
        """
        Stellt sicher, dass das Gerät verfügbar ist.
        Bei Docking-Station-Wechsel wird das Gerät per Name wiederhergestellt.

        Returns: (device_id, needs_stream_restart)
        """
        # Prüfe ob aktuelles Gerät noch funktioniert
        if self.is_device_available(device_index):
            return device_index, False

        print(f"[Audio] Device {device_index} not available, attempting recovery...")

        # Versuche Gerät per Name zu finden (Docking Station Szenario)
        if device_name:
            new_id = self.find_device_by_name(device_name)
            if new_id is not None:
                print(f"[Audio] Recovered device '{device_name}' at new ID {new_id}")
                return new_id, True

        # Fallback: Default device verwenden
        print("[Audio] Device recovery failed, falling back to default device")
        return None, True

    def start_monitor(self, device_index=None):
        """Startet einen Stream nur zur Pegelüberwachung (ohne Aufnahme)"""
        if self.monitor_stream or self.is_recording:
            return
            
        sd = _get_sounddevice()
        np = _get_numpy()
        
        def callback(indata, frames, time_info, status):
            if indata.size > 0:
                self.current_rms = float(np.sqrt(np.mean(indata**2)))

        try:
            self.monitor_stream = sd.InputStream(
                samplerate=self.sample_rate,
                device=device_index,
                channels=1,
                callback=callback
            )
            self.monitor_stream.start()
        except:
            pass

    def stop_monitor(self):
        """Stoppt den Monitor-Stream"""
        if self.monitor_stream:
            try:
                self.monitor_stream.stop()
                self.monitor_stream.close()
            except:
                pass
            self.monitor_stream = None
        self.current_rms = 0
        # Restart unified stream if it was running
        self._restart_unified_stream()

    def _unified_callback(self, indata, frames, time_info, status):
        """Ein Callback für sowohl Monitoring als auch Recording"""
        np = _get_numpy()
        if indata.size > 0:
            self.current_rms = float(np.sqrt(np.mean(indata**2)))
            
            # Nur bei aktiver Aufnahme Daten speichern
            if self.is_recording:
                if len(self.recording) * frames / self.sample_rate < MAX_DURATION_SECONDS:
                    self.recording.append(indata.copy())
                else:
                    self.is_recording = False

    def _restart_unified_stream(self):
        """Startet den unified stream (nach Device-Wechsel etc.)"""
        if self._unified_stream:
            try:
                self._unified_stream.stop()
                self._unified_stream.close()
            except:
                pass
            self._unified_stream = None
        
        if self._current_device_index is not None:
            self._start_unified_stream(self._current_device_index)

    def _start_unified_stream(self, device_index):
        """Startet den unified stream auf einem Gerät"""
        sd = _get_sounddevice()
        try:
            self._unified_stream = sd.InputStream(
                samplerate=self.sample_rate,
                device=device_index,
                channels=1,
                callback=self._unified_callback
            )
            self._unified_stream.start()
            self._current_device_index = device_index
            print(f"[Audio] Unified stream started on device {device_index}")
        except Exception as e:
            print(f"[Audio] Failed to start unified stream: {e}")
            self._unified_stream = None

    def start_monitor(self, device_index=None):
        """Startet den unified stream für Monitoring (und bereitet Recording vor)"""
        if self._unified_stream:
            return  # Bereits aktiv
        
        self._start_unified_stream(device_index)

    def stop_monitor(self):
        """Stoppt den unified stream komplett (nur bei App-Schließung oder Device-Wechsel)"""
        if self._unified_stream:
            try:
                self._unified_stream.stop()
                self._unified_stream.close()
            except:
                pass
            self._unified_stream = None
        self.current_rms = 0

    def start_recording(self, device_index=None):
        """Startet Aufnahme - nutzt unified stream für sofortigen Start"""
        if self.is_recording:
            return

        self.recording = []
        self.start_time = time.time()
        
        # Wenn unified stream läuft: SOFORT aufnehmen (zero latency!)
        if self._unified_stream:
            print("[Audio] INSTANT recording start (unified stream active)")
            self.is_recording = True
            return
        
        # Fallback: Unified stream nicht aktiv, starte ihn mit Recording
        print(f"[Audio] Starting unified stream for recording on device: {device_index}")
        self._start_unified_stream(device_index)
        self.is_recording = True

    def stop_recording(self):
        """Stoppt Aufnahme - lässt unified stream weiterlaufen für nächste Aufnahme"""
        print(f"[Audio] stop_recording called. is_recording={self.is_recording}, unified_stream={self._unified_stream is not None}")
        
        if not self.is_recording:
            print("[Audio] Early exit: Not recording")
            return None

        # Aufnahme stoppen, aber Stream NICHT beenden (für nächste Aufnahme bereit)
        self.is_recording = False

        duration = time.time() - self.start_time
        print(f"[Audio] Recording duration: {duration:.2f}s (min: {MIN_DURATION_SECONDS}s)")
        
        if duration < MIN_DURATION_SECONDS:
            print(f"[Audio] Recording too short ({duration:.2f}s < {MIN_DURATION_SECONDS}s)")
            return None

        if not self.recording:
            print("[Audio] No recording data captured!")
            return None

        np = _get_numpy()
        
        recording_array = np.concatenate(self.recording, axis=0)
        total_duration = len(recording_array) / self.sample_rate
        print(f"[Audio] Total samples: {len(recording_array)}, duration: {total_duration:.2f}s")

        if total_duration > MAX_DURATION_SECONDS:
            max_samples = int(MAX_DURATION_SECONDS * self.sample_rate)
            recording_array = recording_array[:max_samples]

        # Audio-Pegel prüfen (RMS = Root Mean Square)
        # Bei komplett stiller Aufnahme (falsches Mikrofon, kein Pegel) warnen
        rms = np.sqrt(np.mean(recording_array ** 2))
        print(f"[Audio] RMS Level: {rms:.6f}, Threshold: {self.audio_sensitivity}")
        
        if rms < self.audio_sensitivity:
            print(f"[Audio] Kein Audiopegel erkannt (RMS: {rms:.6f} < {self.audio_sensitivity})")
            return NO_AUDIO_DETECTED

        # Konvertiere zu 16-bit PCM
        wav_data = (recording_array * 32767).astype(np.int16)
        
        # Speichere mit eingebautem wave Modul (kein scipy nötig!)
        with wave.open(self.filename, 'wb') as wf:
            wf.setnchannels(1)  # Mono
            wf.setsampwidth(2)  # 16-bit = 2 bytes
            wf.setframerate(self.sample_rate)
            wf.writeframes(wav_data.tobytes())

        file_size = os.path.getsize(self.filename)
        print(f"[Audio] Saved: {self.filename} ({file_size} bytes)")
        return self.filename

    def close(self):
        """Schließt den Recorder und gibt Ressourcen frei."""
        self.stop_monitor()
        if self.stream:
            try:
                self.stream.stop()
                self.stream.close()
            except:
                pass
        self.stream = None
        self.is_recording = False
