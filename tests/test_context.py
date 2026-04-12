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


def test_extract_context_with_status_v2():
    status = """---
status: ACTIVE
current_phase: Phase 3.6 fine-tuning 대기
updated: 2026-04-12
---
# Malmee — 발달 로드맵

## 현황 요약

| 과제 | 상태 | 문항 | 비고 |
|------|------|------|------|
| 표현어휘 | ✅ β | 308 (14 pool) | GPT Image 1.5, AoA-IRT |
| 수용어휘 | 🔧 구현 대기 | 150 plan | eng-review 완료 |
| 문장산출 | ✅ 배포 | 16 prompt | NDW/MLU 자동 |

**블로커**: AI Hub 다운로드 대기
**최근 완료**: 홈 UX 재구성 (2026-04-12)

## Phase 3.6 — PCC 파이프라인 교체 🔄

- [x] 1단계: 베이스라인 측정
- [x] 2단계: fine-tuning 사전 준비
- [ ] 3단계: fine-tuning 실행
- [ ] 4단계: 파이프라인 연결

## Phase 4 — 모바일 배포

- [ ] 모바일 네이티브 녹음
"""
    context = extract_context(status, "")
    # Phase name extracted from frontmatter
    assert "Phase 3.6" in context
    # 현황 요약 table present
    assert "현황 요약" in context
    assert "표현어휘" in context
    # 블로커 present with AI Hub mentioned
    assert "블로커" in context
    assert "AI Hub" in context
    # Progress info for the active phase (🔄)
    assert "2/4" in context


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
