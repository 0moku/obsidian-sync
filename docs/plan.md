# obsidian-sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Claude Code 세션 종료 시 Obsidian vault에 자동으로 세션 로그, 결정 사항, 프로젝트 로드맵을 기록하는 스킬

**Architecture:** 단일 Python 스크립트(`obsidian-sync.py`)가 SessionEnd hook에서 실행되어 transcript JSONL을 파싱하고, Claude API(Haiku)로 구조화된 요약을 생성한 뒤, Obsidian vault에 마크다운 파일을 쓴다. 별도 스크립트(`obsidian-context.py`)가 SessionStart hook에서 `_status.md`를 읽어 컨텍스트를 주입한다.

**Tech Stack:** Python 3, anthropic SDK, Claude Code Hooks (SessionEnd/SessionStart)

**Spec:** `docs/design.md`

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `prompts/summarize.txt` | LLM 요약+로드맵 프롬프트 템플릿 |
| Create | `prompts/roadmap_rules.txt` | 로드맵 업데이트 규칙 (프롬프트에 삽입) |
| Create | `templates/dashboard.md` | Dataview 쿼리 대시보드 템플릿 |
| Create | `bin/obsidian_sync.py` | SessionEnd hook 메인 스크립트 (~300줄) |
| Create | `bin/obsidian_context.py` | SessionStart hook 컨텍스트 주입 (~80줄) |
| Create | `tests/test_parse.py` | transcript 파싱+압축 단위 테스트 |
| Create | `tests/test_writers.py` | 마크다운 생성 단위 테스트 |
| Create | `tests/fixtures/sample_transcript.jsonl` | 테스트용 transcript 샘플 |
| Create | `SKILL.md` | 스킬 정의 + /obsidian-setup, /obsidian-context 커맨드 |
| Create | `requirements.txt` | anthropic 의존성 |
| Create | `README.md` | 설치 및 사용법 |

---

### Task 1: Static Assets — 프롬프트 + 템플릿

**Files:**
- Create: `prompts/summarize.txt`
- Create: `prompts/roadmap_rules.txt`
- Create: `templates/dashboard.md`
- Create: `requirements.txt`

- [ ] **Step 1: Create prompts directory and summarize.txt**

```text
# prompts/summarize.txt
다음은 Claude Code 세션의 transcript이다. 아래 지시에 따라 구조화된 JSON을 생성하라.

## 입력
- TRANSCRIPT: 세션 대화 내용 (압축됨)
- EXISTING_STATUS: 기존 _status.md 내용 (없을 수 있음)
- GIT_DIFF: git diff --stat 결과
- CONTEXT_SOURCES: spec/plan 문서 내용 (없을 수 있음)

## 출력 JSON 구조
정확히 아래 구조의 JSON만 출력하라. 다른 텍스트 없이 JSON만.

{
  "session": {
    "title": "세션을 설명하는 간결한 제목 (한글, 30자 이내, 파일명에 쓸 수 있는 문자만)",
    "summary": "세션에서 한 일 요약 (2-3문장)",
    "key_activities": ["주요 활동 목록"],
    "files_changed": ["변경된 파일 경로 목록"],
    "tags": ["관련 태그 (소문자, 영어)"],
    "workflow": ["사용된 워크플로우 단계 (plan-ceo-review, plan-eng-review, brainstorming, subagent-driven-development, review, qa, ship 등). 해당 없으면 빈 배열"],
    "task_size": "S, M, L 중 하나. 판단 불가하면 null"
  },
  "decisions": [
    {
      "title": "결정 제목",
      "decision": "무엇을 결정했는지",
      "alternatives": "기각된 대안과 이유 (없으면 빈 문자열)",
      "rationale": "근거"
    }
  ],
  "status": {
    "completed": ["이번 세션에서 완료된 것"],
    "in_progress": ["진행 중인 것"],
    "blockers": ["블로커 (없으면 빈 배열)"],
    "next_steps": ["다음 할 일"]
  },
  "roadmap": "업데이트된 _status.md의 전체 내용 (프론트매터 포함). 아래 로드맵 규칙을 반드시 따를 것. 기존 _status.md가 없으면 새로 생성."
}

## 로드맵 규칙
{ROADMAP_RULES}

## 중요
- JSON만 출력. 마크다운 코드 펜스(```)로 감싸지 마라.
- title은 파일명으로 쓰이므로 /\:*?"<>| 문자를 포함하지 마라.
- roadmap 필드는 _status.md 파일의 전체 내용이다. 프론트매터(---)부터 시작하라.
- 기존 _status.md가 있으면 그것을 기반으로 업데이트하라. 없으면 transcript와 context에서 추론하여 새로 만들어라.
```

- [ ] **Step 2: Create roadmap_rules.txt**

```text
# prompts/roadmap_rules.txt
1. 완료 판정: 세션에서 실제로 구현+테스트 통과가 확인된 항목만 [x].
   "논의만 한 것"은 완료가 아니다.

2. 항목 추가: 세션에서 새로운 작업이 구체적으로 언급되었거나,
   spec/plan 문서에 정의된 작업이 로드맵에 없으면 추가.
   해당 Phase 하위에 적절히 배치.

3. 항목 제거: 절대 삭제하지 않는다.
   불필요해진 항목은 취소선으로 표시하고 사유를 남긴다.
   예: - ~~어휘 과제 수동 채점~~ (2026-04-06: 자동 채점으로 대체)

4. Phase 구조 변경: 새로운 Phase 추가는 허용.
   기존 Phase의 이름 변경이나 병합은 세션에서 명시적으로 논의된 경우만.

5. 순서: Phase 내 태스크는 의존성 순서대로 배치.
   완료된 것이 위, 진행 중이 중간, 미착수가 아래.

6. 태스크 세분화: 큰 태스크가 하위 태스크로 분해되었으면 반영.
   2단계 이상 중첩하지 않는다. Phase > 태스크 > 하위 태스크 (최대).

7. 기존 로드맵 존중: 이전 세션에서 합의된 항목을 근거 없이
   임의로 수정하지 않는다. 변경 시 반드시 세션 내 근거가 있어야 한다.

8. Phase 상태 이모지: ✅ (모든 태스크 완료), 🔄 (진행 중), 없음 (미착수).

9. current_phase 프론트매터: 🔄 상태인 Phase로 설정.

10. 하이브리드 워크플로우: gstack/superpowers 사용 흔적이 있으면
    "하이브리드 워크플로우 상태" 섹션을 포함하라.
```

- [ ] **Step 3: Create templates/dashboard.md**

```markdown
# Claude Dev Dashboard

