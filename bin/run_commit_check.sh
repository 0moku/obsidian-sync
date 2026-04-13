#!/usr/bin/env bash
# PreToolUse hook wrapper — vault commit check
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python "${SCRIPT_DIR}/vault_commit_check.py"
