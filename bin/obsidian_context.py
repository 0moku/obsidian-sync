#!/usr/bin/env python3
"""obsidian_context: SessionStart hook — inject Obsidian roadmap + pending reminder."""

import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

GLOBAL_CONFIG_PATH = Path.home() / ".claude" / "obsidian.json"
PENDING_PATH = Path.home() / ".claude" / "obsidian-pending.json"


def normalize_path(p: str) -> str:
    """Normalize MSYS/git-bash paths (/c/Users/...) to Windows paths on Windows."""
    if sys.platform == "win32" and re.match(r'^/[a-zA-Z]/', p):
        return p[1].upper() + ':' + p[2:].replace('/', '\\')
    return p


def load_config(cwd: str) -> dict | None:
    if not GLOBAL_CONFIG_PATH.exists():
        return None
    with open(GLOBAL_CONFIG_PATH, "r", encoding="utf-8") as f:
        global_cfg = json.load(f)
    project_cfg_path = Path(cwd) / ".claude" / "obsidian.json"
    project_cfg = {}
    if project_cfg_path.exists():
        with open(project_cfg_path, "r", encoding="utf-8") as f:
            project_cfg = json.load(f)
    return {**global_cfg, **{k: v for k, v in project_cfg.items() if v is not None}}


def _extract_v2(status_content: str) -> list[str]:
    """Parse v2 status.md format (현황 요약 table + 블로커 + 진행중 Phase)."""
    lines = []
    lines.append("## 프로젝트 로드맵 (Obsidian 기준)")

    # Frontmatter current_phase
    phase_match = re.search(r'current_phase:\s*"?([^"\n]+)"?', status_content)
    if phase_match:
        lines.append(f"현재 Phase: {phase_match.group(1)}")

    # 현황 요약 table (from header through blank line or next section)
    summary_match = re.search(r'## 현황 요약\n(.*?)(?=\n## |\Z)', status_content, re.DOTALL)
    if summary_match:
        lines.append("")
        lines.append("### 현황 요약")
        lines.append(summary_match.group(1).strip())

    # 블로커 / 최근 완료 lines
    blocker_match = re.search(r'\*\*블로커\*\*:\s*(.+)', status_content)
    if blocker_match:
        lines.append("")
        lines.append(f"블로커: {blocker_match.group(1).strip()}")
    recent_match = re.search(r'\*\*최근 완료\*\*:\s*(.+)', status_content)
    if recent_match:
        lines.append(f"최근 완료: {recent_match.group(1).strip()}")

    # Active phase: find section with 🔄 marker and count progress
    active_match = re.search(r'^(## .+🔄)\n(.*?)(?=\n## |\Z)', status_content, re.DOTALL | re.MULTILINE)
    if active_match:
        header = active_match.group(1).strip()
        body = active_match.group(2).strip()
        total = len(re.findall(r'- \[[ x]\]', body))
        done = len(re.findall(r'- \[x\]', body))
        if total > 0:
            lines.append(f"진행중: {header.replace('## ', '')} ({done}/{total})")

    return lines


def _extract_v1(status_content: str) -> list[str]:
    """Parse v1 status.md format (로드맵 + 워크플로우 상태 + 현재 세션 상태)."""
    lines = []
    lines.append("## 프로젝트 로드맵 (Obsidian 기준)")

    phase_match = re.search(r'current_phase:\s*"?([^"\n]+)"?', status_content)
    if phase_match:
        lines.append(f"현재 Phase: {phase_match.group(1)}")

    roadmap_match = re.search(r'## 로드맵\n(.*?)(?=\n## |\Z)', status_content, re.DOTALL)
    if roadmap_match:
        roadmap = roadmap_match.group(1).strip()
        total = len(re.findall(r'- \[[ x]\]', roadmap))
        done = len(re.findall(r'- \[x\]', roadmap))
        if total > 0:
            lines.append(f"진행률: {done}/{total}")
        lines.append("")
        lines.append(roadmap)

    wf_match = re.search(r'## 하이브리드 워크플로우 상태\n(.*?)(?=\n## |\Z)', status_content, re.DOTALL)
    if wf_match:
        lines.append("")
        lines.append("### 하이브리드 워크플로우 상태")
        lines.append(wf_match.group(1).strip())

    cs_match = re.search(r'## 현재 세션 상태\n(.*?)(?=\n## |\Z)', status_content, re.DOTALL)
    if cs_match:
        lines.append("")
        lines.append("### 최근 세션 상태")
        lines.append(cs_match.group(1).strip())

    return lines


