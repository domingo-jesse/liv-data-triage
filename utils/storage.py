import json
from pathlib import Path
from typing import Any

DATA_FILE = Path("data/tickets.json")


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
    if not DATA_FILE.exists():
        DATA_FILE.write_text(json.dumps(_default_payload(), indent=2), encoding="utf-8")


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
        payload = _default_payload()
        DATA_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return payload


def save_data(payload: dict[str, Any]) -> None:
    ensure_data_file()
    tmp_file = DATA_FILE.with_suffix(".json.tmp")
    tmp_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp_file.replace(DATA_FILE)
