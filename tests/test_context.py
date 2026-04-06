import json
import sys
import os
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'bin'))
from obsidian_context import extract_context, get_pending_reminder


def test_extract_context_with_status():
    status = """---
project: test
current_phase: "Phase 2: 채점"
---
# test 현황

## 로드맵
### Phase 1 ✅
- [x] 항목 1
- [x] 항목 2

### Phase 2 🔄
- [x] 항목 3
- [ ] 항목 4

## 현재 세션 상태
### 완료
- MLU 수정
"""
    context = extract_context(status, "")
    assert "Phase 2: 채점" in context
    assert "3/4" in context  # 진행률
    assert "MLU 수정" in context


def test_extract_context_with_decisions():
    decisions = """---
project: test
updated: 2026-04-06
---
# 결정 로그

## 2026-04-06: 결정 A
- details

## 2026-04-05: 결정 B
- details

## 2026-04-04: 결정 C
- details

## 2026-04-03: 결정 D
- details
"""
    context = extract_context("", decisions)
    assert "최근 결정 (3건)" in context
    assert "결정 A" in context
    assert "결정 B" in context
    assert "결정 C" in context
    assert "결정 D" not in context  # only top 3


def test_extract_context_empty():
    assert extract_context("", "") == ""


def test_get_pending_reminder_with_pending():
    with tempfile.TemporaryDirectory() as tmpdir:
        pending = Path(tmpdir) / "pending.json"
        pending.write_text(json.dumps({
            "session_id": "abcdefgh12345",
            "backup_time": "2026-04-06T10:30:00+00:00",
            "transcript_path": "/tmp/t.jsonl",
            "cwd": "/tmp/project",
        }), encoding="utf-8")

        import obsidian_context as mod
        orig = mod.PENDING_PATH
        try:
            mod.PENDING_PATH = pending
            reminder = get_pending_reminder()
        finally:
            mod.PENDING_PATH = orig

        assert "Obsidian Sync" in reminder
        assert "2026-04-06 10:30:00" in reminder
        assert "abcdefgh" in reminder


def test_get_pending_reminder_no_pending():
    import obsidian_context as mod
    orig = mod.PENDING_PATH
    try:
        mod.PENDING_PATH = Path("/nonexistent/path/pending.json")
        reminder = get_pending_reminder()
    finally:
        mod.PENDING_PATH = orig
    assert reminder == ""
