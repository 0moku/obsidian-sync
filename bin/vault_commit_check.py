#!/usr/bin/env python3
"""vault_commit_check: PreToolUse(Bash) hook — warn if vault task files are stale on git commit."""

import json
import os
import re
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

GLOBAL_CONFIG_PATH = Path.home() / ".claude" / "obsidian.json"


def normalize_path(p: str) -> str:
    """Normalize MSYS/git-bash paths (/c/Users/...) to Windows paths on Windows."""
    if sys.platform == "win32" and re.match(r'^/[a-zA-Z]/', p):
        return p[1].upper() + ':' + p[2:].replace('/', '\\')
    return p


def is_git_commit(command: str) -> bool:
    """Return True if the command is a git commit (not just any git command)."""
    # Strip leading whitespace and handle various forms:
    # git commit, git -C ... commit, git commit -m "...", etc.
    cmd = command.strip()
    # Direct: git commit ...
    if re.match(r'^git\s+commit\b', cmd):
        return True
    # With git flags before subcommand: git -C /path commit ...
    if re.match(r'^git\s+(-\S+\s+\S+\s+)*commit\b', cmd):
        return True
    return False


def load_project_config(cwd: str) -> dict | None:
    """Load project obsidian.json from cwd/.claude/obsidian.json."""
    project_cfg_path = Path(cwd) / ".claude" / "obsidian.json"
    if not project_cfg_path.exists():
        return None
    with open(project_cfg_path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_global_config() -> dict | None:
    """Load global obsidian.json from ~/.claude/obsidian.json."""
    if not GLOBAL_CONFIG_PATH.exists():
        return None
    with open(GLOBAL_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def get_staged_files(cwd: str) -> list[str]:
    """Get list of staged file paths via git diff --cached."""
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            capture_output=True, text=True, cwd=cwd, timeout=10
        )
        if result.returncode != 0:
            return []
        return [f.strip() for f in result.stdout.strip().split('\n') if f.strip()]
    except Exception:
        return []


def match_tasks(staged_files: list[str], task_mapping: dict) -> set[str]:
    """Match staged file paths against task_mapping keywords, return set of task names."""
    matched = set()
    # Combine all staged file paths into one search string
    files_text = "\n".join(staged_files).lower()
    for pattern, task_name in task_mapping.items():
        # pattern uses | as OR separator
        keywords = [k.strip() for k in pattern.split("|")]
        for keyword in keywords:
            if keyword.lower() in files_text:
                matched.add(task_name)
                break
    return matched


def parse_frontmatter(content: str) -> dict:
    """Extract YAML frontmatter as a dict (simple key: value parsing)."""
    fm = {}
    match = re.match(r'^---\s*\n(.*?)\n---', content, re.DOTALL)
    if not match:
        return fm
    for line in match.group(1).split('\n'):
        # Simple key: value parsing
        kv = line.split(':', 1)
        if len(kv) == 2:
            key = kv[0].strip()
            value = kv[1].strip().strip('"').strip("'")
            fm[key] = value
    return fm


def check_vault_staleness(
    matched_tasks: set[str],
    vault_path: str,
    project_name: str,
    today: str
) -> list[str]:
    """Check if vault task files are stale (updated date != today). Return warning lines."""
    warnings = []
    tasks_dir = Path(vault_path) / "projects" / project_name / "tasks"
    for task_name in sorted(matched_tasks):
        task_file = tasks_dir / f"{task_name}.md"
        if not task_file.exists():
            warnings.append(f"  - {task_name}: vault task file not found ({task_file})")
            continue
        try:
            content = task_file.read_text(encoding="utf-8")
        except Exception:
            continue
        fm = parse_frontmatter(content)
        updated = fm.get("updated", "")
        if updated != today:
            stale_info = f"last updated {updated}" if updated else "no updated date"
            warnings.append(f"  - {task_name}: {stale_info}")
    return warnings


def get_memory_dir(cwd: str) -> Path:
    """Derive the Claude memory directory path from cwd.

    Example: C:\\dev_projects\\malmee -> C--dev-projects-malmee
    """
    # Normalize to Windows-style path
    normalized = Path(cwd).resolve()
    path_str = str(normalized)
    # Convert: C:\dev_projects\malmee -> C--dev-projects-malmee
    # Replace : with empty, \ and / with -
    dir_name = path_str.replace(":", "").replace("\\", "-").replace("/", "-")
    return Path.home() / ".claude" / "projects" / dir_name / "memory"


def check_volatile_memory(memory_dir: Path, stale_days: int) -> list[str]:
    """Find stale volatile memory files. Return warning lines."""
    warnings = []
    if not memory_dir.exists():
        return warnings
    today = datetime.now()
    for f in sorted(memory_dir.glob("project_*.md")):
        try:
            content = f.read_text(encoding="utf-8")
        except Exception:
            continue
        fm = parse_frontmatter(content)
        if fm.get("volatile", "").lower() != "true":
            continue
        # Check file modification time
        mtime = datetime.fromtimestamp(os.path.getmtime(f))
        age_days = (today - mtime).days
        if age_days > stale_days:
            warnings.append(f"  - {f.name}: {age_days}d old (volatile, limit {stale_days}d)")
    return warnings


def main():
    try:
        hook_input = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    # Extract command from tool_input
    tool_input = hook_input.get("tool_input", {})
    if isinstance(tool_input, str):
        try:
            tool_input = json.loads(tool_input)
        except Exception:
            sys.exit(0)
    command = tool_input.get("command", "")

    # Only fire on git commit
    if not is_git_commit(command):
        sys.exit(0)

    cwd = normalize_path(hook_input.get("cwd", os.getcwd()))

    # Load configs
    project_cfg = load_project_config(cwd)
    if not project_cfg:
        sys.exit(0)
    global_cfg = load_global_config()
    if not global_cfg:
        sys.exit(0)

    vault_path = global_cfg.get("vault_path", "")
    project_name = project_cfg.get("project_name", "")
    task_mapping = project_cfg.get("task_mapping", {})
    memory_stale_days = project_cfg.get("memory_stale_days", 14)

    if not vault_path or not project_name:
        sys.exit(0)

    today = date.today().isoformat()

    # Get staged files and match against task mapping
    staged_files = get_staged_files(cwd)
    if not staged_files:
        sys.exit(0)

    matched_tasks = match_tasks(staged_files, task_mapping)

    all_warnings = []

    # Check vault file staleness
    if matched_tasks:
        vault_warnings = check_vault_staleness(matched_tasks, vault_path, project_name, today)
        if vault_warnings:
            all_warnings.append("⚠ Vault task files are stale (not updated today):")
            all_warnings.extend(vault_warnings)

    # Check volatile memory staleness
    memory_dir = get_memory_dir(cwd)
    memory_warnings = check_volatile_memory(memory_dir, memory_stale_days)
    if memory_warnings:
        all_warnings.append("⚠ Volatile memory files are stale:")
        all_warnings.extend(memory_warnings)

    if all_warnings:
        all_warnings.append("")
        all_warnings.append("Run /obsidian-sync to update vault before committing.")
        print("\n".join(all_warnings))

    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
