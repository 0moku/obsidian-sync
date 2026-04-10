---
name: obsidian-sync
version: 2.0.0
description: |
  Obsidian vault에 Claude Code 세션을 기록하고 프로젝트 로드맵을 관리한다.
  Use when asked to "obsidian-sync", "옵시디언 동기화", "세션 정리",
  "obsidian-setup", "obsidian setup", "옵시디언 설정",
  "obsidian-context", "옵시디언 현황", "로드맵 확인".
  (obsidian-sync)
user-invocable: true
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
  - Glob
  - Grep
  - AskUserQuestion
hooks:
  PostToolUse:
    - matcher: "Bash"
      hooks:
        - type: command
          command: "python ~/.claude/skills/obsidian-sync/bin/obsidian_backup.py"
          timeout: 5
  SessionStart:
    - hooks:
        - type: command
          command: "python ~/.claude/skills/obsidian-sync/bin/obsidian_context.py"
          timeout: 10
---

# /obsidian-sync

Claude Code 세션을 Obsidian vault에 기록하고 프로젝트 로드맵을 관리한다.

## 아키텍처 — 반자동 (구독 모델)

```
PostToolUse hook → obsidian_backup.py → pending.json 저장 (매 tool use)
SessionStart hook → obsidian_context.py → 로드맵 주입 + pending 리마인더
/obsidian-sync → Claude Code가 직접 vault에 .md 생성 (API 불필요)
```

- 요약은 Claude Code 세션 내에서 직접 수행 (외부 API 호출 없음)
- 구독 요금제로 커버, ANTHROPIC_API_KEY 불필요
- 사용자가 원할 때 `/obsidian-sync`로 트리거

## 명령어

### /obsidian-sync

현재 세션의 내용을 Obsidian vault에 기록한다. 아래 순서대로 실행:

1. **설정 로드**
   - `~/.claude/obsidian.json` (vault_path)
   - `.claude/obsidian.json` (project_name, context_sources)
   - 없으면 `/obsidian-setup` 안내

2. **현재 세션 분석** — 이 대화의 내용을 직접 분석
   - 세션에서 한 작업 요약
   - 주요 활동 목록
   - 변경된 파일 (git diff --stat 참조)
   - 결정 사항 (있으면)
   - 현재 상태 (완료/진행 중/블로커/다음 할 일)

3. **세션 로그 생성** — `vault/projects/{name}/sessions/YYYY-MM-DD_{title}.md`

   ```markdown
   ---
   date: YYYY-MM-DD
   project: {project_name}
   tags: [관련, 태그]
   workflow: [사용된 워크플로우]
   task_size: S|M|L
   ---
   # 세션 제목 (한글, 30자 이내)

   ## 요약
   2-3문장 요약

   ## 주요 활동
   - 활동 1
   - 활동 2

   ## 변경된 파일
   - `path/to/file`

   ## 결정 사항
   ### 결정 제목
   - **결정**: 무엇을 결정했는지
   - **대안**: 기각된 대안과 이유
   - **근거**: 근거

   ## 상태
   - 완료: ...
   - 진행 중: ...
   - 다음 할 일: ...
   ```

4. **decisions.md 업데이트** (결정 사항이 있을 때만)
   - `vault/projects/{name}/decisions.md`
   - `# 결정 로그` 바로 아래에 새 결정 삽입 (최신이 위)
   - 프론트매터 `updated` 갱신
   - 파일 없으면 새로 생성

5. **status.md 업데이트** (덮어쓰기)
   - `vault/projects/{name}/status.md`
   - 기존 status.md를 읽고, 이번 세션 결과를 반영하여 갱신
   - 로드맵 업데이트 규칙 (아래) 준수

6. **도메인 카테고리 체크**
   - `.claude/obsidian.json`에 `domain_categories`가 없거나 비어있으면:
     1. 현재 세션 컨텍스트 분석 (우선) — 어떤 도메인 주제가 논의되었는지 파악
     2. 코드베이스 분석 — 프로젝트 구조에서 도메인 영역 감지
     3. 두 소스를 종합해서 카테고리 추천 (각각 `id`, `label`, `description` 포함)
     4. 사용자에게 제시 → 승인/수정 → `.claude/obsidian.json`의 `domain_categories`에 저장
   - 이미 설정되어 있으면:
     1. 세션에서 기존 카테고리에 해당하지 않는 새로운 도메인 주제가 논의되었는지 확인
     2. 새 카테고리가 권장되면 추천 → 승인 시 추가
     3. 해당 없으면 스킵 (질문 없이 진행)

