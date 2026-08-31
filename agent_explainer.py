"""
agent_explainer.py

Turns a decision + reason into a friendlier, more conversational explanation.

IMPORTANT: this module NEVER decides buy/block. It only rephrases a decision
that's already been made by the deterministic mandate gate in main.py. That
separation is deliberate and worth keeping in the pitch: the LLM (if used at
all) only touches the "judgment-light" task of wording, never the
"judgment-critical" task of authorizing spend. If the LLM is unavailable,
slow, or returns something odd, we fall back to a rule-based template --
the explanation always shows up, it just isn't always LLM-flavored.

Optional LLM path uses a local Ollama server (https://ollama.com), which
runs small open models entirely on your machine -- no API key, no cost, no
data leaving your laptop. If Ollama isn't installed/running, this module
degrades to pure rule-based text with zero errors surfaced to the caller.
"""

import requests

OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "qwen2.5:0.5b"  # small, fast, fine for one-sentence rephrasing
OLLAMA_TIMEOUT_SECONDS = 1  # fail fast -- this is a "nice to have", not critical path


def _rule_based_explanation(item_name: str, price: float, category: str,
                             decision: str, reason: str, mandate: dict) -> str:
    """
    Deterministic, template-based explanation. This is the guaranteed
    fallback -- always available, always correct, since it's built directly
    from the same facts the gate used to decide.
    """
    cap = mandate.get("spending_cap")

    if decision == "buy":
        return (
            f"I recommend this purchase. The {item_name} costs ₹{price:,.2f}, "
            f"which is within your spending cap of ₹{cap:,.2f}, and "
            f"'{category}' is an allowed category."
        )

    # decision == "block" -- reuse the backend's precise reason, just framed
    # more conversationally. We don't try to re-derive WHY it was blocked
    # here; the gate already computed that and put it in `reason`, so we
    # simply front it with a friendlier opening line.
    return f"I can't recommend this purchase. {reason}"


def _try_ollama_explanation(item_name: str, price: float, category: str,
                             decision: str, reason: str, mandate: dict) -> str | None:
    """
    Attempt to get a more natural rephrasing from a local Ollama model.

    Returns the generated text on success, or None on ANY failure (model not
    installed, Ollama not running, timeout, unexpected response shape, etc.)
    so the caller can fall back cleanly. This function is intentionally
    forgiving -- an explanation feature should never take down a demo.
    """
    prompt = (
        "You are rephrasing a purchase decision into ONE short, friendly sentence. "
        "Do not change the facts. Do not add new numbers. Do not contradict the decision.\n\n"
        f"Decision: {decision}\n"
        f"Item: {item_name}\n"
        f"Price: ₹{price:,.2f}\n"
        f"Category: {category}\n"
        f"Spending cap: ₹{mandate.get('spending_cap'):,.2f}\n"
        f"Allowed categories: {', '.join(mandate.get('allowed_categories', []))}\n"
        f"Reason (must stay factually consistent with this): {reason}\n\n"
        "Write only the rephrased sentence, nothing else."
    )

    try:
        response = requests.post(
            OLLAMA_URL,
            json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
            timeout=OLLAMA_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        data = response.json()
        text = data.get("response", "").strip()

        # Basic sanity checks -- if the model returned something empty or
        # suspiciously long (rambling instead of one sentence), don't trust
        # it; fall back instead of showing something odd in a demo.
        if not text or len(text) > 400:
            return None
        return text

    except Exception:
        # Covers: Ollama not running, model not pulled, network hiccup,
        # malformed JSON, timeout -- all treated the same way: fall back.
        return None


def generate_explanation(item_name: str, price: float, category: str,
                          decision: str, reason: str, mandate: dict) -> str:
    """
    Public entry point. Tries the LLM first (if reachable), falls back to
    the rule-based template on any failure. The rule-based version is
    always computed so there's zero latency cost to having a fallback ready.
    """
    fallback = _rule_based_explanation(item_name, price, category, decision, reason, mandate)

    llm_text = _try_ollama_explanation(item_name, price, category, decision, reason, mandate)
    if llm_text:
        return llm_text

    return fallback
