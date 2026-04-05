# Claude Dev Dashboard

## 프로젝트 현황
```dataview
TABLE status, current_phase, updated, last_session
FROM "claude-dev/projects"
WHERE file.name = "status"
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
