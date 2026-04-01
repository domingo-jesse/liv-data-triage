import json
import os
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROJECT_DATA_FILE = PROJECT_ROOT / "data" / "tickets.json"
LEGACY_HOME_DATA_FILE = Path.home() / ".liv_ticketing" / "tickets.json"


def _resolve_data_file() -> Path:
    configured_path = os.getenv("TICKET_DATA_FILE", "").strip()
    if configured_path:
        return Path(configured_path).expanduser()
    return PROJECT_DATA_FILE


DATA_FILE = _resolve_data_file()
BACKUP_FILE = DATA_FILE.with_suffix(".json.bak")


def _default_payload() -> dict[str, Any]:
    return {
        "tickets": [],
        "archived_tickets": [],
        "activity_log": [],
        "next_ticket_id": 1,
        "ai_instruction_cache": {},
    }


def ensure_data_file() -> None:
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not DATA_FILE.exists() and LEGACY_HOME_DATA_FILE.exists():
        DATA_FILE.write_text(LEGACY_HOME_DATA_FILE.read_text(encoding="utf-8"), encoding="utf-8")
    if not DATA_FILE.exists() and BACKUP_FILE.exists():
        DATA_FILE.write_text(BACKUP_FILE.read_text(encoding="utf-8"), encoding="utf-8")
    if not DATA_FILE.exists():
        payload = _default_payload()
        serialized = json.dumps(payload, indent=2)
        DATA_FILE.write_text(serialized, encoding="utf-8")
        BACKUP_FILE.write_text(serialized, encoding="utf-8")


def load_data() -> dict[str, Any]:
    ensure_data_file()
    try:
        payload = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        # Backfill newly added top-level keys for older JSON payloads.
        payload.setdefault("tickets", [])
        payload.setdefault("archived_tickets", [])
        payload.setdefault("activity_log", [])
        payload.setdefault("next_ticket_id", 1)
        payload.setdefault("ai_instruction_cache", {})
        return payload
    except json.JSONDecodeError:
        if BACKUP_FILE.exists():
            try:
                payload = json.loads(BACKUP_FILE.read_text(encoding="utf-8"))
                payload.setdefault("tickets", [])
                payload.setdefault("archived_tickets", [])
                payload.setdefault("activity_log", [])
                payload.setdefault("next_ticket_id", 1)
                payload.setdefault("ai_instruction_cache", {})
                DATA_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
                return payload
            except json.JSONDecodeError:
                pass
        payload = _default_payload()
        serialized = json.dumps(payload, indent=2)
        DATA_FILE.write_text(serialized, encoding="utf-8")
        BACKUP_FILE.write_text(serialized, encoding="utf-8")
        return payload


def save_data(payload: dict[str, Any]) -> None:
    ensure_data_file()
    tmp_file = DATA_FILE.with_suffix(".json.tmp")
    serialized = json.dumps(payload, indent=2)
    tmp_file.write_text(serialized, encoding="utf-8")
    tmp_file.replace(DATA_FILE)
    BACKUP_FILE.write_text(serialized, encoding="utf-8")
