# obsidian-sync Design Spec

> Claude Code 세션을 Obsidian vault에 기록하고 프로젝트 로드맵을 관리하는 스킬

**Date:** 2026-04-06
**Status:** Approved
**Version:** 2.0 — 반자동 (구독 모델)

---

## 1. 전체 아키텍처

```
┌─────────────────────────────────────────────────────┐
│ Claude Code Session                                  │
│                                                      │
│  PostToolUse hook → obsidian_backup.py               │
│      ↓                                               │
│  pending.json 저장 (매 tool use)                     │
│                                                      │
│  SessionStart hook → obsidian_context.py             │
│      ↓                                               │
│  status.md 읽기 + pending 리마인더 → systemMessage   │
│                                                      │
│  /obsidian-sync (수동) → Claude Code가 직접 .md 생성  │
│      ↓                                               │
│  세션 로그 + decisions.md + status.md 갱신            │
└─────────────────────────────────────────────────────┘

생성/업데이트 파일:
  vault/projects/{project}/sessions/YYYY-MM-DD_{title}.md  (신규)
  vault/projects/{project}/decisions.md                    (append)
  vault/projects/{project}/status.md                       (덮어쓰기)
  vault/dashboard.md                                       (Dataview, 최초 1회)
```

### v1 → v2 변경점

| 항목 | v1 (자동/API) | v2 (반자동/구독) |
|------|---------------|------------------|
| 동기화 트리거 | SessionEnd hook (자동) | `/obsidian-sync` (수동) |
| 요약 주체 | Python → Anthropic API (Haiku) | Claude Code 세션 자체 |
| 비용 | API 토큰 과금 | 구독에 포함 |
| 의존성 | anthropic SDK, ANTHROPIC_API_KEY | 없음 |
| 백업 | PostToolUse 10분 throttle | PostToolUse 매 tool use |
| SessionStart | 로드맵 주입만 | 로드맵 주입 + pending 리마인더 |
| obsidian_sync.py | SessionEnd hook 스크립트 | 삭제 (SKILL.md로 대체) |

### 구성 요소

| 구성 요소 | 위치 | 역할 |
|-----------|------|------|
| `obsidian_backup.py` | `bin/` | PostToolUse hook. pending.json 저장 |
| `obsidian_context.py` | `bin/` | SessionStart hook. 로드맵 주입 + pending 리마인더 |
| `SKILL.md` | 루트 | `/obsidian-sync`, `/obsidian-setup`, `/obsidian-context` |
| `~/.claude/obsidian.json` | 글로벌 | vault 경로 |
| `.claude/obsidian.json` | 프로젝트별 | 프로젝트 이름, 컨텍스트 소스 |

### 흐름

```
매 tool use → pending.json 저장 (백업)
세션 시작 → 로드맵 주입 + "이전 세션 미정리" 리마인더
사용자 → /obsidian-sync → Claude Code가 직접 vault에 .md 생성
```

---

## 2. 데이터 흐름

### PostToolUse → obsidian_backup.py

매 tool use마다 실행. `~/.claude/obsidian-pending.json`에 현재 세션 정보 저장:

```json
{
  "transcript_path": "/path/to/transcript.jsonl",
  "session_id": "xxx",
  "cwd": "/path/to/project",
  "backup_time": "2026-04-06T10:30:00+00:00"
}
```

### SessionStart → obsidian_context.py

세션 시작 시:
1. `status.md` + `decisions.md` 읽어서 로드맵 컨텍스트 주입
2. `obsidian-pending.json` 존재하면 리마인더 추가:
   ```
   ## Obsidian Sync 알림
   이전 세션(2026-04-06 10:30:00 UTC, id:abc12345)이 아직 정리되지 않았습니다.
   `/obsidian-sync`로 정리할 수 있습니다.
   ```

### /obsidian-sync (수동)

사용자가 명령하면 Claude Code가 직접:
1. 현재 대화 내용을 분석 (transcript 파싱 불필요 — 이미 컨텍스트에 있음)
2. `git diff --stat` 참조
3. 기존 `status.md` 읽기
4. 세션 로그 .md 생성
5. `decisions.md` 업데이트 (결정 있으면)
6. `status.md` 갱신
7. `pending.json` 삭제

---

## 3. 생성 파일 포맷

### 3-1. 세션 로그 — `sessions/YYYY-MM-DD_{title}.md`

