import os
import sys
import logging
import time

print("Starting Debug Script...")
try:
    from data_handler import DataHandler
    print("Import successful.")
    
    dh = DataHandler()
    print(f"DataHandler initialized. Log Path: {dh.get_log_file_path()}")
    
    msg = f"DEBUG LOG ENTRY {time.time()}"
    print(f"Attempting to write: {msg}")
    
    dh.log(msg, "info")
    print("Write called.")
    
    # Check file content immediately
    log_path = dh.get_log_file_path()
    if os.path.exists(log_path):
        with open(log_path, 'r', encoding='utf-8') as f:
            content = f.read()
            if msg in content:
                print("SUCCESS: Log entry found in file.")
            else:
                print("FAILURE: Log entry NOT found in file.")
                print("Last 500 chars of log:")
                print(content[-500:])
    else:
        print("FAILURE: Log file does not exist.")

except Exception as e:
    print(f"CRITICAL ERROR: {e}")
    import traceback
    traceback.print_exc()
