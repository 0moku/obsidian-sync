#!/usr/bin/env bash
# SessionStart hook wrapper — delegates to Python
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python "${SCRIPT_DIR}/obsidian_context.py"
