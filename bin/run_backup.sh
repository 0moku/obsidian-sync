#!/usr/bin/env bash
# PostToolUse hook wrapper — delegates to Python
exec python "${CLAUDE_SKILL_DIR}/bin/obsidian_backup.py"
