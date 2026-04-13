---
name: obsidian-sync
version: 3.0.0
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
  PreToolUse:
    - matcher: "Bash"
      hooks:
        - type: command
          command: "python ~/.claude/skills/obsidian-sync/bin/vault_commit_check.py"
          timeout: 5
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

### Vault 구조

```
vault/projects/{project_name}/
├── status.md              (현황 요약 표 + 진행중/미래 Phase, ~100줄)
├── decisions.md           (결정 로그, 120건 초과 시 아카이브)
├── overrides.md           (Override 로그)
├── sessions/              (세션별 기록)
├── archive/               (완료 Phase, 오래된 결정)
├── tasks/                 (과제별 자기완결 노트)
│   └── {task_id}.md
└── shared/                (과제 간 공통 참조)
    ├── irt_model.md
    ├── image_pipeline.md
    ├── risk_classification.md
    └── references.md
```

## 명령어

### /obsidian-sync

현재 세션의 내용을 Obsidian vault에 기록한다. 아래 순서대로 실행:

1. **설정 로드**
   - `~/.claude/obsidian.json` (vault_path)
   - `.claude/obsidian.json` (project_name, context_sources)
   - 없으면 `/obsidian-setup` 안내

1b. **마이그레이션 감지 (v1→v2)**
   - 감지 조건: vault에 `domain/` 디렉토리가 존재하고 `tasks/` 디렉토리가 없음
   - 감지되면 마이그레이션 모드로 전환:
     1. 사용자에게 "v2 → v3 구조 마이그레이션을 실행합니다" 안내
     2. `archive/` 디렉토리 생성
     3. status.md에서 완료된 Phase 추출 → `archive/phase-{N}-completed.md`로 이동
     4. status.md를 새 형식으로 재작성 (현황 요약 표 + 진행중 Phase만)
     5. `tasks/` 디렉토리 생성
     6. 각 과제에 대해: `domain/assessments/`, `domain/scoring/` + decisions.md + 코드베이스 스캔 → task 노트 템플릿으로 작성
     7. `shared/` 디렉토리 생성
     8. shared 노트 4개 생성:
        - `shared/irt_model.md` — vocabulary_scoring.md 등의 공통 IRT 부분 추출
        - `shared/image_pipeline.md` — 이미지 생성 파이프라인
        - `shared/risk_classification.md` — overall_risk.md에서 추출
        - `shared/references.md` — 기존 reference 파일들 병합
     9. `domain/` → `domain/_archived/`로 이름 변경 (삭제하지 않음)
     10. vault 루트의 `dashboard.md` 삭제
     11. `구조화-선별검사-상세.md`가 있으면 파일 상단에 `> ⚠️ 이 문서는 더 이상 권위적 소스가 아닙니다. tasks/ 노트를 참조하세요.` 추가
     12. step 2로 계속 진행

2. **현재 세션 분석** — 이 대화의 내용을 직접 분석
   - 세션에서 한 작업 요약
   - 주요 활동 목록
   - 변경된 파일 (git diff --stat 참조)
   - 결정 사항 (있으면)
   - 현재 상태 (완료/진행 중/블로커/다음 할 일)
   - **Override 감지** — 아래 조건을 모두 만족하는 순간을 찾아 목록화:
     1. Claude가 제안/주장/판단을 했음
     2. 사용자가 명시적으로 반대하거나 다른 방향을 제시
     3. 다음 중 하나: (a) Claude가 동의/수용 → `conceded` (b) Claude가 반대 유지했으나 사용자 판단으로 진행 → `overruled`
   - Override가 **아닌 것**: 선택지 중 하나를 고른 것, 단순 요구사항 추가
   - 같은 주제는 한 세션에서 1건으로 카운트 (주제 단위)
   - 과거 세션 소급 분석 없음 — 현재 세션의 대화 내용만 감지 대상
   - 각 override에 카테고리 분류:
     - `product_judgment` — UX, 비즈니스 메트릭, 사용자 행동, 시장 관련 반박
     - `technical_approach` — 라이브러리, 아키텍처, 알고리즘, 구현 방식 관련 교정
     - `missed_risk` — Claude가 언급하지 않은 부작용/엣지케이스
     - `scope_adjustment` — 스코프 확대/축소/지연
     - `factual_error` — API, 스펙, 학술 정보 사실관계

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

   ## Override
   (2단계에서 감지된 override가 있을 때만 이 섹션 포함)
   - 한줄요약 (카테고리, resolution) → [[overrides]]
   ```

4. **decisions.md 업데이트** (결정 사항이 있을 때만)
   - `vault/projects/{name}/decisions.md`
   - `# 결정 로그` 바로 아래에 새 결정 삽입 (최신이 위)
   - 프론트매터 `updated` 갱신
   - 파일 없으면 새로 생성

