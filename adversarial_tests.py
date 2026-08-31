"""
adversarial_tests.py

Persists results of DELIBERATE adversarial test attempts (see
run_adversarial_tests.py) -- crafted attacks against the planner/gate
boundary, run under controlled conditions. This is explicitly NOT inferred
from ordinary user traffic: a user typing a request the planner can't match
("something completely nonexistent") is not an "attack," it's just a miss,
and conflating the two would make the security story dishonest in the
opposite direction (inflating how much resistance was actually tested).
"""

import json
from datetime import datetime
from pathlib import Path

ADVERSARIAL_RESULTS_PATH = Path(__file__).resolve().parent / "adversarial_results.json"

_results: list[dict] = []


def _load_from_disk() -> list[dict]:
    if not ADVERSARIAL_RESULTS_PATH.exists():
        return []
    try:
        with open(ADVERSARIAL_RESULTS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        print(f"[adversarial_tests] WARNING: {ADVERSARIAL_RESULTS_PATH} has invalid JSON, starting fresh.")
        return []


def _save_to_disk() -> None:
    try:
        with open(ADVERSARIAL_RESULTS_PATH, "w", encoding="utf-8") as f:
            json.dump(_results, f, indent=2, default=str)
    except OSError as e:
        print(f"[adversarial_tests] WARNING: could not write results to disk: {e}")


_results = _load_from_disk()


def record_adversarial_test(test_name: str, result: str, detail: str = "") -> None:
    """
    result must be "blocked" (the attack was successfully prevented) or
    "succeeded" (the attack got through -- this would be a real bug worth
    surfacing immediately, not something to hide).
    """
    if result not in ("blocked", "succeeded"):
        raise ValueError(f"result must be 'blocked' or 'succeeded', got: {result!r}")

    _results.append({
        "test_name": test_name,
        "result": result,
        "detail": detail,
        "timestamp": datetime.utcnow().isoformat(),
    })
    _save_to_disk()


def get_adversarial_stats() -> dict:
    total_attempts = len(_results)
    blocked_count = sum(1 for r in _results if r["result"] == "blocked")
    success_count = sum(1 for r in _results if r["result"] == "succeeded")

    attack_success_rate_percent = (
        round(success_count / total_attempts * 100, 1) if total_attempts > 0 else None
    )

    return {
        "total_attempts": total_attempts,
        "blocked_count": blocked_count,
        "success_count": success_count,
        "attack_success_rate_percent": attack_success_rate_percent,
        "tests": _results,
    }
