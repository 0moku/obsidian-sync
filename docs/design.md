# obsidian-sync Design Spec

> Claude Code 세션을 Obsidian vault에 자동 기록하고 프로젝트 로드맵을 관리하는 스킬

**Date:** 2026-04-06
**Status:** Approved

---

## 1. 전체 아키텍처

```
┌─────────────────────────────────────────────────────┐
│ Claude Code Session                                  │
│                                                      │
│  SessionEnd hook → python obsidian-sync.py           │
│      ↓                                               │
│  Parse JSONL transcript → Claude API (Haiku) → .md   │
│                                                      │
│  SessionStart hook → python obsidian-context.py      │
│      ↓                                               │
│  _status.md 읽기 → systemMessage로 컨텍스트 주입      │
└─────────────────────────────────────────────────────┘

생성/업데이트 파일:
  vault/projects/{project}/sessions/YYYY-MM-DD_{title}_{n}.md  (신규)
  vault/projects/{project}/decisions.md                        (append)
  vault/projects/{project}/_status.md                         (덮어쓰기)
  vault/dashboard.md                                          (Dataview, 최초 1회)
```

### 구성 요소

| 구성 요소 | 위치 | 역할 |
|-----------|------|------|
| `obsidian-sync.py` | `~/.claude/skills/obsidian-sync/bin/` | SessionEnd hook. transcript → API → .md |
| `obsidian-context.py` | `~/.claude/skills/obsidian-sync/bin/` | SessionStart hook. _status.md → systemMessage |
| `SKILL.md` | `~/.claude/skills/obsidian-sync/` | `/obsidian-setup`, `/obsidian-context` 커맨드 |
| `~/.claude/obsidian.json` | 글로벌 | vault 경로, 기본 모델 |
| `.claude/obsidian.json` | 프로젝트별 | 프로젝트 이름, 컨텍스트 소스 |

### 양방향 흐름

```
세션 종료 → Obsidian vault에 기록 (SessionEnd)
세션 시작 ← Obsidian vault에서 컨텍스트 주입 (SessionStart)
```

---

## 2. 데이터 흐름 — transcript → 요약

### Step 1: Hook input 수신

```json
{
  "hook_event_name": "SessionEnd",
  "session_id": "xxx",
  "transcript_path": "/path/to/transcript.jsonl",
  "cwd": "/path/to/project"
}
```

### Step 2: JSONL 파싱

transcript에서 추출하는 정보:
- 사용자 메시지 전체 (첫 메시지 → 제목 후보)
- 어시스턴트 텍스트 응답 전체
- tool_use 목록 (도구 이름 + 대상 파일)
- 세션 시작/종료 timestamp
- git branch, cwd

### Step 3: 토큰 관리 (API 전송 전 전처리)

제거 대상:
- `thinking` 블록 (시그니처 + 내부 추론)
- `tool_result` 내용 → `"Read: path/to/file (200 lines)"` 형태로 축약
- `progress`, `system`, `file-history-snapshot` 타입

보존 대상:
- 사용자 메시지
- 어시스턴트 텍스트
- tool_use 이름 + input

토큰 초과 시 앞부분(오래된 메시지)부터 잘라냄. 대부분의 세션은 Haiku 200k 컨텍스트 안에 수용.

### Step 4: Claude API 호출

하나의 API 호출로 구조화된 JSON 수신:

```json
{
  "title": "세션 제목 (한글, 30자 이내)",
  "summary": "요약 (2-3문장)",
  "key_activities": ["주요 활동 목록"],
  "files_changed": ["변경 파일 경로"],
  "decisions": [
    {
      "title": "결정 제목",
      "decision": "무엇을 결정했는지",
      "alternatives": "기각된 대안과 이유",
      "rationale": "근거"
    }
  ],
  "status": {
    "completed": ["완료"],
    "in_progress": ["진행 중"],
    "blockers": ["블로커"],
    "next_steps": ["다음 할 일"]
  },
  "tags": ["태그"],
  "workflow": ["사용된 워크플로우 단계"],
  "task_size": "S|M|L|null"
}
```

