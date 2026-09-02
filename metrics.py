DECISION_PREVIEW_EVENT_TYPES = ("agent_decision", "policy_decision", "agent_explanation")


def calculate_metrics(audit_events: list[dict]) -> dict:
    order_events = [
        e for e in audit_events if e.get("event_type") in ("order_created", "order_blocked")
    ]

    buy_count = sum(1 for e in order_events if e["event_type"] == "order_created")
    block_count = sum(1 for e in order_events if e["event_type"] == "order_blocked")
    total_purchase_attempts = buy_count + block_count

    block_rate_percent = (
        round(block_count / total_purchase_attempts * 100, 1)
        if total_purchase_attempts > 0 else None
    )

    # Latency: measured for the deterministic GATE's own computation only
    # (not any LLM calls before/after it -- those are separate and already
    # have their own timeout budget). Captured at the point of decision in
    # main.py's agent_decide(); only present on events logged after that
    # instrumentation was added.
    latencies = [
        e["details"]["latency_ms"]
        for e in audit_events
        if e.get("event_type") in ("agent_decision", "policy_decision")
        and isinstance(e.get("details", {}).get("latency_ms"), (int, float))
    ]
    avg_gate_latency_ms = round(sum(latencies) / len(latencies), 3) if latencies else None

    decision_preview_count = sum(
        1 for e in audit_events if e.get("event_type") in DECISION_PREVIEW_EVENT_TYPES
    )

    return {
        "total_purchase_attempts": total_purchase_attempts,
        "buy_count": buy_count,
        "block_count": block_count,
        "block_rate_percent": block_rate_percent,
        "avg_gate_latency_ms": avg_gate_latency_ms,
        "latency_sample_size": len(latencies),
        "decision_preview_count": decision_preview_count,
        "methodology_note": (
            "buy_count/block_count/block_rate_percent are counted from "
            "order_created/order_blocked events only (actual purchase "
            "attempts), to avoid double-counting one transaction across "
            "its preview and re-check events. decision_preview_count is "
            "reported separately and is NOT included in the rate above."
        ),
    }
