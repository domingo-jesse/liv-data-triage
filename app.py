from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st

from services.openai_service import generate_instructions
from utils.storage import load_data, save_data
from utils.ticket_utils import (
    STATUS_VALUES,
    URGENCY_VALUES,
    add_activity,
    analytics,
    apply_filters,
    create_ticket,
    find_ticket,
    instruction_cache_key,
    log_ticket_history,
)

st.set_page_config(page_title="AI Ticketing System", page_icon="🎫", layout="wide")


@st.cache_data
def _format_iso(iso_value: str) -> str:
    if not iso_value:
        return "-"
    try:
        return datetime.fromisoformat(iso_value.replace("Z", "+00:00")).strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return iso_value


def initialize_state() -> None:
    if "data" not in st.session_state:
        st.session_state.data = load_data()
    if "selected_ticket_id" not in st.session_state:
        st.session_state.selected_ticket_id = None


def persist() -> None:
    save_data(st.session_state.data)


def render_dashboard() -> None:
    st.title("Dashboard")

    stats = analytics(st.session_state.data)
    completion_rate = (stats["completed"] / stats["total"] * 100) if stats["total"] else 0
    active_rate = (stats["open"] / stats["total"] * 100) if stats["total"] else 0

    c1, c2, c3 = st.columns(3)
    c1.metric("Total Tickets", stats["total"])
    c2.metric("Open Tickets", stats["open"], f"{active_rate:.1f}% active")
    c3.metric("Completed Tickets", stats["completed"], f"{completion_rate:.1f}% completion")

    overview_tab, analytics_tab = st.tabs(["Overview", "Analytics"])

    with overview_tab:
        st.subheader("Snapshot")
        c4, c5, c6 = st.columns(3)
        render_breakdown(c4, "By Status", stats["status"], stats["total"])
        render_breakdown(c5, "By Urgency", stats["urgency"], stats["total"])
        render_breakdown(c6, "By Category", stats["category"], stats["total"])

    with analytics_tab:
        with st.spinner("Loading analytics visuals..."):
            st.subheader("Counts by Status")
            st.bar_chart(pd.DataFrame.from_dict(stats["status"], orient="index", columns=["count"]))
            st.subheader("Counts by Urgency")
            st.bar_chart(pd.DataFrame.from_dict(stats["urgency"], orient="index", columns=["count"]))
            st.subheader("Counts by Category")
            st.bar_chart(pd.DataFrame.from_dict(stats["category"], orient="index", columns=["count"]))


def render_breakdown(container, title: str, counts: dict[str, int], total: int) -> None:
    container.write(f"**{title}**")
    if not counts:
        container.caption("No data available.")
        return

    for label, value in sorted(counts.items(), key=lambda item: item[1], reverse=True):
        percentage = (value / total * 100) if total else 0
        container.markdown(f"**{label}** · {value} ({percentage:.1f}%)")
        container.progress(min(percentage / 100, 1.0))


def render_ticket_queue(filtered_tickets: list[dict]) -> None:
    rows = [
        {
            "ID": t["ticket_code"],
            "Title": t["title"],
            "Requester": t["requester"],
            "Urgency": t["urgency"],
            "Status": t["status"],
            "Category": t["category"],
            "Created": _format_iso(t["created_at"]),
        }
        for t in filtered_tickets
    ]
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    options = [f"{t['ticket_code']} | {t['title']}" for t in filtered_tickets]
    if not options:
        st.info("No tickets found for current filters.")
        return
    selected = st.selectbox("Open Ticket", options, key="ticket_selector")
    selected_code = selected.split(" | ")[0]
    for t in filtered_tickets:
        if t["ticket_code"] == selected_code:
            st.session_state.selected_ticket_id = t["ticket_id"]
            break