### Step 5: 추가 입력 (로드맵 업데이트용)

API 호출 시 함께 전달:

| 입력 | 용도 | 필수 |
|------|------|------|
| 기존 `_status.md` | 로드맵 현행 상태 | 있으면 |
| 압축된 transcript | 세션 내용 | 필수 |
| `git diff --stat` | 실제 변경 파일 | 필수 |
| context_sources 파일들 | spec/plan 문서 | 있으면 |
| gstack CEO plans | Phase 기획 | 있으면 |
| gstack learnings | 누적 학습 | 있으면 |

존재하는 소스만 포함. gstack/superpowers 없는 프로젝트에서도 정상 동작.

---

## 3. 생성 파일 포맷

### 3-1. 세션 로그 — `sessions/YYYY-MM-DD_{title}_{n}.md`

```markdown
---
date: 2026-04-06
project: kooing-screen
duration_min: 45
model: claude-opus-4-6
tags: [battery, scoring, bug]
workflow: [plan-eng-review, subagent-driven-development]
task_size: M
session_id: abc123
ai_summary: true
---
# 배터리 채점 로직 버그 수정

## 요약
배터리 채점 서비스에서 MLU 계산이 어절 단위가 아닌 음절 단위로
되어 있던 버그를 수정했다.

## 주요 활동
- battery_scoring.py에서 MLU 계산 로직 수정
- 테스트 케이스 3건 추가
- seed 데이터 업데이트

## 변경된 파일
- `server/app/services/battery_scoring.py`
- `server/tests/test_battery.py`
- `supabase/seed/battery_items.sql`

## 결정 사항
### MLU 계산 단위를 어절로 변경
- **결정**: 음절 → 어절 기준으로 전환
- **대안**: 음절 유지 (K-DST 원본 방식이지만 우리 데이터에 안 맞음)
- **근거**: 수집 데이터가 어절 단위로 전사되어 있음

## 상태
- ✅ MLU 계산 로직 수정
- ✅ 테스트 통과
- 🔲 프로덕션 배포 필요
```

`{n}`은 같은 날짜+제목 충돌 시 증분 번호. 대부분 생략.

### 3-2. decisions.md — append-only, 최신이 위

```markdown
---
project: kooing-screen
updated: 2026-04-06
---
# 결정 로그

## 2026-04-06: MLU 계산 단위를 어절로 변경
- **결정**: 음절 → 어절 기준으로 전환
- **대안**: 음절 유지 (기각: 수집 데이터와 불일치)
- **근거**: 수집 데이터가 어절 단위로 전사되어 있음
- **세션**: [[2026-04-06_배터리-채점-로직-버그-수정]]

## 2026-04-05: 규준 중심 채점 전략 채택
- ...
```

새 결정은 `# 결정 로그` 바로 아래에 삽입. 프론트매터 `updated` 갱신.

### 3-3. _status.md — 매 세션마다 덮어쓰기

```markdown
---
project: kooing-screen
updated: 2026-04-06
status: active
current_phase: "Phase 2: 채점 + 리포트"
last_session: "[[2026-04-06_배터리-채점-로직-버그-수정]]"
tags: [flutter, fastapi, supabase]
---
# kooing-screen 현황

## 로드맵
### Phase 1: 구조화 선별검사 MVP ✅
- [x] 배터리 문항 DB 설계 + seed
- [x] 개별 테스트 플로우 (Hub → Task → TaskComplete)
- [x] 부모 설문 UI
- [x] 진행률 추적 (GET /progress)

### Phase 2: 채점 + 리포트 🔄
- [x] MLU/NDW 동시 추출 로직
- [x] MLU 어절 단위 버그 수정
- [ ] 규준 테이블 DB 적재
  - [ ] K-DST 규준 데이터 정리
  - [ ] 규준 비교 API
- [ ] 종합 리포트 생성 API
- [ ] 리포트 PDF 출력
- ~~어휘 과제 수동 채점~~ (2026-04-05: 데이터 기반 자동 채점으로 전환)

### Phase 3: 치료사 연동
- [ ] 치료사 대시보드 UI
- [ ] AI 품질 Ground Truth 수집 플로우
- [ ] 치료사 피드백 → 모델 개선 파이프라인

## 하이브리드 워크플로우 상태
- 최근 CEO plan: "채점 리포트 MVP" (2026-04-05)
- 최근 eng review: "규준 테이블 아키텍처" (2026-04-06)
- 다음 워크플로우 단계: superpowers brainstorming → writing-plans

## 현재 세션 상태
### 완료
- MLU 계산 로직 수정
- 테스트 케이스 추가

### 진행 중
- 규준 테이블 설계

### 블로커
- (없음)

### 다음 할 일
- 규준 테이블 DB 적재
- 종합 리포트 API 설계
```