## 프로젝트 현황
```dataview
TABLE status, current_phase, updated, last_session
FROM "claude-dev/projects"
WHERE file.name = "_status"
SORT updated DESC
```

## 최근 세션
```dataview
TABLE date, project, duration_min, workflow, tags
FROM "claude-dev/projects"
WHERE date
SORT date DESC
LIMIT 20
```

## 최근 결정
```dataview
TABLE updated
FROM "claude-dev/projects"
WHERE file.name = "decisions"
SORT updated DESC
```
```

- [ ] **Step 4: Create requirements.txt**

```text
anthropic>=0.40.0
```

- [ ] **Step 5: Commit**

```bash
git add prompts/ templates/ requirements.txt
git commit -m "feat: add prompt templates, dashboard template, and requirements"
```

---

### Task 2: Test Fixtures — 샘플 transcript 생성

**Files:**
- Create: `tests/fixtures/sample_transcript.jsonl`

- [ ] **Step 1: Create test fixtures directory and sample transcript**

실제 Claude Code transcript JSONL 포맷에 맞는 샘플. 각 줄은 독립 JSON 객체.

```jsonl
{"type":"file-history-snapshot","messageId":"snap-001","snapshot":{"messageId":"snap-001","trackedFileBackups":{},"timestamp":"2026-04-06T10:00:00Z"},"isSnapshotUpdate":false}
{"parentUuid":null,"isSidechain":false,"userType":"external","cwd":"/c/dev_projects/testproj","sessionId":"sess-abc123","version":"1.0.0","gitBranch":"main","type":"user","message":{"role":"user","content":"배터리 채점 로직에서 MLU를 어절 단위로 변경해줘"},"uuid":"msg-001","timestamp":"2026-04-06T10:00:01Z","permissionMode":"default"}
{"parentUuid":"msg-001","isSidechain":false,"userType":"external","cwd":"/c/dev_projects/testproj","sessionId":"sess-abc123","version":"1.0.0","gitBranch":"main","type":"assistant","uuid":"msg-002","timestamp":"2026-04-06T10:00:05Z","message":{"id":"resp-001","model":"claude-opus-4-6","role":"assistant","stop_reason":"tool_use","content":[{"type":"thinking","thinking":"Let me read the scoring file first...","signature":"sig-xxx"},{"type":"text","text":"채점 로직을 확인하겠습니다."},{"type":"tool_use","id":"toolu-001","name":"Read","input":{"file_path":"/c/dev_projects/testproj/server/app/services/battery_scoring.py"}}],"usage":{"input_tokens":1000,"output_tokens":200}}}
{"parentUuid":"msg-002","isSidechain":false,"userType":"external","cwd":"/c/dev_projects/testproj","sessionId":"sess-abc123","version":"1.0.0","gitBranch":"main","type":"user","message":{"role":"user","content":[{"type":"tool_result","tool_use_id":"toolu-001","content":"def calculate_mlu(utterances):\n    total_syllables = sum(count_syllables(u) for u in utterances)\n    return total_syllables / len(utterances)"}]},"uuid":"msg-003","timestamp":"2026-04-06T10:00:06Z","toolUseResult":{"stdout":"","stderr":"","isImage":false}}
{"parentUuid":"msg-003","isSidechain":false,"userType":"external","cwd":"/c/dev_projects/testproj","sessionId":"sess-abc123","version":"1.0.0","gitBranch":"main","type":"assistant","uuid":"msg-004","timestamp":"2026-04-06T10:00:10Z","message":{"id":"resp-002","model":"claude-opus-4-6","role":"assistant","stop_reason":"tool_use","content":[{"type":"text","text":"음절 단위로 되어있네요. 어절 단위로 수정합니다."},{"type":"tool_use","id":"toolu-002","name":"Edit","input":{"file_path":"/c/dev_projects/testproj/server/app/services/battery_scoring.py","old_string":"total_syllables = sum(count_syllables(u) for u in utterances)","new_string":"total_words = sum(len(u.split()) for u in utterances)"}}],"usage":{"input_tokens":1500,"output_tokens":300}}}
{"parentUuid":"msg-004","isSidechain":false,"userType":"external","cwd":"/c/dev_projects/testproj","sessionId":"sess-abc123","version":"1.0.0","gitBranch":"main","type":"user","message":{"role":"user","content":[{"type":"tool_result","tool_use_id":"toolu-002","content":"File edited successfully"}]},"uuid":"msg-005","timestamp":"2026-04-06T10:00:11Z","toolUseResult":{"stdout":"","stderr":"","isImage":false}}
{"parentUuid":"msg-005","isSidechain":false,"userType":"external","cwd":"/c/dev_projects/testproj","sessionId":"sess-abc123","version":"1.0.0","gitBranch":"main","type":"assistant","uuid":"msg-006","timestamp":"2026-04-06T10:00:15Z","message":{"id":"resp-003","model":"claude-opus-4-6","role":"assistant","stop_reason":"end_turn","content":[{"type":"text","text":"MLU 계산을 음절 기준에서 어절 기준으로 변경했습니다. battery_scoring.py를 수정 완료했습니다."}],"usage":{"input_tokens":2000,"output_tokens":100}}}
{"type":"progress","data":{"type":"hook_progress","hookEvent":"Stop","hookName":"ntfy","command":"curl -s ntfy.sh/..."},"parentToolUseID":"","toolUseID":"hook-001","timestamp":"2026-04-06T10:00:16Z","uuid":"prog-001"}
{"type":"system","subtype":"stop_hook_summary","hookCount":1,"hookInfos":[{"command":"curl -s ntfy.sh/...","durationMs":500}],"hookErrors":[],"timestamp":"2026-04-06T10:00:17Z","uuid":"sys-001"}
```

- [ ] **Step 2: Commit**

```bash
git add tests/
git commit -m "test: add sample transcript fixture"
```

---

### Task 3: Transcript 파싱 + 압축

**Files:**
- Create: `bin/obsidian-sync.py` (파싱/압축 함수만 먼저)
- Create: `tests/test_parse.py`

- [ ] **Step 1: Write failing tests for parse_transcript and compress_transcript**

```python
# tests/test_parse.py
import json
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'bin'))

from obsidian_sync import parse_transcript, compress_transcript

FIXTURE_PATH = os.path.join(os.path.dirname(__file__), 'fixtures', 'sample_transcript.jsonl')


def test_parse_transcript_extracts_messages():
    messages = parse_transcript(FIXTURE_PATH)
    user_msgs = [m for m in messages if m['type'] == 'user']
    assistant_msgs = [m for m in messages if m['type'] == 'assistant']
    # fixture has 1 text user msg + 2 tool_result user msgs + 3 assistant msgs
    assert len(user_msgs) >= 1
    assert len(assistant_msgs) >= 1


