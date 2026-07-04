import json
import os
from datetime import datetime

LOG_FILE = "data/action_log.json"

def log_action(action_type, thread_subject, detail, action_id):
    """
    Appends a record to action_log.json.
    Each record contains: timestamp, action_type, thread_subject, detail, id.
    """
    record = {
        "timestamp": datetime.now().isoformat(),
        "action_type": action_type,
        "thread_subject": thread_subject,
        "detail": detail,
        "id": action_id
    }
    
    log_data = get_action_log()
    log_data.append(record)
    
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(log_data, f, indent=2)

def get_action_log():
    """
    Reads action_log.json and returns the full list.
    Returns [] if the file does not exist or is empty.
    """
    if not os.path.exists(LOG_FILE) or os.path.getsize(LOG_FILE) == 0:
        return []
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
            return []
    except Exception:
        return []

def clear_log():
    """
    Writes an empty list to action_log.json.
    """
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump([], f, indent=2)