def render_create_ticket_form() -> None:
    st.subheader("Create Ticket")
    with st.form("create_ticket_form", clear_on_submit=True):
        title = st.text_input("Ticket Title")
        c1, c2 = st.columns(2)
        requester = c1.text_input("Requester Name")
        department = c2.text_input("Department / Team")
        c3, c4 = st.columns(2)
        urgency = c3.selectbox("Urgency", URGENCY_VALUES, index=1)
        category = c4.text_input("Category", value="General")
        request_description = st.text_area("Request Description", height=120)
        desired_outcome = st.text_area("Desired Outcome", height=80)
        submitted = st.form_submit_button("Create Ticket")

    if submitted:
        if not title.strip() or not requester.strip() or not request_description.strip():
            st.error("Title, requester, and request description are required.")
            return
        ticket = create_ticket(
            st.session_state.data,
            {
                "title": title.strip(),
                "requester": requester.strip(),
                "department": department.strip() or "N/A",
                "urgency": urgency,
                "category": category.strip() or "General",
                "request_description": request_description.strip(),
                "desired_outcome": desired_outcome.strip() or "N/A",
            },
        )
        cache_key = instruction_cache_key(ticket)
        cached_instructions = st.session_state.data["ai_instruction_cache"].get(cache_key, "")
        if cached_instructions:
            ticket["ai_instructions"] = cached_instructions
            log_ticket_history(ticket, "AI Instructions Loaded", "Loaded from saved instruction cache")
            add_activity(
                st.session_state.data,
                ticket["ticket_id"],
                "ai_instructions_loaded",
                f"{ticket['ticket_code']}: AI instructions loaded from cache",
            )
        st.session_state.selected_ticket_id = ticket["ticket_id"]
        persist()
        if cached_instructions:
            st.success(f"Ticket {ticket['ticket_code']} created with saved AI work instructions.")
        else:
            st.success(f"Ticket {ticket['ticket_code']} created.")


def render_ticket_detail() -> None:
    ticket_id = st.session_state.selected_ticket_id
    if ticket_id is None:
        st.info("Select a ticket from the queue to view details.")
        return

    ticket = find_ticket(st.session_state.data, ticket_id)
    if not ticket:
        st.warning("Selected ticket no longer exists.")
        return

    st.subheader(f"Ticket Detail — {ticket['ticket_code']}")
    st.markdown(f"### {ticket['title']}")
    st.caption(f"Requester: {ticket['requester']} | Department: {ticket['department']} | Created: {_format_iso(ticket['created_at'])}")

    c1, c2 = st.columns(2)
    with c1:
        new_status = st.selectbox("Status", STATUS_VALUES, index=STATUS_VALUES.index(ticket["status"]))
    with c2:
        new_urgency = st.selectbox("Urgency", URGENCY_VALUES, index=URGENCY_VALUES.index(ticket["urgency"]))

    if new_status != ticket["status"]:
        old = ticket["status"]
        ticket["status"] = new_status
        if new_status == "Completed" and not ticket["completed_at"]:
            ticket["completed_at"] = datetime.utcnow().isoformat()
        log_ticket_history(ticket, "Status Updated", f"{old} -> {new_status}")
        add_activity(st.session_state.data, ticket["ticket_id"], "status_changed", f"{ticket['ticket_code']}: {old} -> {new_status}")
        persist()
        st.success("Status updated.")

    if new_urgency != ticket["urgency"]:
        old = ticket["urgency"]
        ticket["urgency"] = new_urgency
        log_ticket_history(ticket, "Urgency Updated", f"{old} -> {new_urgency}")
        add_activity(st.session_state.data, ticket["ticket_id"], "urgency_changed", f"{ticket['ticket_code']}: {old} -> {new_urgency}")
        persist()
        st.success("Urgency updated.")

    st.write("**Request Description**")
    st.write(ticket["request_description"])
    st.write("**Desired Outcome**")
    st.write(ticket["desired_outcome"])

    st.write("**Notes / Comments**")
    note = st.text_area("Add note", key=f"note_{ticket['ticket_id']}")
    if st.button("Add Note", key=f"add_note_{ticket['ticket_id']}"):
        if note.strip():
            ticket["notes"].insert(0, {"timestamp": datetime.utcnow().isoformat(), "text": note.strip()})
            log_ticket_history(ticket, "Note Added", note.strip())
            add_activity(st.session_state.data, ticket["ticket_id"], "note_added", f"{ticket['ticket_code']}: note added")
            persist()
            st.success("Note added.")
        else:
            st.warning("Note is empty.")

    for n in ticket["notes"][:5]:
        st.caption(f"{_format_iso(n['timestamp'])} — {n['text']}")

    st.divider()
    st.write("### AI Work Instructions")
    cache_key = instruction_cache_key(ticket)
    if st.button("Generate Instructions", type="primary", key=f"gen_ai_{ticket['ticket_id']}"):
        with st.spinner("Generating AI instructions..."):
            cached = st.session_state.data["ai_instruction_cache"].get(cache_key, "")
            text = cached or generate_instructions(ticket)
            ticket["ai_instructions"] = text
            st.session_state.data["ai_instruction_cache"][cache_key] = text
            if cached:
                log_ticket_history(ticket, "AI Instructions Loaded", "Loaded from saved instruction cache")
                add_activity(
                    st.session_state.data,
                    ticket["ticket_id"],
                    "ai_instructions_loaded",
                    f"{ticket['ticket_code']}: AI instructions loaded from cache",
                )
            else:
                log_ticket_history(ticket, "AI Instructions Generated", "Instructions generated/refreshed")
                add_activity(
                    st.session_state.data,
                    ticket["ticket_id"],
                    "ai_instructions_generated",
                    f"{ticket['ticket_code']}: AI instructions generated",
                )
            persist()
            st.success("Instructions ready and saved.")

    if ticket["ai_instructions"]:
        st.markdown(ticket["ai_instructions"])
    else:
        st.info("No AI instructions yet. Click Generate Instructions.")

    with st.expander("Activity Log"):
        for item in ticket["history"]:
            st.write(f"- {_format_iso(item['timestamp'])} | **{item['action']}** — {item['detail']}")


