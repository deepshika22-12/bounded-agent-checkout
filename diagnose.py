import importlib
import socket
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

print("Python:", sys.version.split()[0])
print("Folder:", ROOT)
print()

print("--- Files ---")
for name in [
    "main.py",
    "config.py",
    "razorpay_client.py",
    "agent_explainer.py",
    "agent_trace.py",
    "audit_store.py",
    "metrics.py",
    "policy_simulator.py",
    "shopping_planner.py",
    "adversarial_tests.py",
    "frontend/app.py",
]:
    print(("OK   " if (ROOT / name).exists() else "MISSING "), name)

print()
print("--- Packages ---")
for pkg in ["fastapi", "uvicorn", "pydantic", "streamlit", "requests"]:
    try:
        importlib.import_module(pkg)
        print("OK   ", pkg)
    except Exception as exc:
        print("FAIL ", pkg, "->", exc)

print()
print("--- Importing main.py ---")
try:
    import main
    routes = sorted(
        r.path for r in main.app.routes if hasattr(r, "path")
    )
    print("main.py imported successfully")
    print("Routes:", ", ".join(routes))
except Exception:
    print("main.py FAILED to import. This is why the backend never starts:")
    traceback.print_exc()

print()
print("--- Port 8000 ---")
sock = socket.socket()
sock.settimeout(1)
busy = sock.connect_ex(("127.0.0.1", 8000)) == 0
sock.close()
print("Something is already listening on 8000" if busy else "Port 8000 is free")