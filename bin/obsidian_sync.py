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


# ---------------------------------------------------------------------------
# File naming
# ---------------------------------------------------------------------------
def sanitize_filename(name: str) -> str:
    """Replace unsafe chars with hyphens, collapse spaces."""
    name = re.sub(r'[/\\:*?"<>|]', '-', name)
    name = re.sub(r'\s+', '-', name.strip())
    name = re.sub(r'-+', '-', name).strip('-')
    return name


def get_session_filename(sessions_dir: str, date: str, title: str) -> str:
    """Generate unique session filename, adding _N suffix on collision."""
    base = f"{date}_{sanitize_filename(title)}"
    candidate = f"{base}.md"
    if not Path(sessions_dir, candidate).exists():
        return candidate
    n = 2
    while Path(sessions_dir, f"{base}_{n}.md").exists():
        n += 1
    return f"{base}_{n}.md"


# ---------------------------------------------------------------------------
# Markdown generators
# ---------------------------------------------------------------------------
def generate_session_log(api_response: dict, meta: dict) -> str:
    """Generate session log markdown from API response + metadata."""
    s = api_response["session"]
    st = api_response["status"]
    decisions = api_response.get("decisions", [])
    lines = [
        "---",
        f"date: {meta['date']}",
        f"project: {meta['project']}",
        f"duration_min: {meta['duration_min']}",
        f"model: {meta['model']}",
        f"tags: [{', '.join(s.get('tags', []))}]",
    ]
    if s.get("workflow"):
        lines.append(f"workflow: [{', '.join(s['workflow'])}]")
    if s.get("task_size"):
        lines.append(f"task_size: {s['task_size']}")
    lines += [
        f"session_id: {meta['session_id']}",
        "ai_summary: true",
        "---",
        f"# {s['title']}",
        "",
        "## 요약",
        s.get("summary", ""),
        "",
        "## 주요 활동",
    ]
    for act in s.get("key_activities", []):
        lines.append(f"- {act}")
    lines += ["", "## 변경된 파일"]
    for f in s.get("files_changed", []):
        lines.append(f"- `{f}`")
    if decisions:
        lines += ["", "## 결정 사항"]
        for d in decisions:
            lines += [
                f"### {d['title']}",
                f"- **결정**: {d['decision']}",
            ]
            if d.get("alternatives"):
                lines.append(f"- **대안**: {d['alternatives']}")
            lines.append(f"- **근거**: {d['rationale']}")
    lines += ["", "## 상태"]
    for item in st.get("completed", []):
        lines.append(f"- ✅ {item}")
    for item in st.get("in_progress", []):
        lines.append(f"- 🔄 {item}")
    for item in st.get("blockers", []):
        lines.append(f"- ❌ {item}")
    for item in st.get("next_steps", []):
        lines.append(f"- 🔲 {item}")
    return "\n".join(lines) + "\n"


def generate_decision_entry(decision: dict, date: str, session_stem: str) -> str:
    """Generate a single decision entry for decisions.md."""
    lines = [
        f"## {date}: {decision['title']}",
        f"- **결정**: {decision['decision']}",
    ]
    if decision.get("alternatives"):
        lines.append(f"- **대안**: {decision['alternatives']}")
    lines += [
        f"- **근거**: {decision['rationale']}",
        f"- **세션**: [[{session_stem}]]",
    ]
    return "\n".join(lines)


