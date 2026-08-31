import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TARGETS = [ROOT / "main.py", ROOT / "frontend" / "app.py"]

HELPER = (
    "\n\ndef utcnow():\n"
    "    from datetime import datetime as _dt, timezone as _tz\n"
    "    return _dt.now(_tz.utc).replace(tzinfo=None)\n"
)

for path in TARGETS:
    if not path.exists():
        print("skip (missing):", path)
        continue

    text = path.read_text(encoding="utf-8")
    original = text

    text = text.replace("use_container_width=True", "width='stretch'")
    text = text.replace("use_container_width=False", "width='content'")
    text = re.sub(r"datetime\.utcnow\(\)", "utcnow()", text)

    if "def utcnow():" not in text and "utcnow()" in text:
        lines = text.split("\n")
        insert_at = 0
        for i, line in enumerate(lines):
            if line.startswith("import ") or line.startswith("from "):
                insert_at = i + 1
        lines.insert(insert_at, HELPER)
        text = "\n".join(lines)

    if text != original:
        path.with_suffix(path.suffix + ".bak").write_text(original, encoding="utf-8")
        path.write_text(text, encoding="utf-8")
        print("updated:", path.name, "(backup saved as .bak)")
    else:
        print("no change:", path.name)