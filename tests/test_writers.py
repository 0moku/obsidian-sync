import json
import sys
import os
import tempfile
from pathlib import Path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "bin"))
from obsidian_sync import (
    generate_session_log, generate_decision_entry,
    update_decisions_file, sanitize_filename, get_session_filename,
)

SAMPLE_API_RESPONSE = {
    "session": {
        "title": "배터리 채점 로직 버그 수정",
        "summary": "MLU 계산을 음절에서 어절로 변경했다.",
        "key_activities": ["MLU 계산 수정", "테스트 추가"],
        "files_changed": ["server/app/services/battery_scoring.py"],
        "tags": ["battery", "scoring"],
        "workflow": ["investigate"],
        "task_size": "S",
    },
    "decisions": [{"title": "MLU 어절 단위로 전환", "decision": "음절 → 어절", "alternatives": "음절 유지 (기각)", "rationale": "수집 데이터가 어절 단위"}],
    "status": {"completed": ["MLU 수정"], "in_progress": [], "blockers": [], "next_steps": ["배포"]},
    "roadmap": "---\nproject: test\nupdated: 2026-04-06\n---\n# test 현황\n",
}

def test_sanitize_filename():
    assert sanitize_filename("배터리 채점/로직") == "배터리-채점-로직"
    assert sanitize_filename('a:b*c?"d') == "a-b-c-d"
    assert sanitize_filename("  hello  world  ") == "hello-world"

def test_get_session_filename_no_collision():
    with tempfile.TemporaryDirectory() as tmpdir:
        name = get_session_filename(tmpdir, "2026-04-06", "테스트-제목")
        assert name == "2026-04-06_테스트-제목.md"

def test_get_session_filename_with_collision():
    with tempfile.TemporaryDirectory() as tmpdir:
        Path(tmpdir, "2026-04-06_테스트-제목.md").touch()
        name = get_session_filename(tmpdir, "2026-04-06", "테스트-제목")
        assert name == "2026-04-06_테스트-제목_2.md"

def test_generate_session_log():
    meta = {"date": "2026-04-06", "project": "test-project", "duration_min": 45, "model": "claude-opus-4-6", "session_id": "abc123"}
    md = generate_session_log(SAMPLE_API_RESPONSE, meta)
    assert "date: 2026-04-06" in md
    assert "tags: [battery, scoring]" in md
    assert "# 배터리 채점 로직 버그 수정" in md
    assert "## 요약" in md
    assert "ai_summary: true" in md

def test_generate_decision_entry():
    entry = generate_decision_entry(SAMPLE_API_RESPONSE["decisions"][0], "2026-04-06", "2026-04-06_배터리-채점-로직-버그-수정")
    assert "## 2026-04-06: MLU 어절 단위로 전환" in entry
    assert "[[2026-04-06_배터리-채점-로직-버그-수정]]" in entry

def test_update_decisions_file_creates_new():
    with tempfile.TemporaryDirectory() as tmpdir:
        fp = Path(tmpdir) / "decisions.md"
        entries = [generate_decision_entry(SAMPLE_API_RESPONSE["decisions"][0], "2026-04-06", "test")]
        update_decisions_file(fp, entries, "test-project")
        content = fp.read_text(encoding="utf-8")
        assert "project: test-project" in content
        assert "MLU 어절" in content

def test_update_decisions_file_appends():
    from datetime import datetime, timezone
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    with tempfile.TemporaryDirectory() as tmpdir:
        fp = Path(tmpdir) / "decisions.md"
        existing = (
            "---\n"
            "project: test\n"
            "updated: 2020-01-01\n"
            "---\n"
            "# 결정 로그\n"
            "\n"
            "## 2020-01-01: 이전\n"
            "- old\n"
        )
        fp.write_text(existing, encoding="utf-8")
        entries = [generate_decision_entry(SAMPLE_API_RESPONSE["decisions"][0], today, "test")]
        update_decisions_file(fp, entries, "test")
        content = fp.read_text(encoding="utf-8")
        assert f"updated: {today}" in content
        assert content.index("MLU") < content.index("이전")