def render_ticket_queue_page() -> None:
    st.title("Ticket Queue")
    s1, s2, s3, s4 = st.columns(4)
    search = s1.text_input("Search")
    status_filter = s2.selectbox("Status", ["All"] + STATUS_VALUES)
    urgency_filter = s3.selectbox("Urgency", ["All"] + URGENCY_VALUES)
    all_categories = sorted({t["category"] for t in st.session_state.data["tickets"]})
    category_filter = s4.selectbox("Category", ["All"] + all_categories)

    filtered = apply_filters(st.session_state.data["tickets"], search, status_filter, urgency_filter, category_filter)

    render_ticket_queue(filtered)
    st.divider()
    render_ticket_detail()


def render_ticket_intake_page() -> None:
    st.title("Create Ticket Intake")
    render_create_ticket_form()
    st.caption("Use the sidebar to navigate to the Ticket Queue page to review and manage created tickets.")


def render_settings_page() -> None:
    st.title("Settings")
    st.info("Set OPENAI_API_KEY in your environment to enable AI instruction generation.")
    if st.button("Load Demo Ticket"):
        ticket = create_ticket(
            st.session_state.data,
            {
                "title": "Merge Excel Reports",
                "requester": "Jesse",
                "department": "Operations",
                "urgency": "Medium",
                "category": "Excel / Reporting",
                "request_description": "Take two Excel sheets, match member IDs, and pull authorization status into the final file using VLOOKUP.",
                "desired_outcome": "Final merged report with status column completed",
            },
        )
        st.session_state.selected_ticket_id = ticket["ticket_id"]
        persist()
        st.success("Demo ticket loaded.")


def main() -> None:
    initialize_state()
    st.sidebar.title("Navigation")
    page = st.sidebar.radio("Go to", ["Dashboard", "Ticket Queue", "Create Ticket Intake", "Settings"])

    if page == "Dashboard":
        render_dashboard()
    elif page == "Ticket Queue":
        render_ticket_queue_page()
    elif page == "Create Ticket Intake":
        render_ticket_intake_page()
    else:
        render_settings_page()


if __name__ == "__main__":
    main()