def test_parse_transcript_extracts_metadata():
    messages = parse_transcript(FIXTURE_PATH)
    # first user message should have session metadata
    first_user = next(m for m in messages if m['type'] == 'user')
    assert first_user['session_id'] == 'sess-abc123'
    assert first_user['cwd'] == '/c/dev_projects/testproj'
    assert first_user['git_branch'] == 'main'


def test_parse_transcript_skips_non_message_types():
    messages = parse_transcript(FIXTURE_PATH)
    types = {m['type'] for m in messages}
    assert 'file-history-snapshot' not in types
    assert 'progress' not in types
    assert 'system' not in types


def test_parse_transcript_extracts_timestamps():
    messages = parse_transcript(FIXTURE_PATH)
    assert messages[0]['timestamp'] is not None
    assert messages[-1]['timestamp'] is not None


def test_compress_transcript_removes_thinking():
    messages = parse_transcript(FIXTURE_PATH)
    compressed = compress_transcript(messages)
    for msg in compressed:
        if msg['type'] == 'assistant':
            for block in msg.get('content', []):
                assert block.get('type') != 'thinking'


def test_compress_transcript_summarizes_tool_results():
    messages = parse_transcript(FIXTURE_PATH)
    compressed = compress_transcript(messages)
    for msg in compressed:
        if msg['type'] == 'user' and isinstance(msg.get('content'), list):
            for block in msg['content']:
                if block.get('type') == 'tool_result':
                    # long content should be summarized
                    assert len(block['content']) < 500


def test_compress_transcript_preserves_user_text():
    messages = parse_transcript(FIXTURE_PATH)
    compressed = compress_transcript(messages)
    user_text_msgs = [m for m in compressed if m['type'] == 'user' and isinstance(m.get('content'), str)]
    assert len(user_text_msgs) >= 1
    assert '배터리' in user_text_msgs[0]['content']


def test_compress_transcript_extracts_tool_uses():
    messages = parse_transcript(FIXTURE_PATH)
    compressed = compress_transcript(messages)
    tool_uses = []
    for msg in compressed:
        if msg['type'] == 'assistant':
            for block in msg.get('content', []):
                if block.get('type') == 'tool_use':
                    tool_uses.append(block)
    assert len(tool_uses) >= 1
    assert tool_uses[0]['name'] in ('Read', 'Edit')
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd ~/.claude/skills/obsidian-sync && python -m pytest tests/test_parse.py -v
```

Expected: ModuleNotFoundError (obsidian_sync not found)

- [ ] **Step 3: Implement parse_transcript and compress_transcript**

```python
# bin/obsidian_sync.py (initial — parsing functions only)
#!/usr/bin/env python3
"""obsidian-sync: Claude Code SessionEnd hook → Obsidian vault."""

import json
import os
import sys
import re
import time
import logging
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_PATH = Path.home() / ".claude" / "obsidian-sync.log"

def get_logger():
    logger = logging.getLogger("obsidian-sync")
    logger.setLevel(logging.DEBUG)
    if not logger.handlers:
        fh = logging.FileHandler(LOG_PATH, encoding="utf-8")
        fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(fh)
    return logger

log = get_logger()

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
GLOBAL_CONFIG_PATH = Path.home() / ".claude" / "obsidian.json"

def load_config(cwd: str) -> dict | None:
    """Load merged global + project config. Returns None if not configured."""
    if not GLOBAL_CONFIG_PATH.exists():
        return None
    with open(GLOBAL_CONFIG_PATH, "r", encoding="utf-8") as f:
        global_cfg = json.load(f)

    project_cfg_path = Path(cwd) / ".claude" / "obsidian.json"
    project_cfg = {}
    if project_cfg_path.exists():
        with open(project_cfg_path, "r", encoding="utf-8") as f:
            project_cfg = json.load(f)

    # Merge: project overrides global
    cfg = {**global_cfg, **{k: v for k, v in project_cfg.items() if v is not None}}
    return cfg

# ---------------------------------------------------------------------------
# Transcript Parsing
# ---------------------------------------------------------------------------
def parse_transcript(path: str) -> list[dict]:
    """Parse JSONL transcript into structured messages."""
    messages = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            entry_type = entry.get("type")
            if entry_type not in ("user", "assistant"):
                continue

            msg = {
                "type": entry_type,
                "timestamp": entry.get("timestamp"),
                "session_id": entry.get("sessionId"),
                "cwd": entry.get("cwd"),
                "git_branch": entry.get("gitBranch"),
            }

            raw_message = entry.get("message", {})
            raw_content = raw_message.get("content")

            if entry_type == "assistant":
                msg["model"] = raw_message.get("model")
                msg["content"] = raw_content if isinstance(raw_content, list) else [{"type": "text", "text": str(raw_content)}]
            elif entry_type == "user":
                if isinstance(raw_content, str):
                    msg["content"] = raw_content
                elif isinstance(raw_content, list):
                    msg["content"] = raw_content
                else:
                    msg["content"] = str(raw_content)

            messages.append(msg)
    return messages


def compress_transcript(messages: list[dict], max_chars: int = 500000) -> list[dict]:
    """Compress transcript for API: remove thinking, summarize tool results."""
    compressed = []
    for msg in messages:
        m = {**msg}

        if m["type"] == "assistant" and isinstance(m.get("content"), list):
            new_content = []
            for block in m["content"]:
                if block.get("type") == "thinking":
                    continue  # strip thinking blocks
                if block.get("type") == "tool_use":
                    # keep tool name + simplified input
                    simplified = {"type": "tool_use", "name": block.get("name", "")}
                    tool_input = block.get("input", {})
                    if "file_path" in tool_input:
                        simplified["file_path"] = tool_input["file_path"]
                    if "command" in tool_input:
                        cmd = tool_input["command"]
                        simplified["command"] = cmd[:200] if len(cmd) > 200 else cmd
                    if "pattern" in tool_input:
                        simplified["pattern"] = tool_input["pattern"]
                    new_content.append(simplified)
                else:
                    new_content.append(block)
            m["content"] = new_content

        elif m["type"] == "user" and isinstance(m.get("content"), list):
            new_content = []
            for block in m["content"]:
                if block.get("type") == "tool_result":
                    content = block.get("content", "")
                    if isinstance(content, str) and len(content) > 300:
                        content = content[:150] + f"\n... ({len(content)} chars total)"
                    new_content.append({"type": "tool_result", "tool_use_id": block.get("tool_use_id"), "content": content})
                else:
                    new_content.append(block)
            m["content"] = new_content

        compressed.append(m)

    # If still too long, truncate from the front
    text = json.dumps(compressed, ensure_ascii=False)
    while len(text) > max_chars and len(compressed) > 4:
        compressed.pop(0)
        text = json.dumps(compressed, ensure_ascii=False)

    return compressed
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd ~/.claude/skills/obsidian-sync && python -m pytest tests/test_parse.py -v
```

Expected: All 8 tests PASS

- [ ] **Step 5: Commit**

```bash
git add bin/obsidian_sync.py tests/test_parse.py
git commit -m "feat: transcript parsing and compression with tests"
```

---

### Task 4: 마크다운 생성 함수

**Files:**
- Modify: `bin/obsidian_sync.py` (append writer functions)
- Create: `tests/test_writers.py`

- [ ] **Step 1: Write failing tests for markdown writers**

```python
# tests/test_writers.py
import json
import sys
import os
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'bin'))

