"""
Fixes the false "Backend not reachable" error in the Agent demo tab.

Root cause: frontend/app.py used one global TIMEOUT_SECONDS = 5 for every
request, including POST /agent/plan, which waits on the local Ollama model.
Ollama's cold start alone takes 5-30 seconds, so that request timed out, and
backend_post reported Timeout and ConnectionError with the same label.

Run once from D:\\bounded_agent_checkout:
    python patch_agent_demo.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
APP = ROOT / "frontend" / "app.py"

if not APP.exists():
    print(f"ERROR: not found: {APP}")
    sys.exit(1)

raw = APP.read_text(encoding="utf-8", newline="")
crlf = "\r\n" in raw
text = raw.replace("\r\n", "\n")

EDITS = []

# ---------------------------------------------------------------- 1. timeouts
EDITS.append((
    'BASE_URL = "http://127.0.0.1:8000"\nTIMEOUT_SECONDS = 5\n',
    'BASE_URL = "http://127.0.0.1:8000"\n'
    '\n'
    '# Fast, purely local endpoints: catalog, mandate, metrics, audit, trace.\n'
    'TIMEOUT_SECONDS = 8\n'
    '\n'
    '# POST /agent/plan invokes the local Ollama model. A cold start alone\n'
    '# takes 5-30 seconds, and CPU inference on a 3B model adds several more,\n'
    '# so this must be generous or the UI will report a false failure.\n'
    'PLANNER_TIMEOUT_SECONDS = 180\n',
))

# ------------------------------------------------------- 2. backend_get split
EDITS.append((
    'def backend_get(path: str):\n'
    '    try:\n'
    '        response = requests.get(f"{BASE_URL}{path}", timeout=TIMEOUT_SECONDS)\n'
    '        response.raise_for_status()\n'
    '        return response.json(), None\n'
    '    except (ConnectionError, Timeout):\n'
    '        return None, "unreachable"\n',

    'def backend_get(path: str, timeout: float = TIMEOUT_SECONDS):\n'
    '    try:\n'
    '        response = requests.get(f"{BASE_URL}{path}", timeout=timeout)\n'
    '        response.raise_for_status()\n'
    '        return response.json(), None\n'
    '    except ConnectionError:\n'
    '        return None, "unreachable"\n'
    '    except Timeout:\n'
    '        return None, "timeout"\n',
))

# ------------------------------------------------------ 3. backend_post split
EDITS.append((
    'def backend_post(\n'
    '    path: str,\n'
    '    json_body: dict | None = None,\n'
    '    headers: dict | None = None,\n'
    '):\n'
    '    try:\n'
    '        response = requests.post(\n'
    '            f"{BASE_URL}{path}",\n'
    '            json=json_body,\n'
    '            headers=headers,\n'
    '            timeout=TIMEOUT_SECONDS,\n'
    '        )\n'
    '        response.raise_for_status()\n'
    '        return response.json(), None\n'
    '    except (ConnectionError, Timeout):\n'
    '        return None, "unreachable"\n',

    'def backend_post(\n'
    '    path: str,\n'
    '    json_body: dict | None = None,\n'
    '    headers: dict | None = None,\n'
    '    timeout: float = TIMEOUT_SECONDS,\n'
    '):\n'
    '    try:\n'
    '        response = requests.post(\n'
    '            f"{BASE_URL}{path}",\n'
    '            json=json_body,\n'
    '            headers=headers,\n'
    '            timeout=timeout,\n'
    '        )\n'
    '        response.raise_for_status()\n'
    '        return response.json(), None\n'
    '    except ConnectionError:\n'
    '        return None, "unreachable"\n'
    '    except Timeout:\n'
    '        return None, "timeout"\n',
))

# ------------------------------------------------- 4. honest timeout messages
EDITS.append((
    'def show_backend_unreachable():\n'
    '    st.error(\n'
    '        f"Backend not reachable at `{BASE_URL}`. "\n'
    '        "Start the API with `uvicorn main:app --reload`, then refresh the page."\n'
    '    )\n',

    'def show_backend_unreachable():\n'
    '    st.error(\n'
    '        f"Backend not reachable at `{BASE_URL}`. "\n'
    '        "Start both services with `python run_all.py`, then refresh the page."\n'
    '    )\n'
    '\n'
    '\n'
    'def show_planner_timeout():\n'
    '    st.error(\n'
    '        f"The backend is running, but the planner did not answer within "\n'
    '        f"{PLANNER_TIMEOUT_SECONDS} seconds."\n'
    '    )\n'
    '    st.caption(\n'
    '        "This is a slow local model, not a connection problem. Check the "\n'
    '        "backend terminal for a line starting with `[planner]`. To bypass "\n'
    '        "the model entirely, restart with `$env:OLLAMA_ENABLED = \\"0\\"` "\n'
    '        "and the deterministic rule-based planner will answer instantly."\n'
    '    )\n',
))

# ------------------------------------------------------- 5. the plan call site
EDITS.append((
    '                plan_result, plan_error = backend_post(\n'
    '                    f"/agent/plan?request={quote(nl_request)}"\n'
    '                )\n'
    '\n'
    '                if plan_error == "unreachable":\n'
    '                    show_backend_unreachable()\n'
    '                elif plan_error and not plan_result:\n'
    '                    st.warning(f"Could not create a plan: {plan_error}")\n',

    '                with st.spinner(\n'
    '                    "The planner is reasoning about your request. "\n'
    '                    "A cold local model can take up to a minute."\n'
    '                ):\n'
    '                    plan_result, plan_error = backend_post(\n'
    '                        f"/agent/plan?request={quote(nl_request)}",\n'
    '                        timeout=PLANNER_TIMEOUT_SECONDS,\n'
    '                    )\n'
    '\n'
    '                if plan_error == "unreachable":\n'
    '                    show_backend_unreachable()\n'
    '                elif plan_error == "timeout":\n'
    '                    show_planner_timeout()\n'
    '                elif plan_error and not plan_result:\n'
    '                    st.warning(f"Could not create a plan: {plan_error}")\n',
))

applied = 0
for index, (old, new) in enumerate(EDITS, start=1):
    count = text.count(old)
    if count == 1:
        text = text.replace(old, new)
        applied += 1
        print(f"edit {index}: applied")
    elif count == 0:
        if new.split("\n")[0] in text:
            print(f"edit {index}: already applied, skipping")
        else:
            print(f"edit {index}: PATTERN NOT FOUND - not applied")
    else:
        print(f"edit {index}: pattern found {count} times, too ambiguous - skipped")

if applied == 0:
    print("\nNothing changed. File left untouched.")
    sys.exit(0)

backup = APP.with_suffix(".py.prepatch")
backup.write_text(raw, encoding="utf-8", newline="")

if crlf:
    text = text.replace("\n", "\r\n")

APP.write_text(text, encoding="utf-8", newline="")

print(f"\n{applied} of {len(EDITS)} edits applied to {APP}")
print(f"Backup written to {backup.name}")
print("\nNow restart:  python run_all.py")