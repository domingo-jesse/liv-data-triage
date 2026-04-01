from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any

STATUS_VALUES = ["New", "In Progress", "Waiting", "Completed"]
URGENCY_VALUES = ["Low", "Medium", "High", "Critical"]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ticket_label(ticket_id: int) -> str:
    return f"TKT-{ticket_id:04d}"


def instruction_cache_key(ticket_like: dict[str, Any]) -> str:
    base = "|".join([
        str(ticket_like.get("title", "")).strip().lower(),
        str(ticket_like.get("category", "")).strip().lower(),
        str(ticket_like.get("request_description", "")).strip().lower(),
        str(ticket_like.get("desired_outcome", "")).strip().lower(),
    ])
    return sha256(base.encode("utf-8")).hexdigest()


def add_activity(data: dict[str, Any], ticket_id: int | None, action: str, detail: str) -> None:
    data["activity_log"].insert(
        0,
        {
            "timestamp": now_iso(),
            "ticket_id": ticket_id,
            "action": action,
            "detail": detail,
        },
    )


def create_ticket(data: dict[str, Any], form: dict[str, str]) -> dict[str, Any]:
    ticket_id = data["next_ticket_id"]
    ticket = {
        "ticket_id": ticket_id,
        "ticket_code": ticket_label(ticket_id),
        "title": form["title"],
        "requester": form["requester"],
        "department": form["department"],
        "created_at": now_iso(),
        "urgency": form["urgency"],
        "status": "New",
        "category": form["category"],
        "request_description": form["request_description"],
        "desired_outcome": form["desired_outcome"],
        "ai_instructions": "",
        "notes": [],
        "completed_at": "",
        "history": [],
        "archived_at": "",
    }
    data["tickets"].insert(0, ticket)
    data["next_ticket_id"] += 1
    log_ticket_history(ticket, "Ticket Created", f"Created by {ticket['requester']}")
    add_activity(data, ticket_id, "ticket_created", f"{ticket['ticket_code']} created")
    return ticket


def log_ticket_history(ticket: dict[str, Any], action: str, detail: str) -> None:
    ticket["history"].insert(0, {"timestamp": now_iso(), "action": action, "detail": detail})


def find_ticket(data: dict[str, Any], ticket_id: int, include_archived: bool = False) -> dict[str, Any] | None:
    for t in data.get("tickets", []):
        if t["ticket_id"] == ticket_id:
            return t
    if include_archived:
        for t in data.get("archived_tickets", []):
            if t["ticket_id"] == ticket_id:
                return t
    return None


def archive_ticket(data: dict[str, Any], ticket_id: int) -> dict[str, Any] | None:
    ticket = find_ticket(data, ticket_id)
    if not ticket:
        return None
    data["tickets"] = [t for t in data["tickets"] if t["ticket_id"] != ticket_id]
    ticket["archived_at"] = now_iso()
    data["archived_tickets"].insert(0, ticket)
    log_ticket_history(ticket, "Ticket Archived", "Moved from active queue to archive")
    add_activity(data, ticket_id, "ticket_archived", f"{ticket['ticket_code']} archived")
    return ticket


def restore_ticket(data: dict[str, Any], ticket_id: int) -> dict[str, Any] | None:
    archived = data.get("archived_tickets", [])
    ticket = None
    for t in archived:
        if t["ticket_id"] == ticket_id:
            ticket = t
            break
    if not ticket:
        return None
    data["archived_tickets"] = [t for t in archived if t["ticket_id"] != ticket_id]
    ticket["archived_at"] = ""
    data["tickets"].insert(0, ticket)
    log_ticket_history(ticket, "Ticket Restored", "Returned from archive to active queue")
    add_activity(data, ticket_id, "ticket_restored", f"{ticket['ticket_code']} restored from archive")
    return ticket


def delete_ticket_forever(data: dict[str, Any], ticket_id: int) -> dict[str, Any] | None:
    ticket = find_ticket(data, ticket_id, include_archived=True)
    if not ticket:
        return None
    data["tickets"] = [t for t in data.get("tickets", []) if t["ticket_id"] != ticket_id]
    data["archived_tickets"] = [t for t in data.get("archived_tickets", []) if t["ticket_id"] != ticket_id]
    add_activity(data, ticket_id, "ticket_deleted_forever", f"{ticket['ticket_code']} permanently deleted")
    return ticket


def apply_filters(
    tickets: list[dict[str, Any]],
    search: str,
    status_filter: str,
    urgency_filter: str,
    category_filter: str,
) -> list[dict[str, Any]]:
    q = search.strip().lower()
    results: list[dict[str, Any]] = []
    for t in tickets:
        haystack = " ".join([
            t["ticket_code"],
            t["title"],
            t["requester"],
            t["category"],
            t["request_description"],
        ]).lower()
        if q and q not in haystack:
            continue
        if status_filter != "All" and t["status"] != status_filter:
            continue
        if urgency_filter != "All" and t["urgency"] != urgency_filter:
            continue
        if category_filter != "All" and t["category"] != category_filter:
            continue
        results.append(t)
    return results


def analytics(data: dict[str, Any]) -> dict[str, Any]:
    tickets = data["tickets"]
    status_counts = Counter(t["status"] for t in tickets)
    urgency_counts = Counter(t["urgency"] for t in tickets)
    category_counts = Counter(t["category"] for t in tickets)
    completed = status_counts.get("Completed", 0)
    total = len(tickets)
    open_count = total - completed
    return {
        "total": total,
        "open": open_count,
        "completed": completed,
        "status": dict(status_counts),
        "urgency": dict(urgency_counts),
        "category": dict(category_counts),
    }
