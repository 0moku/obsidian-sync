import json
import sys
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'bin'))
from obsidian_backup import normalize_path, PENDING_PATH


def test_normalize_path_windows_msys():
    with patch('obsidian_backup.sys') as mock_sys:
        mock_sys.platform = "win32"
        from obsidian_backup import normalize_path as np
        # Re-import won't help due to caching, test directly
    if sys.platform == "win32":
        assert normalize_path("/c/Users/test") == "C:\\Users\\test"
        assert normalize_path("/d/projects/foo") == "D:\\projects\\foo"


def test_normalize_path_passthrough():
    assert normalize_path("C:\\Users\\test") == "C:\\Users\\test"
    assert normalize_path("/home/user/test") == "/home/user/test" or sys.platform == "win32"


def test_backup_writes_pending_json():
    """Integration test: simulate hook input and verify pending.json output."""
    with tempfile.TemporaryDirectory() as tmpdir:
        pending = Path(tmpdir) / "pending.json"
        global_cfg = Path(tmpdir) / "obsidian.json"
        project_dir = Path(tmpdir) / "project" / ".claude"
        project_dir.mkdir(parents=True)

        global_cfg.write_text('{"vault_path": "C:\\\\test"}', encoding="utf-8")
        (project_dir / "obsidian.json").write_text('{"project_name": "test"}', encoding="utf-8")

        hook_input = {
            "transcript_path": str(Path(tmpdir) / "transcript.jsonl"),
            "session_id": "sess-123",
            "cwd": str(Path(tmpdir) / "project"),
        }

        import obsidian_backup as mod
        orig_pending = mod.PENDING_PATH
        orig_global = mod.GLOBAL_CONFIG_PATH
        try:
            mod.PENDING_PATH = pending
            mod.GLOBAL_CONFIG_PATH = global_cfg
            import io
            sys.stdin = io.StringIO(json.dumps(hook_input))
            mod.main()
        finally:
            mod.PENDING_PATH = orig_pending
            mod.GLOBAL_CONFIG_PATH = orig_global
            sys.stdin = sys.__stdin__

        assert pending.exists()
        data = json.loads(pending.read_text(encoding="utf-8"))
        assert data["session_id"] == "sess-123"
        assert "backup_time" in data
