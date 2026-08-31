"""
agent_trace.py

Turns raw audit_store entries into a friendly step-by-step trace for display,
e.g.: User request -> Planner proposal -> Mandate gate -> Razorpay order.

DESIGN NOTE (why this doesn't filter by order_id):
A blocked purchase never creates an order, so there's no order_id to key a
trace on for the single most important demo case -- the mandate gate
stopping an out-of-policy purchase. Our audit events also don't carry a
shared transaction/session id linking a request to its eventual outcome.
Rather than fake that correlation with a fragile timestamp-matching hack,
this module just formats the most recent N raw events (in order) into
readable steps. Simple, and it works identically for buy and block outcomes.
"""

from datetime import datetime


def _format_planner_request(details: dict) -> str:
    return f'"{details.get("user_request", "")}"'


def _format_planner_proposal(details: dict) -> str:
    item_id = details.get("requested_item_id")
    if item_id is None:
        return f"No confident match found — {details.get('selection_reason', '')}"
    mode = details.get("planner_mode", "unknown")
    confidence = details.get("confidence", 0)
    return (
        f"Proposed {item_id} via {mode} "
        f"(confidence {confidence:.0%}) — {details.get('selection_reason', '')}"
    )


def _format_agent_decision(details: dict) -> str:
    decision = details.get("decision", "?").upper()
    return f"{decision} — {details.get('reason', '')}"


def _format_agent_explanation(details: dict) -> str:
    decision = details.get("decision", "?").upper()
    return f"{decision} — \"{details.get('explanation', '')}\""


def _format_policy_decision(details: dict) -> str:
    decision = details.get("decision")
    if decision is None:
        return "No item to evaluate (planner found no match)."
    item = details.get("item") or {}
    item_name = item.get("name", details.get("requested_item_id", "?"))
    return f"{decision.upper()} on {item_name} — {details.get('reason', '')}"


def _format_order_created(details: dict) -> str:
    order = details.get("order", {})
    order_id = order.get("id", "?")
    amount = order.get("amount", 0) / 100
    note = order.get("note", "")
    suffix = " (mock)" if note.startswith("MOCK ORDER") else ""
    return f"{order_id} created for ₹{amount:,.2f}{suffix}"


def _format_order_blocked(details: dict) -> str:
    return f"Blocked — {details.get('reason', '')}"


# Maps event_type -> (friendly action label, formatter function, icon)
EVENT_FORMATTERS = {
    "planner_request": ("User request", _format_planner_request, "🗣️"),
    "planner_proposal": ("Planner proposal", _format_planner_proposal, "🧠"),
    "agent_decision": ("Mandate gate", _format_agent_decision, "⚖️"),
    "agent_explanation": ("Agent explanation", _format_agent_explanation, "💬"),
    "policy_decision": ("Mandate gate (via planner)", _format_policy_decision, "⚖️"),
    "order_created": ("Razorpay order", _format_order_created, "💳"),
    "order_blocked": ("Order blocked", _format_order_blocked, "🚫"),
}


def build_trace(audit_events: list[dict]) -> list[dict]:
    """
    Convert a list of raw audit_store entries (oldest-first, same order as
    GET /audit) into a numbered, human-readable trace.

    Unknown event types are still included (with their raw event_type as
    the label) rather than silently dropped -- a trace that hides events
    is worse than one with an ugly label for something new.
    """
    trace = []
    for i, event in enumerate(audit_events, start=1):
        event_type = event.get("event_type", "unknown")
        details = event.get("details", {})

        label, formatter, icon = EVENT_FORMATTERS.get(
            event_type, (event_type, lambda d: str(d), "•")
        )

        try:
            details_text = formatter(details)
        except Exception:
            # Never let a malformed/unexpected event shape break the whole
            # trace -- show something rather than crashing the tab.
            details_text = str(details)

        trace.append(
            {
                "step": i,
                "icon": icon,
                "action": label,
                "details": details_text,
                "timestamp": event.get("timestamp", ""),
                "event_type": event_type,
            }
        )
    return trace