```markdown
---
date: 2026-04-06
project: kooing-screen
tags: [battery, scoring, bug]
workflow: [plan-eng-review, subagent-driven-development]
task_size: M
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
- 완료: MLU 계산 로직 수정, 테스트 통과
- 진행 중: 규준 테이블 설계
- 다음 할 일: 규준 테이블 DB 적재, 종합 리포트 API 설계
```

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
```

### 3-3. status.md — 매 sync마다 덮어쓰기

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
...

### Phase 2: 채점 + 리포트 🔄
- [x] MLU/NDW 동시 추출 로직
- [ ] 규준 테이블 DB 적재
...

## 현재 세션 상태
### 완료
- MLU 계산 로직 수정

### 진행 중
- 규준 테이블 설계

### 다음 할 일
- 규준 테이블 DB 적재
```

### 3-4. dashboard.md — Dataview 쿼리, 최초 1회 생성

Python이 관리하지 않음. Dataview가 실시간 렌더링.

---

## 4. 로드맵 업데이트 규칙

1. **완료 판정**: 실제로 구현+테스트 통과 확인된 항목만 `[x]`
2. **항목 추가**: 새 작업이 언급되었거나 spec에 있으면 추가
3. **항목 제거**: 절대 삭제 안 함. 취소선 + 사유
4. **Phase 변경**: 새 Phase 추가 허용, 기존 변경은 명시적 논의 시만
5. **순서**: 의존성 순서, 완료 → 진행 중 → 미착수
6. **세분화**: 2단계까지 (Phase > 태스크 > 하위 태스크)
7. **기존 존중**: 근거 없이 임의 수정 금지

---

## 5. 하이브리드 워크플로우 연동

gstack + superpowers 산출물을 로드맵과 세션 로그에 반영.
v2에서도 동일하게 context_sources로 참조.

### 참조 산출물 경로

```
gstack:
  ~/.gstack/projects/{slug}/ceo-plans/
  ~/.gstack/projects/{slug}/*-eng-review-*.md
  ~/.gstack/projects/{slug}/learnings.jsonl

superpowers:
  docs/superpowers/specs/*-design.md
  docs/superpowers/plans/*-plan.md
```

---

## 6. 스킬 구조 + 설정

### 6-1. 디렉토리 구조

```
obsidian-sync/
├── SKILL.md                    # 스킬 정의 (v2: 동기화 로직 포함)
├── bin/
│   ├── obsidian_backup.py      # PostToolUse hook — pending.json 저장
│   └── obsidian_context.py     # SessionStart hook — 로드맵 + 리마인더
├── templates/
│   └── dashboard.md            # Dataview 쿼리 템플릿
├── tests/
│   ├── test_parse.py
│   └── test_writers.py
├── docs/
│   └── design.md               # 이 문서
└── README.md
```

### 6-2. 설정 파일

**글로벌** — `~/.claude/obsidian.json`:
```json
{
  "vault_path": "C:\\Users\\ymku0\\Vault_Moku\\claude-dev"
}
```

**프로젝트별** — `.claude/obsidian.json`:
```json
{
  "project_name": "kooing-screen",
  "gstack_slug": "0moku-kooing-screen",
  "include_gstack": true,
  "include_superpowers": true,
  "context_sources": [
    {"type": "superpowers_specs", "path": "docs/superpowers/specs"},
    {"type": "superpowers_plans", "path": "docs/superpowers/plans"}
  ]
}
```

### 6-3. 새 PC 셋업

```bash
git clone https://github.com/{user}/obsidian-sync ~/.claude/skills/obsidian-sync
cd ~/project && claude  # /obsidian-setup
```

v1 대비 제거된 것: `pip install anthropic`, `ANTHROPIC_API_KEY` 설정

---

## 7. 에러 처리

### 7-1. pending.json 저장 실패
조용히 무시. exit 0.

### 7-2. Vault 경로 없음
vault_path 미존재 → stderr 경고, exit 0.

### 7-3. 설정 파일 없음
`~/.claude/obsidian.json` 또는 `.claude/obsidian.json` 없음 → exit 0.

### 7-4. Hook 원칙
- **절대 실패하지 않는다** — 모든 예외 catch, exit 0
- **타임아웃** — PostToolUse 5초, SessionStart 10초

---

## 설계 결정 요약

| 결정 | 선택 | 근거 |
|------|------|------|
| 동기화 방식 | 반자동 (수동 트리거) | 구독 모델 호환, API 불필요 |
| 요약 주체 | Claude Code 세션 내 | 더 높은 품질 (Opus), 대화 컨텍스트 이미 보유 |
| 백업 주기 | 매 tool use | pending.json은 50B 포인터, I/O 무해 |
| 리마인더 | SessionStart시 pending 체크 | 까먹지 않되 강제하지 않음 |
| obsidian_sync.py | 삭제 | SKILL.md 프롬프트로 대체, 코드 절반 제거 |
| API 의존성 | 제거 | anthropic SDK, API key 불필요 |
| 설정 단순화 | model, api_timeout 제거 | 외부 API 없으므로 불필요 |