4b. **decisions.md 팽창 관리**
   - decisions.md 내 `### ` 헤딩 수를 카운트
   - 120건 초과 시: 60일 이상 된 항목을 `archive/decisions-YYYY-MM.md`로 이동
   - decisions.md 하단에 아카이브 링크 추가: `> 📁 아카이브: [[decisions-YYYY-MM]]`

5. **overrides.md 업데이트** (2단계에서 override가 감지되었을 때만)
   - `vault/projects/{name}/overrides.md`
   - 파일이 없으면 아래 형식으로 새로 생성:
     ```yaml
     ---
     project: {project_name}
     updated: YYYY-MM-DD
     stats:
       product_judgment: 0
       technical_approach: 0
       missed_risk: 0
       scope_adjustment: 0
       factual_error: 0
       total: 0
     resolution_stats:
       conceded: 0
       overruled: 0
     ---
     # Override Log
     ```
   - `# Override Log` 바로 아래에 새 항목 삽입 (최신이 위):
     ```markdown
     ### YYYY-MM-DD: 한줄 요약
     - **카테고리**: {category_id}
     - **resolution**: conceded | overruled
     - **AI 제안**: Claude가 뭘 제안했는지. 1-2문장
     - **사용자 교정**: 사용자가 왜 반대했는지. 핵심 논거 포함
     - **AI가 놓친 것**: AI 사고의 어떤 결함이 이 override를 만들었는지
     - **세션**: [[YYYY-MM-DD_세션제목]]
     ```
   - 프론트매터 `updated` 갱신
   - `stats`, `resolution_stats`를 파일 내 항목 기반으로 재계산
   - override가 없는 세션에서는 이 단계 전체 스킵 (파일 미접촉)

6. **status.md 갱신**
   - `vault/projects/{name}/status.md`
   - 기존 status.md를 읽고, 이번 세션 결과를 반영하여 갱신
   - 형식:
     ```markdown
     ---
     project: {project_name}
     updated: YYYY-MM-DD
     current_phase: "Phase N"
     ---
     # {project_name} 현황

     ## 현황 요약
     | 과제 | 상태 | 문항 | 배포 | 갱신 |
     |------|------|------|------|------|
     | [[tasks/receptive_vocab]] | beta | 40 | ✅ | 04-12 |
     | [[tasks/story_comprehension]] | dev | 96 | 🔧 | 04-12 |
     (task 노트 frontmatter의 deploy_status, item_count에서 자동 생성)

     ## 블로커 / 최근 완료
     - 🔴 블로커: ...
     - ✅ 최근: ...
     (이번 세션에서 감지된 블로커와 완료 항목)

     ## Phase N: {phase_name} (진행 중)
     - [x] 완료된 항목
     - [ ] 미완료 항목

     ## Phase N+1: {phase_name} (예정)
     - [ ] 계획된 항목

     ## 설계 원칙
     - 원칙 1
     - 원칙 2

     ## 완료 Phase
     - [[archive/phase-1-completed|Phase 1: ...]]
     - [[archive/phase-2-completed|Phase 2: ...]]
     ```
   - 현황 요약 표는 `tasks/` 노트의 frontmatter에서 자동 생성
   - 블로커/최근 완료는 이번 세션에서 감지된 내용
   - 진행중 Phase: 완료 항목 체크, 새 항목 추가
   - 완료된 Phase: `archive/`로 이동, status.md에는 링크만 남김
   - "워크플로우 상태" 같은 append-only 섹션 없음
   - 로드맵 업데이트 규칙 (아래) 준수

