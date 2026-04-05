#!/usr/bin/env python3
"""obsidian-sync: Claude Code SessionEnd hook → Obsidian vault."""

import json
import os
import sys
import re
import time
import logging
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_PATH = Path.home() / ".claude" / "obsidian-sync.log"

def get_logger():
    logger = logging.getLogger("obsidian-sync")
    logger.setLevel(logging.DEBUG)
    if not logger.handlers:
        fh = logging.FileHandler(LOG_PATH, encoding="utf-8")
        fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(fh)
    return logger

log = get_logger()

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
GLOBAL_CONFIG_PATH = Path.home() / ".claude" / "obsidian.json"

def load_config(cwd: str) -> dict | None:
    """Load merged global + project config. Returns None if not configured."""
    if not GLOBAL_CONFIG_PATH.exists():
        return None
    with open(GLOBAL_CONFIG_PATH, "r", encoding="utf-8") as f:
        global_cfg = json.load(f)
    project_cfg_path = Path(cwd) / ".claude" / "obsidian.json"
    project_cfg = {}
    if project_cfg_path.exists():
        with open(project_cfg_path, "r", encoding="utf-8") as f:
            project_cfg = json.load(f)
    cfg = {**global_cfg, **{k: v for k, v in project_cfg.items() if v is not None}}
    return cfg

# ---------------------------------------------------------------------------
# Transcript Parsing
# ---------------------------------------------------------------------------
def parse_transcript(path: str) -> list[dict]:
    """Parse JSONL transcript into structured messages."""
    messages = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            entry_type = entry.get("type")
            if entry_type not in ("user", "assistant"):
                continue
            msg = {
                "type": entry_type,
                "timestamp": entry.get("timestamp"),
                "session_id": entry.get("sessionId"),
                "cwd": entry.get("cwd"),
                "git_branch": entry.get("gitBranch"),
            }
            raw_message = entry.get("message", {})
            raw_content = raw_message.get("content")
            if entry_type == "assistant":
                msg["model"] = raw_message.get("model")
                msg["content"] = raw_content if isinstance(raw_content, list) else [{"type": "text", "text": str(raw_content)}]
            elif entry_type == "user":
                if isinstance(raw_content, str):
                    msg["content"] = raw_content
                elif isinstance(raw_content, list):
                    msg["content"] = raw_content
                else:
                    msg["content"] = str(raw_content)
            messages.append(msg)
    return messages


def compress_transcript(messages: list[dict], max_chars: int = 500000) -> list[dict]:
    """Compress transcript for API: remove thinking, summarize tool results."""
    compressed = []
    for msg in messages:
        m = {**msg}
        if m["type"] == "assistant" and isinstance(m.get("content"), list):
            new_content = []
            for block in m["content"]:
                if block.get("type") == "thinking":
                    continue
                if block.get("type") == "tool_use":
                    simplified = {"type": "tool_use", "name": block.get("name", "")}
                    tool_input = block.get("input", {})
                    if "file_path" in tool_input:
                        simplified["file_path"] = tool_input["file_path"]
                    if "command" in tool_input:
                        cmd = tool_input["command"]
                        simplified["command"] = cmd[:200] if len(cmd) > 200 else cmd
                    if "pattern" in tool_input:
                        simplified["pattern"] = tool_input["pattern"]
                    new_content.append(simplified)
                else:
                    new_content.append(block)
            m["content"] = new_content
        elif m["type"] == "user" and isinstance(m.get("content"), list):
            new_content = []
            for block in m["content"]:
                if block.get("type") == "tool_result":
                    content = block.get("content", "")
                    if isinstance(content, str) and len(content) > 300:
                        content = content[:150] + f"\n... ({len(content)} chars total)"
                    new_content.append({"type": "tool_result", "tool_use_id": block.get("tool_use_id"), "content": content})
                else:
                    new_content.append(block)
            m["content"] = new_content
        compressed.append(m)
    text = json.dumps(compressed, ensure_ascii=False)
    while len(text) > max_chars and len(compressed) > 4:
        compressed.pop(0)
        text = json.dumps(compressed, ensure_ascii=False)
    return compressed
