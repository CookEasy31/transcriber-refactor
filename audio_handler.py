"""Audio-Handler mit optimierten Lazy Imports für schnelleren App-Start"""
import os
import time
import wave
import struct
import shutil
import threading
from collections import deque
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
        self.last_recording_file = os.path.join(APP_DATA_DIR, "last_recording.wav")
        self._devices_cache = None
        self.device_index = device_index
        self.audio_sensitivity = audio_sensitivity if audio_sensitivity else MIN_AUDIO_RMS
        self.current_rms = 0
        # Thread-safety lock for recording state
        self._recording_lock = threading.Lock()
        self.monitor_stream = None
        # Unified stream for zero-latency recording
        self._unified_stream = None
        self._current_device_index = None
        # Für automatische Geräte-Wiederherstellung
        self._last_device_name = None
        # Pre-recording buffer (500ms before button press)
        self._pre_buffer_ms = 500
        self._pre_buffer_samples = int(self.sample_rate * self._pre_buffer_ms / 1000)
        # Use deque with maxlen for O(1) append/pop instead of O(n) list.pop(0)
        self._pre_buffer_max_chunks = max(1, self._pre_buffer_samples // 1024 + 2)
        self._pre_buffer = deque(maxlen=self._pre_buffer_max_chunks)
        # Cached numpy functions for callback performance
        self._np_sqrt = None
        self._np_mean = None

    def get_input_devices(self, test_functionality=True):
        """Gibt eine gefilterte Liste relevanter Eingabegeräte zurück: [{'id': 1, 'name': 'Mic X'}]
        
        Args:
            test_functionality: Wenn True, werden nur Geräte zurückgegeben die tatsächlich funktionieren
        """
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
                
                # Duplikate überspringen (erste 25 Zeichen vergleichen - Namen werden manchmal abgeschnitten)
                name_key = name[:25]
                if name_key in seen_names:
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
                
                # Funktionalitätstest: Gerät muss sich öffnen lassen
                if test_functionality:
                    if not self._test_device(i):
                        print(f"[Audio] Device {i} '{name}' nicht verfügbar - übersprungen")
                        continue
                
                seen_names.add(name_key)
                input_devices.append({"id": i, "name": name})
        
        self._devices_cache = input_devices
        return input_devices
    
    def _test_device(self, device_index):
        """Testet ob ein Gerät tatsächlich geöffnet werden kann"""
        sd = _get_sounddevice()
        try:
            # Versuche kurz einen Stream zu öffnen
            stream = sd.InputStream(
                samplerate=16000,
                device=device_index,
                channels=1,
                blocksize=1024
            )
            stream.start()
            stream.stop()
            stream.close()
            return True
        except Exception:
            return False

    def reload_devices(self, test_functionality=False):
        """Löscht den Cache und zwingt zum erneuten Einlesen der Geräte

        Args:
            test_functionality: False = schnell (für Dropdown), True = mit Test (langsam)
        """
        self._devices_cache = None

        # Force sounddevice to refresh its internal device list
        sd = _get_sounddevice()
        try:
            # This forces sounddevice to re-query the host API
            sd._terminate()
            sd._initialize()
        except:
            pass  # Some versions don't have these methods

        # Skip device testing for faster dropdown population
        return self.get_input_devices(test_functionality=test_functionality)

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

    def _unified_callback(self, indata, frames, time_info, status):
        """Ein Callback für sowohl Monitoring als auch Recording"""
        if indata.size > 0:
            # Use cached numpy functions for performance
            self.current_rms = self._np_sqrt(self._np_mean(indata * indata))

            # Always keep pre-buffer filled - deque auto-removes oldest (O(1))
            self._pre_buffer.append(indata.copy())

            # Nur bei aktiver Aufnahme Daten speichern
            with self._recording_lock:
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

    def _start_unified_stream(self, device_index, device_name=None):
        """Startet den unified stream auf einem Gerät mit automatischem Fallback"""
        # Pre-load numpy BEFORE stream starts to avoid blocking in callback
        np = _get_numpy()
        self._np_sqrt = np.sqrt
        self._np_mean = np.mean

        sd = _get_sounddevice()

        # Speichere Präferenz für späteren Fallback
        if device_name:
            self._last_device_name = device_name

        # Liste der zu versuchenden Devices: [bevorzugtes, by-name, default]
        devices_to_try = []

        if device_index is not None:
            devices_to_try.append(("preferred", device_index))

        # By-name lookup als zweite Option
        if self._last_device_name:
            name_id = self.find_device_by_name(self._last_device_name)
            if name_id is not None and name_id != device_index:
                devices_to_try.append(("by-name", name_id))

        # Default device als letzte Option
        devices_to_try.append(("default", None))

        for source, dev_id in devices_to_try:
            try:
                self._unified_stream = sd.InputStream(
                    samplerate=self.sample_rate,
                    device=dev_id,
                    channels=1,
                    callback=self._unified_callback
                )
                self._unified_stream.start()
                self._current_device_index = dev_id

                if source == "preferred":
                    print(f"[Audio] Unified stream started on preferred device {dev_id}")
                elif source == "by-name":
                    print(f"[Audio] Unified stream started on device found by name: {dev_id}")
                else:
                    print(f"[Audio] Unified stream started on DEFAULT device (fallback)")

                return dev_id  # Gib die tatsächlich verwendete Device-ID zurück

            except Exception as e:
                print(f"[Audio] Failed to start stream on {source} device {dev_id}: {e}")
                continue

        # Alle Versuche fehlgeschlagen
        print("[Audio] CRITICAL: Could not start audio stream on any device!")
        self._unified_stream = None
        return None

    def start_monitor(self, device_index=None, device_name=None):
        """Startet den unified stream für Monitoring (und bereitet Recording vor)"""
        if self._unified_stream:
            return self._current_device_index  # Bereits aktiv

        return self._start_unified_stream(device_index, device_name)

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
        """Startet Aufnahme - nutzt unified stream fuer sofortigen Start"""
        with self._recording_lock:
            if self.is_recording:
                return

            # Prepend pre-buffer (last 500ms before button press)
            if self._pre_buffer:
                self.recording = list(self._pre_buffer)
                pre_samples = sum(len(chunk) for chunk in self.recording)
                print(f"[Audio] Pre-buffer: {pre_samples} samples ({pre_samples/self.sample_rate*1000:.0f}ms)")
            else:
                self.recording = []

            self.start_time = time.time() - (self._pre_buffer_ms / 1000)
            self.is_recording = True

        # Wenn unified stream laeuft: SOFORT aufnehmen (zero latency!)
        if self._unified_stream:
            print("[Audio] INSTANT recording start (unified stream active)")
            return

        # Fallback: Unified stream nicht aktiv, starte ihn mit Recording
        print(f"[Audio] Starting unified stream for recording on device: {device_index}")
        self._start_unified_stream(device_index)

    def stop_recording(self):
        """Stoppt Aufnahme - laesst unified stream weiterlaufen fuer naechste Aufnahme"""
        print(f"[Audio] stop_recording called. is_recording={self.is_recording}, unified_stream={self._unified_stream is not None}")

        with self._recording_lock:
            if not self.is_recording:
                print("[Audio] Early exit: Not recording")
                return None
            self.is_recording = False
            recording_snapshot = list(self.recording)  # Snapshot under lock
            self.recording = []

        duration = time.time() - self.start_time
        print(f"[Audio] Recording duration: {duration:.2f}s (min: {MIN_DURATION_SECONDS}s)")

        if duration < MIN_DURATION_SECONDS:
            print(f"[Audio] Recording too short ({duration:.2f}s < {MIN_DURATION_SECONDS}s)")
            return None

        if not recording_snapshot:
            print("[Audio] No recording data captured!")
            return None

        np = _get_numpy()

        recording_array = np.concatenate(recording_snapshot, axis=0)
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

        # Save a copy as last_recording for repeat functionality
        try:
            shutil.copy2(self.filename, self.last_recording_file)
            print(f"[Audio] Last recording saved: {self.last_recording_file}")
        except Exception as e:
            print(f"[Audio] Could not save last recording: {e}")

        file_size = os.path.getsize(self.filename)
        print(f"[Audio] Saved: {self.filename} ({file_size} bytes)")
        return self.filename

    def check_device_health(self):
        """
        Prüft ob das Audio-Device noch funktioniert (z.B. nach Energiesparmodus).

        Returns:
            dict: {
                'healthy': bool,
                'recovered': bool,
                'message': str,
                'device_id': int or None
            }
        """
        result = {
            'healthy': True,
            'recovered': False,
            'message': 'OK',
            'device_id': self._current_device_index
        }

        # Kein Stream aktiv - nichts zu prüfen
        if not self._unified_stream:
            result['healthy'] = False
            result['message'] = 'Kein Audio-Stream aktiv'
            return result

        sd = _get_sounddevice()

        # Prüfe ob der Stream noch aktiv ist
        try:
            stream_active = self._unified_stream.active
        except Exception as e:
            stream_active = False
            print(f"[Audio] Stream check failed: {e}")

        if not stream_active:
            print("[Audio] Health check: Stream inactive, attempting recovery...")
            result['healthy'] = False
            result['message'] = 'Stream inaktiv'

            # Versuche Recovery
            try:
                # Stream schließen falls noch offen
                try:
                    self._unified_stream.stop()
                    self._unified_stream.close()
                except:
                    pass
                self._unified_stream = None

                # Neuen Stream starten
                new_device = self._start_unified_stream(
                    self._current_device_index,
                    self._last_device_name
                )

                if new_device is not None:
                    result['recovered'] = True
                    result['healthy'] = True
                    result['device_id'] = new_device
                    result['message'] = f'Wiederhergestellt auf Device {new_device}'
                    print(f"[Audio] Health check: Recovered on device {new_device}")
                else:
                    result['message'] = 'Wiederherstellung fehlgeschlagen'
                    print("[Audio] Health check: Recovery failed!")

            except Exception as e:
                result['message'] = f'Recovery-Fehler: {e}'
                print(f"[Audio] Health check recovery error: {e}")

            return result

        # Stream aktiv - prüfe ob Device noch existiert
        if self._current_device_index is not None:
            if not self.is_device_available(self._current_device_index):
                print(f"[Audio] Health check: Device {self._current_device_index} no longer available")
                result['healthy'] = False
                result['message'] = f'Device {self._current_device_index} nicht mehr verfügbar'

                # Versuche Recovery auf anderem Device
                try:
                    self.stop_monitor()
                    new_device = self._start_unified_stream(
                        self._current_device_index,
                        self._last_device_name
                    )

                    if new_device is not None:
                        result['recovered'] = True
                        result['healthy'] = True
                        result['device_id'] = new_device
                        result['message'] = f'Gewechselt zu Device {new_device}'
                        print(f"[Audio] Health check: Switched to device {new_device}")
                    else:
                        result['message'] = 'Kein funktionierendes Device gefunden'

                except Exception as e:
                    result['message'] = f'Wechsel-Fehler: {e}'
                    print(f"[Audio] Health check switch error: {e}")

        return result

    def get_last_recording(self):
        """Returns path to last recording if it exists"""
        if os.path.exists(self.last_recording_file):
            return self.last_recording_file
        return None

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