7. **Vault Drift 수정 + Memory 정비**

   이 세션에서 변경된 코드와 vault/memory의 일관성을 확인하고 수정한다.

   **7a. Vault task drift 수정**
   1. `.claude/obsidian.json`의 `task_mapping` 로드
   2. 이 세션의 `git diff` (또는 `git log --since` 오늘)에서 변경된 파일 목록 추출
   3. `task_mapping` 키워드로 영향받는 vault task 파일 식별
   4. 각 영향받는 task 파일에 대해:
      - 코드베이스 현재 상태와 vault 내용 비교
      - `deploy_status`, `item_count`, "현재 (배포됨)" 섹션이 실제와 일치하는지 확인
      - 불일치 발견 시 task 노트 재생성 (8단계 규칙 적용)
      - `updated:` 날짜를 오늘로 갱신 (내용을 실제 검증/갱신한 경우에만. 날짜만 변경 금지)
   5. status.md 요약 테이블도 task 파일과 일치하도록 동기화

   **7b. 미매핑 파일 감지 (audit)**
   1. 알려진 과제 코드 디렉토리 스캔:
      - `app/lib/screens/battery/tasks/` — Flutter task widgets
      - `server/app/services/` — scoring/sampling services
   2. 각 파일명에서 task 키워드 추출
   3. `task_mapping`에 없는 키워드 발견 시 경고: "⚠ 미매핑 코드 파일: {path} — obsidian.json task_mapping에 추가 필요"

   **7c. Volatile memory 정비**
   1. `~/.claude/projects/{dir}/memory/project_*.md` 스캔
   2. `volatile: true`이면서 `memory_stale_days` 초과한 파일 목록화
   3. 각 stale memory에 대해: 현재 코드 상태와 교차 검증
   4. 내용이 맞으면 `volatile` 유지하되 마지막 수정 시각 갱신 (touch)
   5. 내용이 틀리면 memory 내용 업데이트 또는 삭제

8. **카테고리 체크** (기존 7단계)
   - `.claude/obsidian.json`에 `domain_categories`가 없거나 비어있으면:
     1. 코드베이스 분석 — tasks (과제)와 shared (공통 컴포넌트) 감지
     2. 사용자에게 추천 제시 → 승인/수정 → `.claude/obsidian.json`의 `domain_categories`에 저장
   - 이미 설정되어 있으면:
     1. 세션에서 새로운 과제가 논의되었는지 확인
     2. 새 task가 필요하면 추천 → 승인 시 추가
     3. 해당 없으면 스킵 (질문 없이 진행)

9. **task 노트 + shared 노트 갱신**

   **9a. task 노트 갱신**
   - `tasks/` 내 각 파일에 대해:
     1. 이번 세션에서 해당 과제를 다뤘는지 판단
        - 판단 기준 (둘 중 하나): 세션에서 해당 과제를 논의함 / `git diff`에 관련 파일 포함
     2. 변경 없으면 스킵
     3. 변경 있으면:
        - 기존 노트 읽기
        - `## 메모` 이하 텍스트를 별도 보존
        - 코드베이스 스캔 (DB 스키마, API 엔드포인트, 위젯, seed 데이터)
        - 세션에서 추출 (결정, 상태 변경, 계획)
        - task 노트 템플릿으로 `## 메모` 위 섹션 재생성 + 보존한 `## 메모` 이하 복원
        - 정보 소스 우선순위: "현재 (배포됨)" → 코드가 세션보다 우선, "계획" → 세션 우선
        - decisions.md에서 해당 task_id 또는 한글명으로 매칭되는 최근 5건 추출 → `## 주요 결정`
     4. 새로 감지된 과제는 task 노트 템플릿으로 새 파일 생성
   - 코드에서 사라진 과제의 파일은 삭제하지 않고 frontmatter에 `status: deprecated`, `deprecated_reason`, `deprecated_date` 설정

   **9b. shared 노트 갱신**
   - `shared/` 내 각 파일에 대해:
     1. 이번 세션에서 해당 주제를 다뤘는지 판단
     2. 변경 없으면 스킵
     3. 변경 있으면: 기존 읽기 → `## 메모` 보존 → 코드+세션에서 재생성 → 복원
   - task 노트보다 갱신 빈도 낮음 (과제 간 공통 요소가 변경될 때만)

10. **pending.json 삭제**
   - `~/.claude/obsidian-pending.json` 삭제하여 다음 세션 리마인더 방지

11. **완료 메시지** 출력

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
   - `vault/projects/{name}/tasks/` 디렉토리 생성
   - `vault/projects/{name}/shared/` 디렉토리 생성
   - `vault/projects/{name}/archive/` 디렉토리 생성

