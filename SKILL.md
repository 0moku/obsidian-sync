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
    - hooks:
        - type: command
          command: "bash ${CLAUDE_SKILL_DIR}/bin/run_backup.sh"
          timeout: 5
  SessionStart:
    - hooks:
        - type: command
          command: "bash ${CLAUDE_SKILL_DIR}/bin/run_context.sh"
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

6. **pending.json 삭제**
   - `~/.claude/obsidian-pending.json` 삭제하여 다음 세션 리마인더 방지

7. **완료 메시지** 출력

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
  ]
}
```