from obsidian_sync import (
    generate_session_log,
    generate_decision_entry,
    update_decisions_file,
    sanitize_filename,
    get_session_filename,
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
    "decisions": [
        {
            "title": "MLU 어절 단위로 전환",
            "decision": "음절 → 어절",
            "alternatives": "음절 유지 (기각)",
            "rationale": "수집 데이터가 어절 단위",
        }
    ],
    "status": {
        "completed": ["MLU 수정"],
        "in_progress": [],
        "blockers": [],
        "next_steps": ["배포"],
    },
    "roadmap": "---\nproject: test-project\nupdated: 2026-04-06\nstatus: active\ncurrent_phase: \"Phase 1\"\nlast_session: \"[[2026-04-06_배터리-채점-로직-버그-수정]]\"\ntags: [python]\n---\n# test-project 현황\n\n## 로드맵\n### Phase 1 🔄\n- [x] MLU 수정\n- [ ] 배포\n",
}


def test_sanitize_filename():
    assert sanitize_filename("배터리 채점/로직") == "배터리-채점-로직"
    assert sanitize_filename('a:b*c?"d') == "a-b-c--d"
    assert sanitize_filename("  hello  world  ") == "hello-world"


def test_get_session_filename_no_collision():
    with tempfile.TemporaryDirectory() as tmpdir:
        name = get_session_filename(tmpdir, "2026-04-06", "테스트-제목")
        assert name == "2026-04-06_테스트-제목.md"


def test_get_session_filename_with_collision():
    with tempfile.TemporaryDirectory() as tmpdir:
        # create existing file
        Path(tmpdir, "2026-04-06_테스트-제목.md").touch()
        name = get_session_filename(tmpdir, "2026-04-06", "테스트-제목")
        assert name == "2026-04-06_테스트-제목_2.md"


def test_generate_session_log():
    meta = {
        "date": "2026-04-06",
        "project": "test-project",
        "duration_min": 45,
        "model": "claude-opus-4-6",
        "session_id": "abc123",
    }
    md = generate_session_log(SAMPLE_API_RESPONSE, meta)
    assert "---" in md
    assert "date: 2026-04-06" in md
    assert "tags: [battery, scoring]" in md
    assert "# 배터리 채점 로직 버그 수정" in md
    assert "## 요약" in md
    assert "## 주요 활동" in md
    assert "## 변경된 파일" in md
    assert "## 결정 사항" in md
    assert "## 상태" in md
    assert "ai_summary: true" in md


def test_generate_decision_entry():
    entry = generate_decision_entry(
        SAMPLE_API_RESPONSE["decisions"][0],
        "2026-04-06",
        "2026-04-06_배터리-채점-로직-버그-수정",
    )
    assert "## 2026-04-06: MLU 어절 단위로 전환" in entry
    assert "**결정**" in entry
    assert "**세션**" in entry
    assert "[[2026-04-06_배터리-채점-로직-버그-수정]]" in entry


def test_update_decisions_file_creates_new():
    with tempfile.TemporaryDirectory() as tmpdir:
        filepath = Path(tmpdir) / "decisions.md"
        entries = [generate_decision_entry(
            SAMPLE_API_RESPONSE["decisions"][0], "2026-04-06", "test-session"
        )]
        update_decisions_file(filepath, entries, "test-project")
        content = filepath.read_text(encoding="utf-8")
        assert "project: test-project" in content
        assert "# 결정 로그" in content
        assert "MLU 어절" in content


def test_update_decisions_file_appends():
    with tempfile.TemporaryDirectory() as tmpdir:
        filepath = Path(tmpdir) / "decisions.md"
        filepath.write_text(
            "---\nproject: test-project\nupdated: 2026-04-05\n---\n# 결정 로그\n\n## 2026-04-05: 이전 결정\n- old\n",
            encoding="utf-8",
        )
        entries = [generate_decision_entry(
            SAMPLE_API_RESPONSE["decisions"][0], "2026-04-06", "test-session"
        )]
        update_decisions_file(filepath, entries, "test-project")
        content = filepath.read_text(encoding="utf-8")
        assert "updated: 2026-04-06" in content
        assert "MLU 어절" in content
        assert "이전 결정" in content
        # new entry should be above old
        mlu_pos = content.index("MLU")
        old_pos = content.index("이전 결정")
        assert mlu_pos < old_pos
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd ~/.claude/skills/obsidian-sync && python -m pytest tests/test_writers.py -v
```

Expected: ImportError (functions not defined yet)

- [ ] **Step 3: Implement markdown writer functions in obsidian_sync.py**

`bin/obsidian_sync.py`에 아래 함수들을 추가:

```python
# ---------------------------------------------------------------------------
# File naming
# ---------------------------------------------------------------------------
def sanitize_filename(name: str) -> str:
    """Replace unsafe chars with hyphens, collapse spaces."""
    name = re.sub(r'[/\\:*?"<>|]', '-', name)
    name = re.sub(r'\s+', '-', name.strip())
    name = re.sub(r'-+', '-', name).strip('-')
    return name


def get_session_filename(sessions_dir: str, date: str, title: str) -> str:
    """Generate unique session filename, adding _N suffix on collision."""
    base = f"{date}_{sanitize_filename(title)}"
    candidate = f"{base}.md"
    if not Path(sessions_dir, candidate).exists():
        return candidate
    n = 2
    while Path(sessions_dir, f"{base}_{n}.md").exists():
        n += 1
    return f"{base}_{n}.md"