### 3-4. dashboard.md — Dataview 쿼리, 최초 1회 생성

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

Python 스크립트가 dashboard.md를 이후 수정하지 않음. Dataview가 실시간 렌더링.

---

## 4. 로드맵 상세 설계

로드맵은 이 시스템의 핵심 기능. 자동으로 진화하되 안전하게.

### 4-1. LLM 로드맵 업데이트 규칙

```
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
```

### 4-2. 로드맵 자동 생성

`/obsidian-setup` 시 로드맵 입력을 요구하지 않는다. 첫 SessionEnd 시 LLM이 transcript + 프로젝트 구조를 보고 초안을 자동 생성. 이후 세션마다 점진적으로 진화.

### 4-3. Phase 상태 이모지

| 이모지 | 의미 |
|--------|------|
| ✅ | 모든 하위 태스크 완료 |
| 🔄 | 진행 중 (하나 이상 완료, 하나 이상 미완료) |
| (없음) | 미착수 |

`current_phase` 프론트매터는 🔄 Phase로 자동 설정.

---

## 5. 하이브리드 워크플로우 연동

gstack(기획/리뷰/QA/배포) + superpowers(brainstorming→plan→subagent 구현) 산출물을 로드맵과 세션 로그에 반영.

### 5-1. 참조 산출물 경로

```
gstack:
  ~/.gstack/projects/{slug}/ceo-plans/          → Phase 기획
  ~/.gstack/projects/{slug}/*-eng-review-*.md   → 아키텍처 결정
  ~/.gstack/projects/{slug}/learnings.jsonl      → 누적 학습

superpowers:
  docs/superpowers/specs/*-design.md            → 기능 설계
  docs/superpowers/plans/*-plan.md              → 구현 계획
```

### 5-2. 로드맵 자동 반영 시나리오

| 워크플로우 이벤트 | 로드맵 반영 |
|---|---|
| CEO plan 생성 | 새 Phase/태스크 추가 |
| eng review 생성 | 기술 제약/하위 태스크 세분화 |
| superpowers spec 생성 | 설계 완료 체크, 구현 태스크 추가 |
| subagent-driven-development | 구현 완료 태스크 체크 |
| `/review`, `/qa` 실행 | 리뷰/QA 태스크 자동 추가+체크 |
| `/ship` 실행 | 배포 태스크 체크, 다음 Phase 전환 |

### 5-3. 세션 로그 워크플로우 태깅

프론트매터 `workflow` 필드로 Dataview 필터링 가능:

```dataview
TABLE date, workflow, tags
FROM "claude-dev/projects/kooing-screen/sessions"
WHERE contains(workflow, "plan-ceo-review")
SORT date DESC
```

---

## 6. 스킬 구조 + 설정

### 6-1. 디렉토리 구조 (GitHub repo)

```
obsidian-sync/
├── SKILL.md                    # 스킬 정의
├── bin/
│   ├── obsidian-sync.py        # SessionEnd hook
│   ├── obsidian-context.py     # SessionStart hook
│   └── setup.py                # /obsidian-setup 헬퍼
├��─ prompts/
│   ├── summarize.txt           # LLM 요약 프롬프트
│   └── roadmap_rules.txt       # 로드맵 업데이트 규칙
├── templates/
│   └── dashboard.md            # Dataview 쿼리 템플릿
├── docs/
│   └── design.md               # 이 문서
├── requirements.txt            # anthropic
└── README.md
```

