import json
import os
import threading
from typing import Any, Dict, Optional

_lock = threading.Lock()


def ensure_file(path: str, default_content: Dict[str, Any]) -> None:
    """Create file with default JSON if it doesn't exist."""
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True) if os.path.dirname(path) else None
        with open(path, "w", encoding="utf-8") as f:
            json.dump(default_content, f, indent=2, ensure_ascii=False)


def read_json(path: str, default_content: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Thread-safe JSON read with optional default creation."""
    with _lock:
        if default_content is not None:
            ensure_file(path, default_content)
        if not os.path.exists(path):
            return default_content.copy() if default_content is not None else {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default_content.copy() if default_content is not None else {}


def write_json(path: str, data: Dict[str, Any]) -> bool:
    """Thread-safe atomic JSON write. Returns True on success."""
    tmp_path = f"{path}.tmp"
    with _lock:
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, path)
            return True
        except Exception:
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass
            return False


# High-level helpers
def get_bot_config() -> Dict[str, Any]:
    """Return the centralized bot configuration from config/bot_config.json.
    Ensures file exists with sensible defaults and returns its contents.
    """
    default = {
        "ADMIN_LOG_CHANNEL_ID": 1418956399404122132,
        "COMMAND_LOG_CHANNEL_ID": 1418322935789392110,
        "REPORT_LOG_CHANNEL_ID": 1418956399404122132,
        "MODERATOR_ROLE_ID": 1362049467934838985,
        "STAFF_ROLE_ID": 1418345309377003551,
        "WELCOME_CHANNEL_ID": 1362060484085547018,
        # Extra owners allowed to run critical admin commands besides the application owner
        "EXTRA_OWNER_IDS": [1033834366822002769]
    }
    return read_json("config/bot_config.json", default)