# ---------------------------------------------------------------------------
# Markdown generators
# ---------------------------------------------------------------------------
def generate_session_log(api_response: dict, meta: dict) -> str:
    """Generate session log markdown from API response + metadata."""
    s = api_response["session"]
    st = api_response["status"]
    decisions = api_response.get("decisions", [])

    lines = [
        "---",
        f"date: {meta['date']}",
        f"project: {meta['project']}",
        f"duration_min: {meta['duration_min']}",
        f"model: {meta['model']}",
        f"tags: [{', '.join(s.get('tags', []))}]",
    ]
    if s.get("workflow"):
        lines.append(f"workflow: [{', '.join(s['workflow'])}]")
    if s.get("task_size"):
        lines.append(f"task_size: {s['task_size']}")
    lines += [
        f"session_id: {meta['session_id']}",
        "ai_summary: true",
        "---",
        f"# {s['title']}",
        "",
        "## 요약",
        s.get("summary", ""),
        "",
        "## 주요 활동",
    ]
    for act in s.get("key_activities", []):
        lines.append(f"- {act}")

    lines += ["", "## 변경된 파일"]
    for f in s.get("files_changed", []):
        lines.append(f"- `{f}`")

    if decisions:
        lines += ["", "## 결정 사항"]
        for d in decisions:
            lines += [
                f"### {d['title']}",
                f"- **결정**: {d['decision']}",
            ]
            if d.get("alternatives"):
                lines.append(f"- **대안**: {d['alternatives']}")
            lines.append(f"- **근거**: {d['rationale']}")

    lines += ["", "## 상태"]
    for item in st.get("completed", []):
        lines.append(f"- ✅ {item}")
    for item in st.get("in_progress", []):
        lines.append(f"- 🔄 {item}")
    for item in st.get("blockers", []):
        lines.append(f"- ❌ {item}")
    for item in st.get("next_steps", []):
        lines.append(f"- 🔲 {item}")

    return "\n".join(lines) + "\n"


def generate_decision_entry(decision: dict, date: str, session_stem: str) -> str:
    """Generate a single decision entry for decisions.md."""
    lines = [
        f"## {date}: {decision['title']}",
        f"- **결정**: {decision['decision']}",
    ]
    if decision.get("alternatives"):
        lines.append(f"- **대안**: {decision['alternatives']}")
    lines += [
        f"- **근거**: {decision['rationale']}",
        f"- **세션**: [[{session_stem}]]",
    ]
    return "\n".join(lines)


