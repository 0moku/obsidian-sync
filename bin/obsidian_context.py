#!/usr/bin/env python3
"""obsidian_context: SessionStart hook — inject Obsidian roadmap into Claude Code."""

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

GLOBAL_CONFIG_PATH = Path.home() / ".claude" / "obsidian.json"


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


def extract_context(status_content: str, decisions_content: str) -> str:
    """Build concise context string from _status.md and decisions.md."""
    lines = []
    if status_content:
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
    if decisions_content:
        decision_headers = re.findall(r'^## \d{4}-\d{2}-\d{2}: .+$', decisions_content, re.MULTILINE)
        if decision_headers:
            lines.append("")
            lines.append(f"### 최근 결정 ({min(3, len(decision_headers))}건)")
            for h in decision_headers[:3]:
                lines.append(f"- {h.replace('## ', '')}")
    return "\n".join(lines) if lines else ""


def main():
    try:
        hook_input = json.load(sys.stdin)
    except Exception:
        sys.exit(0)
    cwd = hook_input.get("cwd", "")
    cfg = load_config(cwd)
    if not cfg:
        sys.exit(0)
    vault_path = Path(cfg.get("vault_path", ""))
    project_name = cfg.get("project_name", Path(cwd).name)
    project_dir = vault_path / "projects" / project_name
    status_content = ""
    decisions_content = ""
    status_path = project_dir / "_status.md"
    decisions_path = project_dir / "decisions.md"
    if status_path.exists():
        status_content = status_path.read_text(encoding="utf-8")
    if decisions_path.exists():
        decisions_content = decisions_path.read_text(encoding="utf-8")
    if not status_content and not decisions_content:
        sys.exit(0)
    context = extract_context(status_content, decisions_content)
    if context:
        print(json.dumps({"systemMessage": context}))
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