7. **도메인 노트 업데이트**
   - 각 카테고리에 대해:
     1. 이번 세션에서 해당 카테고리 관련 변경이 있었는지 판단
        - 변경 판단 기준 (둘 중 하나 이상): 세션에서 해당 도메인을 논의했음 / `git diff`에 관련 파일이 포함됨
     2. 변경이 없으면 스킵
     3. 변경이 있으면:
        - 기존 노트 파일 읽기 (파일 존재 시)
        - `## 메모` 이하 텍스트를 별도 변수에 보존
        - 코드베이스 + 세션 컨텍스트에서 최신 정보 추출
        - `## 메모` 위 섹션 재생성 + 보존한 `## 메모` 이하 복원하여 파일 작성
        - 코드에서 사라진 항목은 frontmatter에 `status: deprecated`, `deprecated_reason`, `deprecated_date` 설정
     4. 새로 감지된 항목은 도메인 노트 형식에 따라 새 파일 생성
   - vault에 `domain/{category_id}/` 디렉토리가 없으면 생성

8. **pending.json 삭제**
   - `~/.claude/obsidian-pending.json` 삭제하여 다음 세션 리마인더 방지

9. **완료 메시지** 출력

### /obsidian-setup

프로젝트에 obsidian-sync를 설정한다. 아래 순서대로 실행:

1. **Vault 경로 확인/설정**
   - `~/.claude/obsidian.json` 확인. 없으면 사용자에게 vault 경로 질문
   - 기본값 제안: `C:\Users\{user}\Vault_Moku\claude-dev`

2. **프로젝트 이름 추출**
   - `git remote get-url origin`에서 repo 이름 추출
   - fallback: 현재 디렉토리명
   - 사용자가 `--name` 인자로 오버라이드 가능

3. **컨텍스트 소스 자동 탐지**
   아래 경로를 탐지하고 결과를 출력:
   - gstack: `~/.gstack/projects/` 에서 매칭
   - superpowers: `docs/superpowers/specs/`, `docs/superpowers/plans/`
   - 범용: `docs/specs/`, `docs/plans/`, `docs/design/`, `docs/architecture/`, `docs/adr/`, `ROADMAP.md`, `TODO.md`, `PLAN.md`
   - `--context <path>` 인자로 커스텀 경로 추가

4. **설정 파일 생성**
   - `~/.claude/obsidian.json` (글로벌, 최초 1회)
   - `.claude/obsidian.json` (프로젝트별)

5. **Vault 폴더 구조 생성**
   - `vault/projects/{name}/sessions/` 디렉토리 생성
   - `vault/projects/{name}/domain/` 디렉토리 생성

6. **dashboard.md 생성** (vault 루트에 없을 때만)
   - `templates/dashboard.md` 복사

7. **완료 메시지** 출력

### /obsidian-context

현재 프로젝트의 Obsidian 로드맵을 읽어서 대화 컨텍스트에 주입한다.
`status.md`와 `decisions.md`를 읽어서 요약한 내용을 출력한다.

## 로드맵 업데이트 규칙

status.md의 로드맵을 업데이트할 때 반드시 준수:

1. **완료 판정**: 세션에서 실제로 구현+테스트 통과가 확인된 항목만 `[x]`.
   "논의만 한 것"은 완료가 아니다.

2. **항목 추가**: 세션에서 새로운 작업이 구체적으로 언급되었거나,
   spec/plan 문서에 정의된 작업이 로드맵에 없으면 추가.

3. **항목 제거**: 절대 삭제하지 않는다.
   불필요해진 항목은 취소선으로 표시하고 사유를 남긴다.
   예: `- ~~어휘 과제 수동 채점~~ (2026-04-06: 자동 채점으로 대체)`

4. **Phase 구조 변경**: 새로운 Phase 추가는 허용.
   기존 Phase의 이름 변경이나 병합은 세션에서 명시적으로 논의된 경우만.