def update_decisions_file(filepath: Path, new_entries: list[str], project: str):
    """Append new decisions to decisions.md (newest on top)."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    if filepath.exists():
        content = filepath.read_text(encoding="utf-8")
        # Update frontmatter date
        content = re.sub(r'updated: \d{4}-\d{2}-\d{2}', f'updated: {today}', content)
        # Insert after "# 결정 로그\n"
        marker = "# 결정 로그\n"
        idx = content.find(marker)
        if idx >= 0:
            insert_pos = idx + len(marker)
            insert_text = "\n" + "\n\n".join(new_entries) + "\n"
            content = content[:insert_pos] + insert_text + content[insert_pos:]
        else:
            content += "\n" + "\n\n".join(new_entries) + "\n"
    else:
        content = f"---\nproject: {project}\nupdated: {today}\n---\n# 결정 로그\n\n"
        content += "\n\n".join(new_entries) + "\n"

    filepath.write_text(content, encoding="utf-8")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd ~/.claude/skills/obsidian-sync && python -m pytest tests/test_writers.py -v
```

Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add bin/obsidian_sync.py tests/test_writers.py
git commit -m "feat: markdown generation functions with tests"
```

---

### Task 5: Claude API 호출 + 컨텍스트 수집

**Files:**
- Modify: `bin/obsidian_sync.py` (API call + context gathering functions)

- [ ] **Step 1: Implement context gathering functions**

`bin/obsidian_sync.py`에 추가:

```python
# ---------------------------------------------------------------------------
# Context gathering
# ---------------------------------------------------------------------------
def gather_context_sources(cwd: str, cfg: dict) -> str:
    """Gather content from context sources (specs, plans, gstack, etc)."""
    parts = []

    # gstack sources
    gstack_slug = cfg.get("gstack_slug")
    if cfg.get("include_gstack") and gstack_slug:
        gstack_dir = Path.home() / ".gstack" / "projects" / gstack_slug

        # CEO plans — latest file only
        ceo_dir = gstack_dir / "ceo-plans"
        if ceo_dir.exists():
            ceo_files = sorted(ceo_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
            if ceo_files:
                content = ceo_files[0].read_text(encoding="utf-8")[:3000]
                parts.append(f"## CEO Plan (latest): {ceo_files[0].name}\n{content}")

        # Eng reviews — latest file only
        eng_files = sorted(gstack_dir.glob("*-eng-review-*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
        if eng_files:
            content = eng_files[0].read_text(encoding="utf-8")[:3000]
            parts.append(f"## Eng Review (latest): {eng_files[0].name}\n{content}")

        # Learnings — last 10 entries
        learnings_path = gstack_dir / "learnings.jsonl"
        if learnings_path.exists():
            lines = learnings_path.read_text(encoding="utf-8").strip().split("\n")
            last_10 = lines[-10:] if len(lines) > 10 else lines
            parts.append(f"## Learnings (last {len(last_10)})\n" + "\n".join(last_10))

    # context_sources from project config
    for source in cfg.get("context_sources", []):
        src_path = Path(cwd) / source["path"]
        if src_path.is_file():
            content = src_path.read_text(encoding="utf-8")[:3000]
            parts.append(f"## {source['type']}: {source['path']}\n{content}")
        elif src_path.is_dir():
            # Read most recently modified files (max 3)
            files = sorted(src_path.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)[:3]
            for fp in files:
                content = fp.read_text(encoding="utf-8")[:2000]
                parts.append(f"## {source['type']}: {fp.name}\n{content}")

    return "\n\n---\n\n".join(parts) if parts else ""


def get_git_diff_stat(cwd: str) -> str:
    """Run git diff --stat in the project directory."""
    import subprocess
    try:
        result = subprocess.run(
            ["git", "diff", "--stat", "HEAD"],
            cwd=cwd, capture_output=True, text=True, timeout=5,
        )
        return result.stdout.strip() or "(no changes)"
    except Exception:
        return "(git diff unavailable)"


def get_existing_status(vault_project_dir: Path) -> str:
    """Read existing _status.md if it exists."""
    status_path = vault_project_dir / "_status.md"
    if status_path.exists():
        return status_path.read_text(encoding="utf-8")
    return ""
```

- [ ] **Step 2: Implement Claude API call function**

```python
# ---------------------------------------------------------------------------
# Claude API
# ---------------------------------------------------------------------------
def call_claude_api(
    compressed_messages: list[dict],
    existing_status: str,
    git_diff: str,
    context_sources: str,
    cfg: dict,
) -> dict | None:
    """Call Claude API with compressed transcript and context. Returns parsed JSON."""
    try:
        import anthropic
    except ImportError:
        log.error("anthropic SDK not installed. Run: pip install anthropic")
        return None

    # Load prompt templates
    skill_dir = Path(__file__).resolve().parent.parent
    prompt_template = (skill_dir / "prompts" / "summarize.txt").read_text(encoding="utf-8")
    roadmap_rules = (skill_dir / "prompts" / "roadmap_rules.txt").read_text(encoding="utf-8")
    prompt_template = prompt_template.replace("{ROADMAP_RULES}", roadmap_rules)

    # Build user message
    transcript_text = json.dumps(compressed_messages, ensure_ascii=False, indent=None)
    user_parts = [f"## TRANSCRIPT\n{transcript_text}"]
    if existing_status:
        user_parts.append(f"## EXISTING_STATUS\n{existing_status}")
    user_parts.append(f"## GIT_DIFF\n{git_diff}")
    if context_sources:
        user_parts.append(f"## CONTEXT_SOURCES\n{context_sources}")

    user_message = "\n\n".join(user_parts)
    model = cfg.get("model", "claude-haiku-4-5-20251001")
    timeout = cfg.get("api_timeout", 30)

    client = anthropic.Anthropic()

    for attempt in range(2):
        try:
            response = client.messages.create(
                model=model,
                max_tokens=8192,
                system=prompt_template,
                messages=[{"role": "user", "content": user_message}],
                timeout=timeout,
            )
            text = response.content[0].text.strip()
            # Strip markdown code fences if present
            if text.startswith("```"):
                text = re.sub(r'^```\w*\n?', '', text)
                text = re.sub(r'\n?```$', '', text)
            return json.loads(text)
        except json.JSONDecodeError as e:
            log.error(f"API response not valid JSON (attempt {attempt+1}): {e}")
            if attempt == 0:
                time.sleep(3)
        except Exception as e:
            log.error(f"API call failed (attempt {attempt+1}): {e}")
            if attempt == 0:
                time.sleep(3)

    return None
```

- [ ] **Step 3: Commit**

```bash
git add bin/obsidian_sync.py
git commit -m "feat: context gathering and Claude API integration"
```

---

### Task 6: Main entry point + fallback + 에러 처리

**Files:**
- Modify: `bin/obsidian_sync.py` (main function)

- [ ] **Step 1: Implement fallback session log for API failure**

```python
# ---------------------------------------------------------------------------
# Fallback (no API)
# ---------------------------------------------------------------------------
def generate_fallback_session_log(messages: list[dict], meta: dict) -> str:
    """Generate minimal session log without API summary."""
    # Extract user text messages
    user_texts = []
    for m in messages:
        if m["type"] == "user" and isinstance(m.get("content"), str):
            user_texts.append(m["content"])

    # Extract files from tool_use
    files_changed = set()
    for m in messages:
        if m["type"] == "assistant" and isinstance(m.get("content"), list):
            for block in m["content"]:
                if block.get("type") == "tool_use":
                    fp = block.get("file_path") or block.get("input", {}).get("file_path", "")
                    if fp:
                        files_changed.add(fp)

    title = user_texts[0][:30] if user_texts else "untitled"
    title = sanitize_filename(title)

    lines = [
        "---",
        f"date: {meta['date']}",
        f"project: {meta['project']}",
        f"duration_min: {meta['duration_min']}",
        f"model: {meta['model']}",
        f"session_id: {meta['session_id']}",
        "ai_summary: false",
        "---",
        f"# {title}",
        "",
        "## 사용자 메시지",
    ]
    for t in user_texts[:10]:
        lines.append(f"- {t[:200]}")

    if files_changed:
        lines += ["", "## 변경된 파일"]
        for f in sorted(files_changed):
            lines.append(f"- `{f}`")

    return "\n".join(lines) + "\n"
```

- [ ] **Step 2: Implement main function**

```python
# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    try:
        # Read hook input from stdin
        hook_input = json.load(sys.stdin)
    except Exception as e:
        log.error(f"Failed to read stdin: {e}")
        sys.exit(0)

    transcript_path = hook_input.get("transcript_path")
    cwd = hook_input.get("cwd", "")
    session_id = hook_input.get("session_id", "unknown")

    if not transcript_path or not Path(transcript_path).exists():
        log.warning(f"Transcript not found: {transcript_path}")
        sys.exit(0)

    # Load config
    cfg = load_config(cwd)
    if not cfg:
        sys.exit(0)  # not configured — silent exit

    vault_path = Path(cfg.get("vault_path", ""))
    if not vault_path.exists():
        log.warning(f"Vault path does not exist: {vault_path}")
        sys.exit(0)

    project_name = cfg.get("project_name", Path(cwd).name)

    # Parse transcript
    messages = parse_transcript(transcript_path)
    if len(messages) < 3:
        log.info("Session too short, skipping")
        sys.exit(0)

    # Metadata
    first_ts = messages[0].get("timestamp", "")
    last_ts = messages[-1].get("timestamp", "")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    model = "unknown"
    for m in messages:
        if m["type"] == "assistant" and m.get("model"):
            model = m["model"]
            break

    duration_min = 0
    try:
        t1 = datetime.fromisoformat(first_ts.replace("Z", "+00:00"))
        t2 = datetime.fromisoformat(last_ts.replace("Z", "+00:00"))
        duration_min = max(1, int((t2 - t1).total_seconds() / 60))
    except Exception:
        pass

    meta = {
        "date": today,
        "project": project_name,
        "duration_min": duration_min,
        "model": model,
        "session_id": session_id[:8],
    }

    # Ensure vault directories
    project_dir = vault_path / "projects" / project_name
    sessions_dir = project_dir / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)

    # Compress + call API
    compressed = compress_transcript(messages)
    existing_status = get_existing_status(project_dir)
    git_diff = get_git_diff_stat(cwd)
    context_sources = gather_context_sources(cwd, cfg)

    api_response = call_claude_api(compressed, existing_status, git_diff, context_sources, cfg)

    if api_response:
        # --- Session log ---
        title = api_response["session"]["title"]
        filename = get_session_filename(str(sessions_dir), today, sanitize_filename(title))
        session_stem = Path(filename).stem
        session_md = generate_session_log(api_response, meta)
        (sessions_dir / filename).write_text(session_md, encoding="utf-8")
        log.info(f"Session log: {filename}")

        # --- Decisions ---
        decisions = api_response.get("decisions", [])
        if decisions:
            entries = [generate_decision_entry(d, today, session_stem) for d in decisions]
            update_decisions_file(project_dir / "decisions.md", entries, project_name)
            log.info(f"Decisions: {len(decisions)} entries added")

        # --- _status.md (roadmap) ---
        roadmap_content = api_response.get("roadmap", "")
        if roadmap_content:
            (project_dir / "_status.md").write_text(roadmap_content, encoding="utf-8")
            log.info("Status/roadmap updated")

    else:
        # Fallback — no API
        log.warning("API failed, generating fallback session log")
        fallback_md = generate_fallback_session_log(messages, meta)
        title_text = messages[0].get("content", "untitled") if messages else "untitled"
        if isinstance(title_text, list):
            title_text = "untitled"
        title_slug = sanitize_filename(title_text[:30])
        filename = get_session_filename(str(sessions_dir), today, title_slug)
        (sessions_dir / filename).write_text(fallback_md, encoding="utf-8")
        log.info(f"Fallback session log: {filename}")

    log.info("obsidian-sync completed")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log.error(f"Unhandled exception: {e}")
    sys.exit(0)
```

- [ ] **Step 3: Run all tests**

```bash
cd ~/.claude/skills/obsidian-sync && python -m pytest tests/ -v
```

Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add bin/obsidian_sync.py
git commit -m "feat: main entry point with fallback and error handling"
```

---

### Task 7: SessionStart 컨텍스트 주입 스크립트

**Files:**
- Create: `bin/obsidian_context.py`

- [ ] **Step 1: Implement obsidian-context.py**

```python
#!/usr/bin/env python3
"""obsidian-context: SessionStart hook — inject Obsidian roadmap into Claude Code."""

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
        # Extract current_phase from frontmatter
        phase_match = re.search(r'current_phase:\s*"?([^"\n]+)"?', status_content)
        if phase_match:
            lines.append(f"현재 Phase: {phase_match.group(1)}")

        # Extract roadmap section
        roadmap_match = re.search(r'## 로드맵\n(.*?)(?=\n## |\Z)', status_content, re.DOTALL)
        if roadmap_match:
            roadmap = roadmap_match.group(1).strip()
            # Count completed/total
            total = len(re.findall(r'- \[[ x]\]', roadmap))
            done = len(re.findall(r'- \[x\]', roadmap))
            if total > 0:
                lines.append(f"진행률: {done}/{total}")
            lines.append("")
            lines.append(roadmap)

        # Extract workflow status if present
        wf_match = re.search(r'## 하이브리드 워크플로우 상태\n(.*?)(?=\n## |\Z)', status_content, re.DOTALL)
        if wf_match:
            lines.append("")
            lines.append("### 하이브리드 워크플로우 상태")
            lines.append(wf_match.group(1).strip())

        # Extract current session status
        cs_match = re.search(r'## 현재 세션 상태\n(.*?)(?=\n## |\Z)', status_content, re.DOTALL)
        if cs_match:
            lines.append("")
            lines.append("### 최근 세션 상태")
            lines.append(cs_match.group(1).strip())

    if decisions_content:
        # Extract last 3 decisions (## headers)
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
```

- [ ] **Step 2: Commit**

```bash
git add bin/obsidian_context.py
git commit -m "feat: SessionStart context injection script"
```

---

### Task 8: SKILL.md 스킬 정의

**Files:**
- Create: `SKILL.md`

- [ ] **Step 1: Create SKILL.md**

```markdown
---
name: obsidian-sync
version: 1.0.0
description: |
  Obsidian vault에 Claude Code 세션을 자동 기록하고 프로젝트 로드맵을 관리한다.
  Use when asked to "obsidian-setup", "obsidian setup", "옵시디언 설정",
  "obsidian-context", "옵시디언 현황", "로드맵 확인".
  (obsidian-sync)
user-invocable: true
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
  - Glob
  - AskUserQuestion
hooks:
  SessionEnd:
    - hooks:
        - type: command
          command: "python3 ${CLAUDE_SKILL_DIR}/bin/obsidian_sync.py"
          timeout: 30
  SessionStart:
    - hooks:
        - type: command
          command: "python3 ${CLAUDE_SKILL_DIR}/bin/obsidian_context.py"
          timeout: 10
---

# /obsidian-sync

Claude Code 세션을 Obsidian vault에 자동 기록하고 프로젝트 로드맵을 관리한다.

## 명령어

이 스킬은 두 가지 명령어를 제공한다:

### /obsidian-setup

프로젝트에 obsidian-sync를 설정한다. 아래 순서대로 실행:

1. **Vault 경로 확인/설정**
   - `~/.claude/obsidian.json` 확인. 없으면 사용자에게 vault 경로 질문
   - 기본값 제안: `C:\Users\{user}\Vault_Moku\claude-dev`

2. **요약 모델 선택**
   - haiku (기본, 저렴) vs sonnet (정확) 중 선택
   - 기본값: `claude-haiku-4-5-20251001`

3. **프로젝트 이름 추출**
   - `git remote get-url origin`에서 repo 이름 추출
   - fallback: 현재 디렉토리명
   - 사용자가 `--name` 인자로 오버라이드 가능

4. **컨텍스트 소스 자동 탐지**
   아래 경로를 탐지하고 결과를 출력:
   - gstack: `~/.gstack/projects/` 에서 매칭
   - superpowers: `docs/superpowers/specs/`, `docs/superpowers/plans/`
   - 범용: `docs/specs/`, `docs/plans/`, `docs/design/`, `docs/architecture/`, `docs/adr/`, `ROADMAP.md`, `TODO.md`, `PLAN.md`
   - `--context <path>` 인자로 커스텀 경로 추가

5. **설정 파일 생성**
   - `~/.claude/obsidian.json` (글로벌, 최초 1회)
   - `.claude/obsidian.json` (프로젝트별)

6. **Vault 폴더 구조 생성**
   - `vault/projects/{name}/sessions/` 디렉토리 생성

7. **dashboard.md 생성** (vault 루트에 없을 때만)
   - `templates/dashboard.md` 복사

8. **pip install anthropic** (없으면)

9. **완료 메시지** 출력

### /obsidian-context

현재 프로젝트의 Obsidian 로드맵을 읽어서 대화 컨텍스트에 주입한다.
`_status.md`와 `decisions.md`를 읽어서 요약한 내용을 출력한다.

실행 방법:
1. `~/.claude/obsidian.json`과 `.claude/obsidian.json` 읽기
2. vault에서 해당 프로젝트의 `_status.md` 읽기
3. vault에서 해당 프로젝트의 `decisions.md` 읽기
4. 로드맵 현황, 최근 결정, 워크플로우 상태를 요약해서 출력

## 설정 파일 구조

### 글로벌: ~/.claude/obsidian.json
```json
{
  "vault_path": "C:\\Users\\ymku0\\Vault_Moku\\claude-dev",
  "model": "claude-haiku-4-5-20251001",
  "api_timeout": 30,
  "max_transcript_tokens": 150000
}
```

### 프로젝트별: .claude/obsidian.json
```json
{
  "project_name": "project-name",
  "model": null,
  "gstack_slug": "slug-or-null",
  "include_gstack": true,
  "include_superpowers": true,
  "context_sources": [
    {"type": "type-name", "path": "relative/path"}
  ]
}
```
```

- [ ] **Step 2: Commit**

```bash
git add SKILL.md
git commit -m "feat: SKILL.md with /obsidian-setup and /obsidian-context"
```

---

### Task 9: README.md

**Files:**
- Create: `README.md`

- [ ] **Step 1: Create README.md**

```markdown
# obsidian-sync

Claude Code 세션을 Obsidian vault에 자동 기록하고 프로젝트 로드맵을 관리하는 Claude Code 스킬.

## Features

- **자동 세션 로그**: 세션 종료 시 transcript를 LLM으로 요약하여 Obsidian에 기록
- **로드맵 자동 관리**: 프로젝트 로드맵을 세션 내용에 맞춰 자동 업데이트
- **결정 추적**: 세션 중 내려진 결정을 자동 추출하여 누적 기록
- **세션 시작 컨텍스트**: 새 세션 시작 시 로드맵 현황을 자동 주입
- **하이브리드 워크플로우**: gstack + superpowers 산출물 연동
- **Dataview 대시보드**: 프로젝트 현황을 한눈에 확인

## Installation

```bash
git clone https://github.com/{user}/obsidian-sync ~/.claude/skills/obsidian-sync
```

## Setup

Claude Code에서:

```
/obsidian-setup
```

## Requirements

- Python 3.10+
- `anthropic` Python SDK
- `ANTHROPIC_API_KEY` 환경변수
- Obsidian + Dataview 플러그인 (대시보드용)

## Cost

- Haiku (기본): 세션당 ~$0.005-0.01
- Sonnet (선택): 세션당 ~$0.03-0.05
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: add README"
```

---

### Task 10: End-to-End 테스트

**Files:**
- No new files. Uses existing fixture + real vault path.

- [ ] **Step 1: Test obsidian-sync.py with sample transcript (dry run)**

Stdin을 파이프로 넘겨 실행. 실제 API 호출이 발생하므로 `ANTHROPIC_API_KEY`가 필요.

```bash
cd ~/.claude/skills/obsidian-sync

# 1. 먼저 글로벌 설정 생성 (테스트용 임시 경로)
python3 -c "
import json
from pathlib import Path
cfg = {
    'vault_path': str(Path.home() / 'Vault_Moku' / 'claude-dev'),
    'model': 'claude-haiku-4-5-20251001',
    'api_timeout': 30,
    'max_transcript_tokens': 150000
}
Path.home().joinpath('.claude', 'obsidian.json').write_text(json.dumps(cfg, indent=2))
print('Global config created')
"

# 2. 프로젝트 설정 생성 (테스트용)
mkdir -p /tmp/test-obsidian-project/.claude
python3 -c "
import json
cfg = {
    'project_name': 'test-project',
    'model': None,
    'gstack_slug': None,
    'include_gstack': False,
    'include_superpowers': False,
    'context_sources': []
}
with open('/tmp/test-obsidian-project/.claude/obsidian.json', 'w') as f:
    json.dump(cfg, f, indent=2)
print('Project config created')
"

# 3. 실행
echo '{"hook_event_name":"SessionEnd","session_id":"test-e2e-001","transcript_path":"'$HOME'/.claude/skills/obsidian-sync/tests/fixtures/sample_transcript.jsonl","cwd":"/tmp/test-obsidian-project"}' | python3 bin/obsidian_sync.py
```

- [ ] **Step 2: Verify output files exist**

```bash
ls -la ~/Vault_Moku/claude-dev/projects/test-project/sessions/
cat ~/Vault_Moku/claude-dev/projects/test-project/sessions/*.md
cat ~/Vault_Moku/claude-dev/projects/test-project/_status.md
cat ~/Vault_Moku/claude-dev/projects/test-project/decisions.md 2>/dev/null || echo "(no decisions)"
```

Expected:
- Session log `.md` 파일 생성됨
- `_status.md` 생성됨 (로드맵 포함)
- `ai_summary: true` in session log frontmatter

- [ ] **Step 3: Test obsidian-context.py**

```bash
echo '{"hook_event_name":"SessionStart","session_id":"test-ctx-001","cwd":"/tmp/test-obsidian-project"}' | python3 bin/obsidian_context.py
```

Expected: JSON with `systemMessage` containing roadmap context

- [ ] **Step 4: Test edge case — empty transcript (< 3 messages)**

```bash
echo '{"hook_event_name":"SessionEnd","session_id":"test-short","transcript_path":"/dev/null","cwd":"/tmp/test-obsidian-project"}' | python3 bin/obsidian_sync.py
echo "Exit code: $?"
```

Expected: Exit 0, no files created, log says "Session too short"

- [ ] **Step 5: Test edge case — no config**

```bash
echo '{"hook_event_name":"SessionEnd","session_id":"test-nocfg","transcript_path":"tests/fixtures/sample_transcript.jsonl","cwd":"/tmp/no-config-here"}' | python3 bin/obsidian_sync.py
echo "Exit code: $?"
```

Expected: Exit 0, silent (no config = not configured)

- [ ] **Step 6: Clean up test artifacts and commit**

```bash
rm -rf /tmp/test-obsidian-project
rm -rf ~/Vault_Moku/claude-dev/projects/test-project
git add -A
git commit -m "test: end-to-end verification complete"
```

---

### Task 11: Git repo 초기화 + 최종 정리

**Files:**
- Modify: `.gitignore`

- [ ] **Step 1: Initialize git repo if not already**

```bash
cd ~/.claude/skills/obsidian-sync
git init
```

- [ ] **Step 2: Create .gitignore**

```text
__pycache__/
*.pyc
.pytest_cache/
*.egg-info/
dist/
build/
```

- [ ] **Step 3: Final commit with all files**

```bash
git add -A
git commit -m "feat: obsidian-sync v1.0.0 — complete skill"
```

- [ ] **Step 4: Verify final directory structure**

```bash
find . -not -path './.git/*' -not -path './.git' | sort
```

Expected:
```
.
./SKILL.md
./README.md
./requirements.txt
./.gitignore
./bin/obsidian_sync.py
./bin/obsidian_context.py
./docs/design.md
./docs/plan.md
./prompts/summarize.txt
./prompts/roadmap_rules.txt
./templates/dashboard.md
./tests/test_parse.py
./tests/test_writers.py
./tests/fixtures/sample_transcript.jsonl
```