6. **완료 메시지** 출력

### /obsidian-context

현재 프로젝트의 Obsidian 현황을 읽어서 대화 컨텍스트에 주입한다.
`status.md`의 현황 요약 표 + 블로커 + 진행중 Phase와 `decisions.md`를 읽어서 요약한 내용을 출력한다.

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

## Override Log

세션에서 사용자가 AI의 제안/판단을 교정한 이력을 기록한다.
harness 개발용 패턴 분석 데이터셋 + 개인 회고 자료로 활용.
세션 컨텍스트에는 주입하지 않는다 (행동 교정은 feedback memory 담당).

### 감지 기준

감지 조건 (AND):
1. Claude가 제안/주장/판단을 했음
2. 사용자가 명시적으로 반대하거나 다른 방향을 제시
3. (a) Claude가 동의/수용 → `conceded` 또는 (b) Claude가 반대 유지, 사용자가 진행 → `overruled`

감지하지 않는 것:
- 선택지 중 하나를 고른 것 (정상적 의사결정)
- 단순 요구사항 추가 (override가 아니라 스코프 확장)

카운팅: 같은 주제는 한 세션에서 1건. 다른 세션이면 별도 건.

### 카테고리

| ID | 라벨 | 시그널 |
|---|---|---|
| `product_judgment` | 제품 판단 | UX, 비즈니스 메트릭, 시장 |
| `technical_approach` | 기술 접근 | 라이브러리, 아키텍처, 구현 |
| `missed_risk` | 놓친 리스크 | 미언급 부작용/엣지케이스 |
| `scope_adjustment` | 스코프 조정 | 범위 확대/축소/지연 |
| `factual_error` | 사실 오류 | API, 스펙, 학술 정보 |

### 엔트리 형식

```markdown
### YYYY-MM-DD: 한줄 요약
- **카테고리**: {category_id}
- **resolution**: conceded | overruled
- **AI 제안**: 1-2문장
- **사용자 교정**: 핵심 논거 포함
- **AI가 놓친 것**: AI 사고 결함 유형화
- **세션**: [[YYYY-MM-DD_세션제목]]
```

**"AI가 놓친 것"** 필드가 핵심 — 단순 기록이 아니라 AI 판단 결함의 유형화를 강제한다.

### 파일 규칙

- 새 항목은 `# Override Log` 바로 아래에 삽입 (최신이 위)
- `stats`, `resolution_stats`는 매 동기화 시 재계산
- 파일 미존재 시 첫 override 감지 시점에 자동 생성
- override 없는 세션에서는 파일 미접촉

### feedback memory와의 관계

| 시스템 | 역할 | 소비 시점 |
|---|---|---|
| feedback memory | 행동 교정 ("이렇게 하지 마") | 매 세션 자동 주입 |
| overrides.md | 교정 이력 + 패턴 분석 데이터 | 회고 / harness 배치 분석 |

같은 사건이 양쪽에 다른 형태로 저장될 수 있다.

## Task 노트

프로젝트의 과제별 도메인 지식을 자기완결적 노트로 기록한다.
각 task 노트는 해당 과제에 대한 모든 정보(현황, 채점, 학술 근거, 결정)를 한 파일에 담는다.
`/obsidian-sync` 실행 시 자동으로 최신 상태를 유지한다.

### Task 노트 템플릿

```markdown
---
project: {project_name}
task_id: {task_id}
updated: YYYY-MM-DD
deploy_status: beta | production | dev | planned
item_count: N
status: active | deprecated
deprecated_reason: (deprecated일 때만)
deprecated_date: (deprecated일 때만)
---
# {과제 한글명} ({영문명})

> **상태**: {emoji} {상태} | **문항**: {N}개 ({상세}) | **갱신**: {date}
> **다음**: {다음 단계} | **의존**: [[shared/irt_model]], [[shared/image_pipeline]]

## 현재 (배포됨)
코드베이스에서 추출한 현재 구현 상태.
DB 스키마, API 엔드포인트, 위젯, seed 데이터 기반.

## 계획 (확정, 미구현)
세션에서 합의되었으나 아직 코드에 없는 것.

## 검토 중
논의되었으나 아직 확정되지 않은 것.

## 채점
채점 방식, 기준점, 알고리즘.

## 학술 근거
참조 논문, 표준화 검사, 이론적 배경.

## 주요 결정
decisions.md에서 task_id 또는 한글명으로 매칭된 최근 5건.

## 관련 항목
- [[tasks/다른_과제]]
- [[shared/공통_참조]]

---
> ⚠️ 이 구분선 아래 내용은 자동 동기화 시 보존됩니다.
## 메모

```

