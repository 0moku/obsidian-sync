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