def extract_context(status_content: str, decisions_content: str) -> str:
    """Build concise context string from status.md and decisions.md."""
    lines = []
    if status_content:
        # v2 detection: presence of 현황 요약 section
        if '## 현황 요약' in status_content:
            lines.extend(_extract_v2(status_content))
        else:
            lines.extend(_extract_v1(status_content))
    if decisions_content:
        decision_headers = re.findall(r'^## \d{4}-\d{2}-\d{2}: .+$', decisions_content, re.MULTILINE)
        if decision_headers:
            lines.append("")
            lines.append(f"### 최근 결정 ({min(3, len(decision_headers))}건)")
            for h in decision_headers[:3]:
                lines.append(f"- {h.replace('## ', '')}")
    return "\n".join(lines) if lines else ""


def get_pending_reminder() -> str:
    """Check for unsynced previous session and return reminder text."""
    if not PENDING_PATH.exists():
        return ""
    try:
        pending = json.loads(PENDING_PATH.read_text(encoding="utf-8"))
    except Exception:
        return ""
    backup_time = pending.get("backup_time", "")
    session_id = pending.get("session_id", "")[:8]
    if not backup_time:
        return ""
    # Format: show date/time portion
    time_display = backup_time[:19].replace("T", " ")
    return (
        f"\n---\n"
        f"## Obsidian Sync 알림\n"
        f"이전 세션({time_display} UTC, id:{session_id})이 아직 정리되지 않았습니다.\n"
        f"`/obsidian-sync`로 정리할 수 있습니다."
    )


def parse_frontmatter(content: str) -> dict:
    """Extract YAML frontmatter as a dict (simple key: value parsing)."""
    fm = {}
    match = re.match(r'^---\s*\n(.*?)\n---', content, re.DOTALL)
    if not match:
        return fm
    for line in match.group(1).split('\n'):
        kv = line.split(':', 1)
        if len(kv) == 2:
            key = kv[0].strip()
            value = kv[1].strip().strip('"').strip("'")
            fm[key] = value
    return fm


def check_vault_drift(config: dict, cwd: str) -> str:
    """Check vault task files for drift against recent git commits.

    For each task_mapping entry:
    1. Get the vault task file's `updated:` date from frontmatter
    2. Get the most recent git commit date that touched files matching the keywords
    3. If git commit date > vault updated date, the task file is stale

    Returns warning text (empty string if no drift).
    """
    task_mapping = config.get("task_mapping", {})
    if not task_mapping:
        return ""
    vault_path = Path(config.get("vault_path", ""))
    project_name = config.get("project_name", "")
    if not vault_path or not project_name:
        return ""
    tasks_dir = vault_path / "projects" / project_name / "tasks"
    stale = []
    for pattern, task_name in task_mapping.items():
        # Avoid duplicate checks for the same task file
        if any(t == task_name for t, _, _ in stale):
            continue
        # Read vault task file updated date
        task_file = tasks_dir / f"{task_name}.md"
        if not task_file.exists():
            continue
        try:
            content = task_file.read_text(encoding="utf-8")
        except Exception:
            continue
        fm = parse_frontmatter(content)
        vault_date_str = fm.get("updated", "")
        if not vault_date_str:
            continue
        try:
            vault_date = datetime.strptime(vault_date_str[:10], "%Y-%m-%d").date()
        except ValueError:
            continue
        # Find most recent git commit date for any keyword in this mapping
        keywords = [k.strip() for k in pattern.split("|")]
        latest_commit_date = None
        for keyword in keywords:
            try:
                result = subprocess.run(
                    ["git", "log", "-1", "--format=%Y-%m-%d", "--", f"*{keyword}*"],
                    capture_output=True, text=True, cwd=cwd, timeout=10
                )
                if result.returncode != 0 or not result.stdout.strip():
                    continue
                commit_date = datetime.strptime(result.stdout.strip()[:10], "%Y-%m-%d").date()
                if latest_commit_date is None or commit_date > latest_commit_date:
                    latest_commit_date = commit_date
            except Exception:
                continue
        if latest_commit_date is None:
            continue
        if latest_commit_date > vault_date:
            stale.append((task_name, vault_date_str[:10], latest_commit_date.isoformat()))
    if not stale:
        return ""
    lines = [
        "\n---",
        "## \u26a0 Vault Drift \uac10\uc9c0",
        "\ub2e4\uc74c vault task \ud30c\uc77c\uc774 \ucf54\ub4dc\ubcf4\ub2e4 \uc624\ub798\ub410\uc2b5\ub2c8\ub2e4:",
    ]
    for task_name, v_date, c_date in stale:
        lines.append(f"  - {task_name}.md (vault: {v_date}, code: {c_date})")
    lines.append("\ucee4\ubc0b \uc804\uc5d0 vault task \ud30c\uc77c\uc744 \uac31\uc2e0\ud558\uc138\uc694.")
    return "\n".join(lines)