### Task 노트 업데이트 규칙

1. **자동 재생성 영역**: `---` 구분선 + `## 메모` 위 섹션은 매 동기화 시 재생성 (덮어쓰기)
2. **보존 영역**: `## 메모` 이하는 무조건 보존. 사용자가 Obsidian에서 직접 작성한 내용이 있을 수 있다.
3. **항목 삭제 금지**: 코드에서 사라진 과제의 파일을 삭제하지 않는다.
   `status: deprecated` + `deprecated_reason`, `deprecated_date`를 frontmatter에 추가한다.
4. **정보 소스 우선순위**:
   - "현재 (배포됨)" → 코드베이스(모델, 스키마, 서비스 로직, seed 데이터)가 세션보다 우선
   - "계획 (확정, 미구현)" → 세션에서 논의된 내용 우선
5. **결정 추출**: decisions.md에서 `task_id` 또는 한글 과제명으로 매칭되는 최근 5건을 `## 주요 결정`에 포함
6. **deploy_status 기준**:
   - `production` — 프로덕션 배포 완료, 사용자 접근 가능
   - `beta` — 배포되었으나 제한적 접근
   - `dev` — 개발 중, 로컬/스테이징만
   - `planned` — 설계만 완료, 코드 없음

## Shared 노트

과제 간 공통으로 참조되는 도메인 지식을 기록한다.
task 노트보다 갱신 빈도가 낮다.

### Shared 노트 목록

| 파일 | 내용 | 갱신 트리거 |
|------|------|-------------|
| `shared/irt_model.md` | IRT 모델, 능력 추정, 문항 파라미터 | 채점 알고리즘 변경 시 |
| `shared/image_pipeline.md` | 일러스트 생성 파이프라인, 스타일 가이드 | 이미지 생성 프로세스 변경 시 |
| `shared/risk_classification.md` | 위험군 분류 기준, 종합 점수 산출 | 분류 로직 변경 시 |
| `shared/references.md` | 학술 참고문헌, 표준화 검사 목록 | 새 참고문헌 추가 시 |

### Shared 노트 업데이트 규칙

1. **자동 재생성 영역 / 보존 영역**: task 노트와 동일 (`## 메모` 기준)
2. **갱신 조건**: 세션에서 해당 주제를 다뤘을 때만 갱신
3. **정보 소스**: 코드베이스 + 세션 컨텍스트 병용

### Shared 노트 템플릿

```markdown
---
project: {project_name}
shared_id: {shared_id}
updated: YYYY-MM-DD
status: active | deprecated
---
# {제목}

## 개요
1-2문장 설명

## 상세
구조화된 상세 내용.
코드베이스 + 세션 컨텍스트에서 추출.

## 참조하는 과제
- [[tasks/관련_과제_1]]
- [[tasks/관련_과제_2]]

---
> ⚠️ 이 구분선 아래 내용은 자동 동기화 시 보존됩니다.
## 메모

```

## 비정상 종료 시 복구

기존 pending 메커니즘이 task 노트에도 동일하게 적용된다.
PostToolUse hook가 매 tool use마다 `pending.json`에 `transcript_path`를 저장하므로,
세션이 비정상 종료되더라도 다음 세션의 `/obsidian-sync`가 트랜스크립트에서
task 변경 내용을 감지하고 노트를 업데이트한다.

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
      "id": "task-id-or-shared-id",
      "label": "표시명",
      "description": "What to extract from codebase for this task/shared note"
    }
  ]
}
```

#### domain_categories 필드

| 필드 | 용도 |
|------|------|
| `id` | task 노트 또는 shared 노트의 파일명에 사용 (영문 snake_case) |
| `label` | Obsidian 노트 내 표시명 |
| `description` | Claude가 코드베이스에서 무엇을 추출할지 판단하는 근거. 이 설명이 스캔의 핵심 지시 |

`domain_categories`는 선택 사항이다. 미설정 시 `/obsidian-sync` 실행 시점에
코드베이스를 분석하여 tasks와 shared 컴포넌트를 자동 추천한다.