### 6-2. SKILL.md 정의

```yaml
---
name: obsidian-sync
version: 1.0.0
description: |
  Obsidian vault에 Claude Code 세션을 자동 기록하고 프로젝트 로드맵을 관리한다.
  Use when asked to "obsidian-setup", "obsidian setup", "옵시디언 설정",
  "obsidian-context", "옵시디언 현황", "로드맵 확인".
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
  - Glob
hooks:
  SessionEnd:
    - hooks:
        - type: command
          command: "python ${CLAUDE_SKILL_DIR}/bin/obsidian-sync.py"
          timeout: 30
  SessionStart:
    - hooks:
        - type: command
          command: "python ${CLAUDE_SKILL_DIR}/bin/obsidian-context.py"
          timeout: 10
---
```

### 6-3. 설정 파일

**글로벌** — `~/.claude/obsidian.json`:

```json
{
  "vault_path": "C:\\Users\\ymku0\\Vault_Moku\\claude-dev",
  "model": "claude-haiku-4-5-20251001",
  "api_timeout": 30,
  "max_transcript_tokens": 150000
}
```

**프로젝트별** — `.claude/obsidian.json`:

```json
{
  "project_name": "kooing-screen",
  "model": null,
  "gstack_slug": "0moku-kooing-screen",
  "include_gstack": true,
  "include_superpowers": true,
  "context_sources": [
    {"type": "superpowers_specs", "path": "docs/superpowers/specs"},
    {"type": "superpowers_plans", "path": "docs/superpowers/plans"},
    {"type": "adr", "path": "docs/adr"},
    {"type": "roadmap", "path": "ROADMAP.md"}
  ]
}
```

프로젝트별 `model`이 null이면 글로벌 설정 사용.

### 6-4. `/obsidian-setup` 실행 흐름

```
1. Vault 경로 설정
   - 기본값: ~/.claude/obsidian.json에서 읽기, 없으면 사용자 입력

2. 요약 모델 선택
   - 기본값: haiku
   - 선택지: haiku, sonnet

3. 프로젝트 이름 자동 추출
   - git remote origin → repo 이름
   - fallback: 현재 디렉토리명
   - --name 옵션으로 오버라이드

4. 자동 탐지
   a. gstack — ~/.gstack/projects/ 매칭
   b. superpowers — docs/superpowers/specs/, docs/superpowers/plans/
   c. 범용 계획/설계 문서:
      - docs/specs/
      - docs/plans/
      - docs/design/
      - docs/architecture/
      - docs/adr/
      - .github/ROADMAP.md
      - ROADMAP.md
      - TODO.md
      - PLAN.md
   d. --context 옵션으로 커스텀 경로 추가

5. 탐지 결과 요약 출력
   "gstack: 0moku-kooing-screen ✓
    superpowers specs: 3개 ✓
    superpowers plans: 2개 ✓
    CEO plans: 2개 ✓
    docs/adr/: 탐지 안 됨"

6. ~/.claude/obsidian.json 생성 (최초 1회)
7. .claude/obsidian.json 생성 (탐지 결과 반영)
8. Vault 내 폴더 구조 생성
   vault/projects/{name}/sessions/
9. dashboard.md 생성 (없을 때만)
10. pip install anthropic (없으면)
11. 완료 메시지
```

### 6-5. 새 PC 셋업

```bash
# 1. 스킬 설치
git clone https://github.com/{user}/obsidian-sync ~/.claude/skills/obsidian-sync

# 2. 프로젝트에서 셋업
cd ~/dev_projects/langdevtest
# Claude Code 실행 후:
/obsidian-setup
```

두 줄이면 끝. 이후 세션부터 자동 기록 시작.

---

## 7. SessionStart 컨텍스트 주입

### 7-1. 동작

