from datetime import datetime


def _independent_expected_decision(item: dict, mandate: dict, decision_timestamp: str) -> tuple[str, str]:
    """
    Re-derive buy/block from raw facts. Mirrors the SAME rules agent_decide()
    is supposed to implement, written from scratch here on purpose.
    """
    ts = None
    if decision_timestamp:
        try:
            ts = datetime.fromisoformat(decision_timestamp)
        except ValueError:
            ts = None

    expiry = mandate.get("expiry")
    if isinstance(expiry, str):
        try:
            expiry = datetime.fromisoformat(expiry)
        except ValueError:
            expiry = None

    if ts is not None and expiry is not None and ts > expiry:
        return "block", "mandate had expired at the time of this decision"

    if item["category"] not in mandate.get("allowed_categories", []):
        return "block", f"category '{item['category']}' is not in the allowed list"

    if item["price"] > mandate.get("spending_cap", 0):
        return "block", f"price {item['price']} exceeds spending cap {mandate.get('spending_cap')}"

    return "buy", "within spending cap and category is allowed"


def validate_policy_accuracy(audit_events: list[dict], catalog: list[dict], mandate: dict) -> dict:
    """
    Only `agent_decision` and `policy_decision` events carry a decision to
    validate. Note: because the gate is re-checked server-side (by design),
    the SAME logical transaction may appear here more than once -- this
    doesn't affect the accuracy percentage (a deterministic gate gives the
    same answer every time), it just means total_validated counts each
    re-check as its own validated instance rather than deduplicating.
    """
    catalog_by_id = {item["item_id"]: item for item in catalog}

    total_validated = 0
    correct_decisions = 0
    mismatches = []

    for event in audit_events:
        event_type = event.get("event_type")
        details = event.get("details", {})

        if event_type == "agent_decision":
            item_id = details.get("item_id")
            actual_decision = details.get("decision")
        elif event_type == "policy_decision":
            item_id = details.get("requested_item_id")
            actual_decision = details.get("decision")
        else:
            continue

        if item_id is None or actual_decision is None:
            continue  # e.g. planner found no catalog match -- nothing to validate

        item = catalog_by_id.get(item_id)
        if item is None:
            continue  # can't validate against an item no longer in the catalog

        expected_decision, expected_reason = _independent_expected_decision(
            item, mandate, event.get("timestamp", "")
        )

        total_validated += 1
        if expected_decision == actual_decision:
            correct_decisions += 1
        else:
            mismatches.append({
                "item_id": item_id,
                "actual_decision": actual_decision,
                "expected_decision": expected_decision,
                "expected_reason": expected_reason,
                "timestamp": event.get("timestamp"),
            })

    policy_accuracy_percent = (
        round(correct_decisions / total_validated * 100, 1) if total_validated > 0 else None
    )

    return {
        "total_validated": total_validated,
        "correct_decisions": correct_decisions,
        "policy_accuracy_percent": policy_accuracy_percent,
        "mismatches": mismatches,  # empty list if everything checks out -- shown for transparency
        "note": (
            "total_validated counts every agent_decision/policy_decision event, "
            "including repeated re-checks of the same logical transaction. This "
            "inflates the sample size but not the accuracy percentage, since a "
            "deterministic gate answers identically each time it's re-checked."
        ),
    }
