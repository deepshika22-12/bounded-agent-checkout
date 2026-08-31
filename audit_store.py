"""
audit_store.py

Makes the audit trail survive server restarts by backing it with a JSON file
instead of a plain Python list living only in memory.

Design is intentionally simple: the whole log is kept in memory (a list of
dicts) AND mirrored to disk on every append. For a hackathon-scale audit
trail (hundreds of entries, not millions) rewriting the full file on each
append is simple, easy to reason about, and hard to get subtly wrong --
which matters more here than raw performance.
"""

import json
from datetime import datetime
from pathlib import Path

# audit_log.json lives in the project root, next to main.py
AUDIT_LOG_PATH = Path(__file__).resolve().parent / "audit_log.json"

# The in-memory list every other module reads from. Loaded once at import
# time, then kept in sync with disk on every append.
_audit_entries: list[dict] = []


def _load_from_disk() -> list[dict]:
    """
    Load existing audit entries from disk, if the file exists.

    Handles two failure modes without crashing the server:
      1. File doesn't exist yet (first run ever) -> start empty.
      2. File exists but isn't valid JSON (e.g. manually edited, or the
         process died mid-write) -> log a warning and start empty, rather
         than taking down the whole app over a corrupted log file.
    """
    if not AUDIT_LOG_PATH.exists():
        return []

    try:
        with open(AUDIT_LOG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            if not isinstance(data, list):
                print(
                    f"[audit_store] WARNING: {AUDIT_LOG_PATH} did not contain "
                    "a JSON list as expected. Starting with an empty audit log."
                )
                return []
            return data
    except json.JSONDecodeError:
        print(
            f"[audit_store] WARNING: {AUDIT_LOG_PATH} contains invalid JSON "
            "(possibly corrupted). Starting with an empty audit log instead "
            "of crashing. The corrupted file was left untouched -- back it "
            "up or delete it manually if you want a clean slate."
        )
        return []


def _save_to_disk() -> None:
    """Write the full in-memory list back to the JSON file."""
    try:
        with open(AUDIT_LOG_PATH, "w", encoding="utf-8") as f:
            json.dump(_audit_entries, f, indent=2, default=str)
    except OSError as e:
        # If disk write fails (permissions, disk full, etc.), don't crash
        # the request that triggered this -- the entry still exists in
        # memory for this session, it just won't survive a restart.
        print(f"[audit_store] WARNING: could not write audit log to disk: {e}")


# Load whatever's already on disk as soon as this module is imported.
_audit_entries = _load_from_disk()


def append_audit_entry(event_type: str, details: dict) -> None:
    """
    Add one entry to the audit trail and persist it immediately.

    Same shape as the original in-memory version, so nothing downstream
    (the /audit endpoint, the Streamlit frontend) needs to change.
    """
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "event_type": event_type,
        "details": details,
    }
    _audit_entries.append(entry)
    _save_to_disk()


def get_all_audit_entries() -> list[dict]:
    """Return the current full audit trail (most-recent-last, same as before)."""
    return _audit_entries
