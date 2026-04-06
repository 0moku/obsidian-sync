#!/usr/bin/env python3
"""obsidian_backup: PostToolUse hook — save pending session info for later sync."""

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

PENDING_PATH = Path.home() / ".claude" / "obsidian-pending.json"
GLOBAL_CONFIG_PATH = Path.home() / ".claude" / "obsidian.json"


def normalize_path(p: str) -> str:
    if sys.platform == "win32" and re.match(r'^/[a-zA-Z]/', p):
        return p[1].upper() + ':' + p[2:].replace('/', '\\')
    return p


def main():
    try:
        hook_input = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    transcript_path = normalize_path(hook_input.get("transcript_path", ""))
    session_id = hook_input.get("session_id", "")
    cwd = normalize_path(hook_input.get("cwd", ""))

    if not transcript_path or not session_id:
        sys.exit(0)

    if not GLOBAL_CONFIG_PATH.exists():
        sys.exit(0)
    project_cfg = Path(cwd) / ".claude" / "obsidian.json"
    if not project_cfg.exists():
        sys.exit(0)

    PENDING_PATH.write_text(json.dumps({
        "transcript_path": transcript_path,
        "session_id": session_id,
        "cwd": cwd,
        "backup_time": datetime.now(timezone.utc).isoformat(),
    }, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
