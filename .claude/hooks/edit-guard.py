#!/usr/bin/env python3
"""PostToolUse(Edit|Write), wiki/dogmas.md: no TODOs in source (exit 2 feeds stderr back);
a touched test file is flagged so the change can name the wiki claim it traces to."""

import json
import os
import pathlib
import re
import sys

MARKER = re.compile(r"\b(TODO|FIXME|XXX)\b")

try:
    path = pathlib.Path(json.load(sys.stdin)["tool_input"]["file_path"])
except (KeyError, TypeError, ValueError):
    sys.exit(0)

root = pathlib.Path(os.environ.get("CLAUDE_PROJECT_DIR", ".")).resolve()
if not (path.suffix == ".py" and path.is_file() and path.resolve().is_relative_to(root)):
    sys.exit(0)

hits = [
    f"{path}:{n}" for n, line in enumerate(path.read_text().splitlines(), 1) if MARKER.search(line)
]
if hits and ".claude" not in path.parts:
    print(
        "No TODOs (wiki/dogmas.md#code): do the work now, or run it through /intake onto "
        "BOARD.md. Remove: " + ", ".join(hits[:5]),
        file=sys.stderr,
    )
    sys.exit(2)

if "tests" in path.parts or path.name.startswith("test_") or path.name == "conftest.py":
    context = (
        f"Test file touched: {path}. Be able to name the wiki claim it traces to. Weakening or "
        "removing an assertion is an egress finding unless a wiki-declared behaviour "
        "changed in the same diff."
    )
    print(
        json.dumps(
            {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": context}}
        )
    )
