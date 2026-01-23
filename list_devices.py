import sounddevice as sd

print("=== ALLE AUDIO-GERÄTE ===")
devices = sd.query_devices()
for i, d in enumerate(devices):
    input_ch = d.get('max_input_channels', 0)
    if input_ch > 0:
        print(f"[INPUT] {i}: {d['name']}")
    else:
        print(f"[OUTPUT] {i}: {d['name']}")
