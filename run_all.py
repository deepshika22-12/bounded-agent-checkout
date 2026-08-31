"""
Starts the Bounded Agent Checkout backend and frontend together.

- frees ports 8000 and 8501 first, so a stale process cannot cause
  "Only one usage of each socket address"
- waits for GET /health before launching Streamlit
- preloads the Ollama model with keep_alive so the first planner
  request in the UI does not pay the cold-start cost
- shuts both processes down on Ctrl+C
"""

import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PY = sys.executable
BACKEND_PORT = 8000
FRONTEND_PORT = 8501

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
OLLAMA_ENABLED = os.getenv("OLLAMA_ENABLED", "1") == "1"
OLLAMA_KEEP_ALIVE = os.getenv("OLLAMA_KEEP_ALIVE", "-1")


def free_port(port: int) -> None:
    script = (
        f"Get-NetTCPConnection -LocalPort {port} -State Listen "
        "-ErrorAction SilentlyContinue | "
        "Select-Object -ExpandProperty OwningProcess | "
        "Sort-Object -Unique | "
        "ForEach-Object { Stop-Process -Id $_ -Force "
        "-ErrorAction SilentlyContinue }"
    )
    subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        capture_output=True,
    )


def warm_up_ollama() -> None:
    if not OLLAMA_ENABLED:
        print("Ollama disabled (OLLAMA_ENABLED=0). Planner will be rule-based.")
        return

    try:
        with urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=2) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except Exception:
        print(f"Ollama not reachable at {OLLAMA_URL}. Planner will be rule-based.")
        return

    names = [m.get("name", "") for m in payload.get("models", [])]
    base = OLLAMA_MODEL.split(":")[0]
    present = OLLAMA_MODEL in names or any(n.split(":")[0] == base for n in names)

    if not present:
        print(f"Model '{OLLAMA_MODEL}' is NOT pulled. Installed: {names or 'none'}")
        print(f"   Run this, and let it finish:  ollama pull {OLLAMA_MODEL}")
        print("   Until then the planner falls back to rule-based.")
        return

    print(f"Preloading '{OLLAMA_MODEL}' into memory (first time can take a minute) ...")
    body = json.dumps({
        "model": OLLAMA_MODEL,
        "keep_alive": OLLAMA_KEEP_ALIVE,
    }).encode("utf-8")
    request_obj = urllib.request.Request(
        f"{OLLAMA_URL}/api/generate",
        data=body,
        headers={"Content-Type": "application/json"},
    )

    started = time.time()
    try:
        with urllib.request.urlopen(request_obj, timeout=300):
            pass
        print(f"Model resident in memory after {time.time() - started:.1f}s.")
    except Exception as exc:
        print(f"Preload failed ({exc}). The first UI request will be slower.")


def main() -> int:
    for port in (BACKEND_PORT, FRONTEND_PORT):
        print(f"Freeing port {port} ...")
        free_port(port)
    time.sleep(1)

    warm_up_ollama()

    backend = subprocess.Popen(
        [PY, "-m", "uvicorn", "main:app",
         "--host", "127.0.0.1", "--port", str(BACKEND_PORT)],
        cwd=ROOT,
    )

    print(f"Waiting for backend on http://127.0.0.1:{BACKEND_PORT} ...")

    ready = False
    for _ in range(60):
        if backend.poll() is not None:
            print("Backend exited during startup. Scroll up for the traceback.")
            return 1
        try:
            url = f"http://127.0.0.1:{BACKEND_PORT}/health"
            with urllib.request.urlopen(url, timeout=1) as response:
                print("Backend ready:", response.read().decode())
                ready = True
                break
        except Exception:
            time.sleep(0.5)

    if not ready:
        print("Backend never became ready. Run: python diagnose.py")
        backend.terminate()
        return 1

    frontend = subprocess.Popen(
        [PY, "-m", "streamlit", "run", "frontend/app.py",
         "--server.port", str(FRONTEND_PORT),
         "--server.address", "127.0.0.1",
         "--server.headless", "true"],
        cwd=ROOT,
    )

    print(f"\n  Open  http://127.0.0.1:{FRONTEND_PORT}")
    print("  Press Ctrl+C once to stop both.\n")

    try:
        frontend.wait()
    except KeyboardInterrupt:
        print("\nShutting down ...")
    finally:
        for proc in (frontend, backend):
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
        print("Stopped.")

    return 0


if __name__ == "__main__":
    sys.exit(main())