from __future__ import annotations

from datetime import datetime

import altair as alt
import pandas as pd
import streamlit as st

from services.openai_service import generate_instructions
from utils.storage import DATA_FILE, load_data, save_data
from utils.ticket_utils import (
    STATUS_VALUES,
    URGENCY_VALUES,
    add_activity,
    analytics,
    apply_filters,
    archive_ticket,
    create_ticket,
    delete_ticket_forever,
    find_ticket,
    instruction_cache_key,
    log_ticket_history,
    restore_ticket,
)

st.set_page_config(page_title="Liv's Data Triage System", page_icon="🎫", layout="wide")


@st.cache_data
def _format_iso(iso_value: str) -> str:
    if not iso_value:
        return "-"
    try:
        return datetime.fromisoformat(iso_value.replace("Z", "+00:00")).strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return iso_value


def apply_professional_theme() -> None:
    st.markdown(
        """
        <style>
            .stApp {
                background: #F8FAFC;
            }
            [data-testid="stSidebar"] {
                background: #111827;
            }
            [data-testid="stSidebar"] * {
                color: #E2E8F0 !important;
            }
            .stMetric {
                background: #FFFFFF;
                border: 1px solid #E5E7EB;
                border-radius: 12px;
                padding: 0.4rem 0.7rem;
            }
            .stButton>button[kind="primary"] {
                background: #111827;
                border: 1px solid #111827;
                border-radius: 10px;
                color: white;
            }
            .stButton>button[kind="secondary"] {
                border-radius: 10px;
            }
            .stDataFrame, div[data-baseweb="select"], div[data-baseweb="input"] {
                border-radius: 10px;
            }
            .block-container {
                padding-top: 1.2rem;
            }
            .section-card {
                background: #FFFFFF;
                border: 1px solid #E5E7EB;
                border-radius: 14px;
                padding: 0.8rem 1rem;
                margin: 0.4rem 0 1rem 0;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


def initialize_state() -> None:
    if "data" not in st.session_state:
        st.session_state.data = load_data()
    st.session_state.data.setdefault("archived_tickets", [])
    if "selected_ticket_id" not in st.session_state:
        st.session_state.selected_ticket_id = None
    if "selected_archived_ticket_id" not in st.session_state:
        st.session_state.selected_archived_ticket_id = None


def persist() -> None:
    save_data(st.session_state.data)


def render_dashboard() -> None:
    st.title("Liv's Data Triage System")
    st.caption("Clean, focused workflow for queue triage and operational insights.")

    stats = analytics(st.session_state.data)
    completion_rate = (stats["completed"] / stats["total"] * 100) if stats["total"] else 0
    active_rate = (stats["open"] / stats["total"] * 100) if stats["total"] else 0

    c1, c2, c3 = st.columns(3)
    c1.metric("Total Tickets", stats["total"])
    c2.metric("Open Tickets", stats["open"], f"{active_rate:.1f}% active")
    c3.metric("Completed Tickets", stats["completed"], f"{completion_rate:.1f}% completion")

    overview_tab, analytics_tab = st.tabs(["Overview", "Dynamic Analytics"])

    with overview_tab:
        st.subheader("Snapshot")
        c4, c5, c6 = st.columns(3)
        render_breakdown(c4, "By Status", stats["status"], stats["total"], "status")
        render_breakdown(c5, "By Urgency", stats["urgency"], stats["total"], "urgency")
        render_breakdown(c6, "By Category", stats["category"], stats["total"], "category")

    with analytics_tab:
        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.subheader("Dynamic Chart Studio")
        c7, c8, c9, c10 = st.columns(4)
        metric_choice = c7.selectbox("Locate chart by metric", ["Status", "Urgency", "Category"])
        chart_type = c8.selectbox("Chart Type", ["Bar", "Donut"])
        sort_order = c9.selectbox("Sort", ["Descending by Count", "Alphabetical"])
        top_n = c10.slider("Top Items", min_value=3, max_value=12, value=8)

        counts_map = {
            "Status": stats["status"],
            "Urgency": stats["urgency"],
            "Category": stats["category"],
        }
        selected_counts = counts_map[metric_choice]

        with st.spinner("Refreshing chart..."):
            st.altair_chart(
                make_dynamic_chart(selected_counts, metric_choice, chart_type, sort_order, top_n),
                use_container_width=True,
            )
        st.markdown("</div>", unsafe_allow_html=True)


def make_count_chart(counts: dict[str, int], label: str) -> alt.Chart:
    labels = list(counts.keys())
    values = list(counts.values())
    chart_data = pd.DataFrame({label: labels, "count": values})
    lower_label = label.lower()
    color_scale = alt.Scale(scheme="tableau10")
    if lower_label == "urgency":
        color_scale = alt.Scale(
            domain=["Low", "Medium", "High", "Critical"],
            range=["#2E7D32", "#F9A825", "#C62828", "#000000"],
        )

    return (
        alt.Chart(chart_data)
        .mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4)
        .encode(
            x=alt.X(f"{label}:N", title=label, sort=labels),
            y=alt.Y("count:Q", title="Count"),
            color=alt.Color(f"{label}:N", scale=color_scale, legend=None),
            tooltip=[alt.Tooltip(f"{label}:N"), alt.Tooltip("count:Q", title="Count")],
        )
        .properties(height=260)
    )


def make_dynamic_chart(counts: dict[str, int], label: str, chart_type: str, sort_order: str, top_n: int) -> alt.Chart:
    items = list(counts.items())
    if sort_order == "Descending by Count":
        items = sorted(items, key=lambda item: item[1], reverse=True)
    else:
        items = sorted(items, key=lambda item: item[0].lower())
    items = items[:top_n]
    chart_data = pd.DataFrame(items, columns=[label, "count"])

    if chart_type == "Donut":
        return (
            alt.Chart(chart_data)
            .mark_arc(innerRadius=60)
            .encode(
                theta=alt.Theta("count:Q"),
                color=alt.Color(f"{label}:N"),
                tooltip=[alt.Tooltip(f"{label}:N"), alt.Tooltip("count:Q", title="Count")],
            )
            .properties(height=320)
        )

    return (
        alt.Chart(chart_data)
        .mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4)
        .encode(
            x=alt.X(f"{label}:N", sort=[item[0] for item in items]),
            y=alt.Y("count:Q", title="Count"),
            color=alt.Color(f"{label}:N", legend=None),
            tooltip=[alt.Tooltip(f"{label}:N"), alt.Tooltip("count:Q", title="Count")],
        )
        .properties(height=320)
    )


def _palette_for_breakdown(kind: str, labels: list[str]) -> dict[str, str]:
    if kind == "urgency":
        return {
            "Low": "#2E7D32",
            "Medium": "#F9A825",
            "High": "#C62828",
            "Critical": "#000000",
        }
    if kind == "status":
        return {
            "New": "#4C78A8",
            "In Progress": "#F58518",
            "Waiting": "#E45756",
            "Completed": "#72B7B2",
        }
    tableau10 = [
        "#4C78A8",
        "#F58518",
        "#E45756",
        "#72B7B2",
        "#54A24B",
        "#EECA3B",
        "#B279A2",
        "#FF9DA6",
        "#9D755D",
        "#BAB0AC",
    ]
    return {label: tableau10[idx % len(tableau10)] for idx, label in enumerate(labels)}


def render_breakdown(container, title: str, counts: dict[str, int], total: int, kind: str) -> None:
    container.write(f"**{title}**")
    if not counts:
        container.caption("No data available.")
        return

    sorted_counts = sorted(counts.items(), key=lambda item: item[1], reverse=True)
    color_map = _palette_for_breakdown(kind, [label for label, _ in sorted_counts])

    for label, value in sorted_counts:
        percentage = (value / total * 100) if total else 0
        container.markdown(f"**{label}** · {value} ({percentage:.1f}%)")
        container.markdown(
            f"""
            <div style="background:#E5E7EB;height:10px;border-radius:999px;margin:6px 0 14px 0;">
                <div style="background:{color_map.get(label, '#4C78A8')};width:{min(percentage, 100):.1f}%;height:10px;border-radius:999px;"></div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_ticket_queue(filtered_tickets: list[dict], selector_key: str, state_key: str) -> None:
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
    selected = st.selectbox("Open Ticket", options, key=selector_key)
    selected_code = selected.split(" | ")[0]
    for t in filtered_tickets:
        if t["ticket_code"] == selected_code:
            st.session_state[state_key] = t["ticket_id"]
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


def render_ticket_detail(ticket_id: int | None, archived: bool = False) -> None:
    if ticket_id is None:
        st.info("Select a ticket from the queue to view details.")
        return

    ticket = find_ticket(st.session_state.data, ticket_id, include_archived=archived)
    if not ticket:
        st.warning("Selected ticket no longer exists.")
        return

    st.subheader(f"Ticket Detail — {ticket['ticket_code']}")
    st.markdown(f"### {ticket['title']}")
    st.caption(f"Requester: {ticket['requester']} | Department: {ticket['department']} | Created: {_format_iso(ticket['created_at'])}")

    c1, c2 = st.columns(2)
    with c1:
        new_status = st.selectbox(
            "Status",
            STATUS_VALUES,
            index=STATUS_VALUES.index(ticket["status"]),
            disabled=archived,
            key=f"status_{ticket['ticket_id']}_{'archive' if archived else 'active'}",
        )
    with c2:
        new_urgency = st.selectbox(
            "Urgency",
            URGENCY_VALUES,
            index=URGENCY_VALUES.index(ticket["urgency"]),
            disabled=archived,
            key=f"urgency_{ticket['ticket_id']}_{'archive' if archived else 'active'}",
        )

    if not archived and new_status != ticket["status"]:
        old = ticket["status"]
        ticket["status"] = new_status
        if new_status == "Completed" and not ticket["completed_at"]:
            ticket["completed_at"] = datetime.utcnow().isoformat()
        log_ticket_history(ticket, "Status Updated", f"{old} -> {new_status}")
        add_activity(st.session_state.data, ticket["ticket_id"], "status_changed", f"{ticket['ticket_code']}: {old} -> {new_status}")
        persist()
        st.success("Status updated.")

    if not archived and new_urgency != ticket["urgency"]:
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
    note = st.text_area("Add note", key=f"note_{ticket['ticket_id']}_{'archive' if archived else 'active'}")
    if st.button("Add Note", key=f"add_note_{ticket['ticket_id']}_{'archive' if archived else 'active'}", disabled=archived):
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
    if st.button(
        "Generate Instructions",
        type="primary",
        key=f"gen_ai_{ticket['ticket_id']}_{'archive' if archived else 'active'}",
        disabled=archived,
    ):
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

    st.divider()
    action_cols = st.columns([1, 1, 2])
    if archived:
        if action_cols[0].button("Restore Ticket", key=f"restore_{ticket['ticket_id']}"):
            restored = restore_ticket(st.session_state.data, ticket["ticket_id"])
            if restored:
                st.session_state.selected_archived_ticket_id = None
                st.session_state.selected_ticket_id = restored["ticket_id"]
                persist()
                st.success(f"{restored['ticket_code']} restored to active queue.")
                st.rerun()
        if action_cols[1].button("Delete Forever", key=f"delete_archived_{ticket['ticket_id']}"):
            removed = delete_ticket_forever(st.session_state.data, ticket["ticket_id"])
            if removed:
                st.session_state.selected_archived_ticket_id = None
                persist()
                st.success(f"{removed['ticket_code']} deleted permanently.")
                st.rerun()
    else:
        if action_cols[0].button("Archive Completed Ticket", key=f"archive_{ticket['ticket_id']}"):
            if ticket["status"] != "Completed":
                st.warning("Only completed tickets can be archived.")
            else:
                archived_ticket = archive_ticket(st.session_state.data, ticket["ticket_id"])
                if archived_ticket:
                    st.session_state.selected_ticket_id = None
                    st.session_state.selected_archived_ticket_id = archived_ticket["ticket_id"]
                    persist()
                    st.success(f"{archived_ticket['ticket_code']} moved to archive.")
                    st.rerun()
        if action_cols[1].button("Delete Forever", key=f"delete_active_{ticket['ticket_id']}"):
            removed = delete_ticket_forever(st.session_state.data, ticket["ticket_id"])
            if removed:
                st.session_state.selected_ticket_id = None
                persist()
                st.success(f"{removed['ticket_code']} deleted permanently.")
                st.rerun()


def render_ticket_queue_page() -> None:
    st.title("Ticket Queue")
    s1, s2, s3, s4 = st.columns(4)
    search = s1.text_input("Search")
    status_filter = s2.selectbox("Status", ["All"] + STATUS_VALUES)
    urgency_filter = s3.selectbox("Urgency", ["All"] + URGENCY_VALUES)
    all_categories = sorted({t["category"] for t in st.session_state.data["tickets"]})
    category_filter = s4.selectbox("Category", ["All"] + all_categories)

    filtered = apply_filters(st.session_state.data["tickets"], search, status_filter, urgency_filter, category_filter)

    filtered = [t for t in filtered if t.get("status") != "Completed"]
    render_ticket_queue(filtered, "ticket_selector_active", "selected_ticket_id")
    st.divider()
    render_ticket_detail(st.session_state.selected_ticket_id)


def render_completed_queue_page() -> None:
    st.title("Completed Queue")
    st.caption("Review completed tickets from the active queue.")

    active_completed = [t for t in st.session_state.data["tickets"] if t.get("status") == "Completed"]
    st.subheader("Active Completed Tickets")
    s1, s2, s3 = st.columns(3)
    search = s1.text_input("Search Completed Tickets")
    urgency_filter = s2.selectbox("Urgency", ["All"] + URGENCY_VALUES, key="completed_urgency_filter")
    all_categories = sorted({t["category"] for t in active_completed})
    category_filter = s3.selectbox("Category", ["All"] + all_categories, key="completed_category_filter")
    completed_filtered = apply_filters(active_completed, search, "Completed", urgency_filter, category_filter)
    render_ticket_queue(completed_filtered, "ticket_selector_completed", "selected_ticket_id")
    st.divider()
    render_ticket_detail(st.session_state.selected_ticket_id)


@st.dialog("Clear all data?")
def confirm_clear_all_data() -> None:
    st.error("Warning: this action is irreversible and will permanently delete all tickets, archive data, and activity history.")
    c1, c2 = st.columns(2)
    if c1.button("Yes, clear everything", type="primary"):
        st.session_state.data = {
            "tickets": [],
            "archived_tickets": [],
            "activity_log": [],
            "next_ticket_id": 1,
            "ai_instruction_cache": {},
        }
        st.session_state.selected_ticket_id = None
        st.session_state.selected_archived_ticket_id = None
        persist()
        st.success("All app data has been cleared.")
        st.rerun()
    if c2.button("No, keep data"):
        st.rerun()


def render_ticket_intake_page() -> None:
    st.title("Create Ticket Intake")
    render_create_ticket_form()
    st.caption("Use the sidebar to navigate to the Ticket Queue page to review and manage created tickets.")


def render_settings_page() -> None:
    st.title("Settings")
    st.info("Set OPENAI_API_KEY in your environment to enable AI instruction generation.")
    st.caption(f"Persistent data file: `{DATA_FILE}`")
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

    st.divider()
    st.subheader("Data Management")
    st.caption("Use with caution.")
    if st.button("Clear All Data", type="secondary"):
        confirm_clear_all_data()


def main() -> None:
    initialize_state()
    apply_professional_theme()
    st.sidebar.title("Navigation")
    page = st.sidebar.radio("Go to", ["Dashboard", "Ticket Queue", "Create Ticket Intake", "Completed Queue", "Settings"])

    if page == "Dashboard":
        render_dashboard()
    elif page == "Ticket Queue":
        render_ticket_queue_page()
    elif page == "Create Ticket Intake":
        render_ticket_intake_page()
    elif page == "Completed Queue":
        render_completed_queue_page()
    else:
        render_settings_page()


if __name__ == "__main__":
    main()