def check_memory_staleness(config: dict, cwd: str) -> str:
    """Find stale volatile memory files.

    Scans project_*.md in the Claude memory directory.
    Only checks files with `volatile: true` in frontmatter.
    Flags files with mtime older than config["memory_stale_days"] (default 14).

    Returns warning text (empty string if no stale files).
    """
    stale_days = config.get("memory_stale_days", 14)
    # Derive memory dir from cwd
    normalized = Path(cwd).resolve()
    path_str = str(normalized)
    dir_name = path_str.replace(":", "").replace("\\", "-").replace("/", "-")
    memory_dir = Path.home() / ".claude" / "projects" / dir_name / "memory"
    if not memory_dir.exists():
        return ""
    now = datetime.now()
    stale = []
    for f in sorted(memory_dir.glob("project_*.md")):
        try:
            content = f.read_text(encoding="utf-8")
        except Exception:
            continue
        fm = parse_frontmatter(content)
        if fm.get("volatile", "").lower() != "true":
            continue
        try:
            mtime = datetime.fromtimestamp(os.path.getmtime(f))
        except Exception:
            continue
        age_days = (now - mtime).days
        if age_days > stale_days:
            stale.append((f.name, age_days))
    if not stale:
        return ""
    lines = [
        f"\n## \u26a0 Stale Memory \uac10\uc9c0",
        f"\ub2e4\uc74c volatile memory\uac00 {stale_days}\uc77c \uc774\uc0c1 \uacbd\uacfc\ud588\uc2b5\ub2c8\ub2e4:",
    ]
    for name, age in stale:
        lines.append(f"  - {name} ({age}d)")
    return "\n".join(lines)


def main():
    try:
        hook_input = json.load(sys.stdin)
    except Exception:
        sys.exit(0)
    cwd = normalize_path(hook_input.get("cwd", ""))
    cfg = load_config(cwd)
    if not cfg:
        sys.exit(0)
    vault_path = Path(cfg.get("vault_path", ""))
    project_name = cfg.get("project_name", Path(cwd).name)
    project_dir = vault_path / "projects" / project_name
    status_content = ""
    decisions_content = ""
    status_path = project_dir / "status.md"
    decisions_path = project_dir / "decisions.md"
    if status_path.exists():
        status_content = status_path.read_text(encoding="utf-8")
    if decisions_path.exists():
        decisions_content = decisions_path.read_text(encoding="utf-8")

    context = extract_context(status_content, decisions_content)
    pending_reminder = get_pending_reminder()
    drift_warning = check_vault_drift(cfg, cwd)
    memory_warning = check_memory_staleness(cfg, cwd)

    message = (context + pending_reminder + drift_warning + memory_warning).strip()
    if message:
        print(json.dumps({"systemMessage": message}))
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