5. **순서**: Phase 내 태스크는 의존성 순서대로 배치.

6. **태스크 세분화**: 큰 태스크가 하위 태스크로 분해되었으면 반영.
   2단계 이상 중첩하지 않는다.

7. **기존 로드맵 존중**: 이전 세션에서 합의된 항목을 근거 없이 수정하지 않는다.

## 도메인 노트

프로젝트의 핵심 도메인 지식을 Obsidian vault에 항목별 개별 파일로 기록한다.
`/obsidian-sync` 실행 시 자동으로 최신 상태를 유지한다.

### Vault 구조

```
vault/projects/{project_name}/
├── status.md
├── decisions.md
├── sessions/
└── domain/
    ├── {category_id}/
    │   ├── {item_id}.md
    │   └── ...
    └── {category_id}/
        └── ...
```

항목의 `id`는 코드베이스의 식별자(enum, 변수명, 클래스명 등)를 기반으로 결정한다.
같은 항목은 항상 같은 파일에 매핑되어야 업데이트가 정확하다.

### 노트 파일 형식

```markdown
---
project: {project_name}
category: {category_id}
item_id: {item_id}
updated: YYYY-MM-DD
status: active | deprecated
deprecated_reason: (deprecated일 때만)
deprecated_date: (deprecated일 때만)
---
# {항목 제목}

## 개요
항목에 대한 1-2문장 설명

## 상세
카테고리 특성에 맞는 상세 내용.
코드베이스 + 세션 컨텍스트에서 추출한 구조화된 정보.
섹션 구조는 카테고리 description을 기반으로 자유롭게 결정.

## 관련 항목
- [[다른 노트로의 Obsidian 내부 링크]]

---
> ⚠️ 이 구분선 아래 내용은 자동 동기화 시 보존됩니다.
## 메모

```

### 도메인 노트 업데이트 규칙

1. **자동 재생성 영역**: `---` 구분선 + `## 메모` 위 섹션은 매 동기화 시 재생성 (덮어쓰기)
2. **보존 영역**: `## 메모` 이하는 무조건 보존. 사용자가 Obsidian에서 직접 작성한 내용이 있을 수 있다.
3. **항목 삭제 금지**: 코드에서 사라진 항목의 파일을 삭제하지 않는다.
   `status: deprecated` + `deprecated_reason`, `deprecated_date`를 frontmatter에 추가한다.
4. **정보 소스**: 코드베이스(모델, 스키마, 서비스 로직, seed 데이터)가 기본이고,
   세션에서 논의된 암묵지(임상적 맥락, 학술적 판단 근거 등)도 반영한다.

### 비정상 종료 시 복구

기존 pending 메커니즘이 도메인 노트에도 동일하게 적용된다.
PostToolUse hook가 매 tool use마다 `pending.json`에 `transcript_path`를 저장하므로,
세션이 비정상 종료되더라도 다음 세션의 `/obsidian-sync`가 트랜스크립트에서
도메인 변경 내용을 감지하고 노트를 업데이트한다.

## 설정 파일 구조

### 글로벌: ~/.claude/obsidian.json
```json
{
  "vault_path": "C:\\Users\\ymku0\\Vault_Moku\\claude-dev"
}
```

### 프로젝트별: .claude/obsidian.json
```json
{
  "project_name": "project-name",
  "gstack_slug": "slug-or-null",
  "include_gstack": true,
  "include_superpowers": true,
  "context_sources": [
    {"type": "type-name", "path": "relative/path"}
  ],
  "domain_categories": [
    {
      "id": "category-id",
      "label": "표시명",
      "description": "What to extract from codebase for this category"
    }
  ]
}
```

#### domain_categories 필드

| 필드 | 용도 |
|------|------|
| `id` | 폴더/파일명에 사용 (영문 snake_case) |
| `label` | Obsidian 노트 내 표시명 |
| `description` | Claude가 코드베이스에서 무엇을 추출할지 판단하는 근거. 이 설명이 스캔의 핵심 지시 |

`domain_categories`는 선택 사항이다. 미설정 시 `/obsidian-sync` 실행 시점에
세션 컨텍스트 + 코드베이스를 분석하여 카테고리를 자동 추천한다.
