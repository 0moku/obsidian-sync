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
