#!/usr/bin/env bash
# SessionStart hook wrapper — delegates to Python
exec python "${CLAUDE_SKILL_DIR}/bin/obsidian_context.py"
