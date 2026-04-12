#!/usr/bin/env python3
"""obsidian_context: SessionStart hook — inject Obsidian roadmap + pending reminder."""

import json
import re
import sys
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

    message = (context + pending_reminder).strip()
    if message:
        print(json.dumps({"systemMessage": message}))
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