세션 시작 시 `obsidian-context.py`가 `_status.md`를 읽어서 systemMessage로 반환.

### 7-2. 주입 포맷

```
## 프로젝트 로드맵 (Obsidian 기준)
현재 Phase: Phase 2 — 채점 + 리포트 (4/6 완료)

### 하이브리드 워크플로우 상태
- 최근 CEO plan: "채점 리포트 MVP" (2026-04-05)
- 최근 eng review: "규준 테이블 아키텍처" (2026-04-06)
- 다음 워크플로우 단계: superpowers brainstorming → writing-plans

### 최근 완료
- MLU 어절 단위 버그 수정 (2026-04-06)

### 미완료 (우선순위순)
1. 규준 테이블 DB 적재 → K-DST 규준 데이터 정리, 규준 비교 API
2. 종합 리포트 생성 API
3. 리포트 PDF 출력

### 최근 결정 (3건)
- MLU 어절 단위 전환 (2026-04-06)
- 규준 중심 채점 전략 채택 (2026-04-05)
- 치료사를 Ground Truth 제공자로 피벗 (2026-04-03)
```

### 7-3. `/obsidian-context` 수동 호출

세션 중 로드맵을 다시 확인하고 싶을 때 수동으로 호출. _status.md를 읽어서 대화 컨텍스트에 주입.

---

## 8. 에러 처리

### 8-1. API 실패

```
1회 재시도 (3초 대기)
→ 재실패 시 fallback 세션 로그 생성:
  - transcript에서 기계적 추출만 (사용자 메시지 목록, 변경 파일)
  - 프론트매터에 ai_summary: false
  - _status.md, decisions.md 업데이트 안 함
→ stderr에 에러 로그
```

### 8-2. Transcript 너무 짧음

```
메시지 3개 미만 → 세션 로그 생성 안 함, exit 0
```

### 8-3. Vault 경로 없음

```
vault_path 디렉토리가 존재하지 않음
→ 자동 생성 안 함 (Obsidian vault 삭제/이동 가능성)
→ stderr 경고, exit 0
```

### 8-4. 동시 세션

```
같은 프로젝트에서 동시 종료 시:
- 세션 로그: session_id 해시로 파일명 충돌 방지
- _status.md: 마지막 쓰기가 이김 (허용 가능)
- decisions.md: append 방식이라 양쪽 다 기록
```

### 8-5. 설정 파일 없음

```
~/.claude/obsidian.json 없음 → exit 0 (미설정 프로젝트)
.claude/obsidian.json 없음 → exit 0
```

### 8-6. Hook 원칙

- **절대 실패하지 않는다** — 모든 예외 catch, exit 0
- **타임아웃** — SessionEnd 30초, SessionStart 10초
- **로그** — `~/.claude/obsidian-sync.log`에 에러 기록

---

## 설계 결정 요약

| 결정 | 선택 | 근거 |
|------|------|------|
| LLM 모델 | 설정 가능, 기본 Haiku | 비용/품질 밸런스, 환경변수로 오버라이드 |
| 프로젝트 이름 | git remote 자동 + --name 오버라이드 | 자동화 + 사람이 읽기 좋은 이름 |
| 자동 처리 범위 | 전부 자동 (로그+결정+상태+로드맵) | 수동 트리거는 결국 안 쓰게 됨 |
| Vault 위치 | 기존 vault 하위 폴더 | 기본: Vault_Moku/claude-dev/ |
| Dashboard | Dataview 쿼리 | 실시간 렌더링, 스크립트가 관리 안 해도 됨 |
| 로드맵 관리 | LLM 자동 진화 + 안전장치 | 초기 입력 불필요, 취소선 정책 |
| 아키텍처 | 단일 Python 스크립트 | 이 규모에서 모듈화는 과잉 |
| API 비용 | anthropic SDK 직접 호출 | 월 ~$1-2, 구독과 별개 |
| 스킬 배포 | GitHub repo | 새 PC에서 clone 한 줄 |
| 범용성 | gstack/superpowers 없어도 동작 | 범용 계획 문서 자동 탐지 |