def update_decisions_file(filepath: Path, new_entries: list[str], project: str):
    """Append new decisions to decisions.md (newest on top)."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if filepath.exists():
        content = filepath.read_text(encoding="utf-8")
        content = re.sub(r'updated: \d{4}-\d{2}-\d{2}', f'updated: {today}', content)
        marker = "# 결정 로그\n"
        idx = content.find(marker)
        if idx >= 0:
            insert_pos = idx + len(marker)
            insert_text = "\n" + "\n\n".join(new_entries) + "\n"
            content = content[:insert_pos] + insert_text + content[insert_pos:]
        else:
            content += "\n" + "\n\n".join(new_entries) + "\n"
    else:
        content = f"---\nproject: {project}\nupdated: {today}\n---\n# 결정 로그\n\n"
        content += "\n\n".join(new_entries) + "\n"
    filepath.write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# Context gathering
# ---------------------------------------------------------------------------
def gather_context_sources(cwd: str, cfg: dict) -> str:
    """Gather content from context sources (specs, plans, gstack, etc)."""
    parts = []
    gstack_slug = cfg.get("gstack_slug")
    if cfg.get("include_gstack") and gstack_slug:
        gstack_dir = Path.home() / ".gstack" / "projects" / gstack_slug
        ceo_dir = gstack_dir / "ceo-plans"
        if ceo_dir.exists():
            ceo_files = sorted(ceo_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
            if ceo_files:
                content = ceo_files[0].read_text(encoding="utf-8")[:3000]
                parts.append(f"## CEO Plan (latest): {ceo_files[0].name}\n{content}")
        eng_files = sorted(gstack_dir.glob("*-eng-review-*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
        if eng_files:
            content = eng_files[0].read_text(encoding="utf-8")[:3000]
            parts.append(f"## Eng Review (latest): {eng_files[0].name}\n{content}")
        learnings_path = gstack_dir / "learnings.jsonl"
        if learnings_path.exists():
            lines = learnings_path.read_text(encoding="utf-8").strip().split("\n")
            last_10 = lines[-10:] if len(lines) > 10 else lines
            parts.append(f"## Learnings (last {len(last_10)})\n" + "\n".join(last_10))
    for source in cfg.get("context_sources", []):
        src_path = Path(cwd) / source["path"]
        if src_path.is_file():
            content = src_path.read_text(encoding="utf-8")[:3000]
            parts.append(f"## {source['type']}: {source['path']}\n{content}")
        elif src_path.is_dir():
            files = sorted(src_path.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)[:3]
            for fp in files:
                content = fp.read_text(encoding="utf-8")[:2000]
                parts.append(f"## {source['type']}: {fp.name}\n{content}")
    return "\n\n---\n\n".join(parts) if parts else ""


def get_git_diff_stat(cwd: str) -> str:
    """Run git diff --stat in the project directory."""
    import subprocess
    try:
        result = subprocess.run(["git", "diff", "--stat", "HEAD"], cwd=cwd, capture_output=True, text=True, timeout=5)
        return result.stdout.strip() or "(no changes)"
    except Exception:
        return "(git diff unavailable)"


def get_existing_status(vault_project_dir: Path) -> str:
    """Read existing _status.md if it exists."""
    status_path = vault_project_dir / "_status.md"
    if status_path.exists():
        return status_path.read_text(encoding="utf-8")
    return ""


# ---------------------------------------------------------------------------
# Claude API
# ---------------------------------------------------------------------------
def call_claude_api(compressed_messages: list[dict], existing_status: str, git_diff: str, context_sources: str, cfg: dict) -> dict | None:
    """Call Claude API with compressed transcript and context. Returns parsed JSON."""
    try:
        import anthropic
    except ImportError:
        log.error("anthropic SDK not installed. Run: pip install anthropic")
        return None
    skill_dir = Path(__file__).resolve().parent.parent
    prompt_template = (skill_dir / "prompts" / "summarize.txt").read_text(encoding="utf-8")
    roadmap_rules = (skill_dir / "prompts" / "roadmap_rules.txt").read_text(encoding="utf-8")
    prompt_template = prompt_template.replace("{ROADMAP_RULES}", roadmap_rules)
    transcript_text = json.dumps(compressed_messages, ensure_ascii=False, indent=None)
    user_parts = [f"## TRANSCRIPT\n{transcript_text}"]
    if existing_status:
        user_parts.append(f"## EXISTING_STATUS\n{existing_status}")
    user_parts.append(f"## GIT_DIFF\n{git_diff}")
    if context_sources:
        user_parts.append(f"## CONTEXT_SOURCES\n{context_sources}")
    user_message = "\n\n".join(user_parts)
    model = cfg.get("model", "claude-haiku-4-5-20251001")
    timeout = cfg.get("api_timeout", 30)
    client = anthropic.Anthropic()
    for attempt in range(2):
        try:
            response = client.messages.create(
                model=model, max_tokens=8192, system=prompt_template,
                messages=[{"role": "user", "content": user_message}], timeout=timeout,
            )
            text = response.content[0].text.strip()
            if text.startswith("```"):
                text = re.sub(r'^```\w*\n?', '', text)
                text = re.sub(r'\n?```$', '', text)
            return json.loads(text)
        except json.JSONDecodeError as e:
            log.error(f"API response not valid JSON (attempt {attempt+1}): {e}")
            if attempt == 0: time.sleep(3)
        except Exception as e:
            log.error(f"API call failed (attempt {attempt+1}): {e}")
            if attempt == 0: time.sleep(3)
    return None
