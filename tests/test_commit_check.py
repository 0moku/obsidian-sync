import json
import os
import sys
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'bin'))
import vault_commit_check as mod


# ---------------------------------------------------------------------------
# test_no_fire_on_non_commit: Non-commit commands produce no output
# ---------------------------------------------------------------------------

def test_no_fire_on_non_commit():
    """Non-commit bash commands should not trigger the hook."""
    non_commit_cmds = [
        "git status",
        "git push origin master",
        "git log --oneline",
        "git diff --cached",
        "git add .",
        "echo 'git commit is in a string'",
        "ls -la",
        "flutter run -d chrome",
        "git stash",
        "git rebase main",
    ]
    for cmd in non_commit_cmds:
        assert not mod.is_git_commit(cmd), f"Should not fire on: {cmd}"


# ---------------------------------------------------------------------------
# test_fire_on_git_commit: Detects git commit commands (various forms)
# ---------------------------------------------------------------------------

def test_fire_on_git_commit():
    """Various forms of git commit should trigger the hook."""
    commit_cmds = [
        'git commit -m "fix: something"',
        "git commit --amend",
        "git commit -am 'chore: update'",
        'git commit -m "$(cat <<\'EOF\'\nmessage\nEOF\n)"',
        "git commit --no-edit",
        "git commit",
    ]
    for cmd in commit_cmds:
        assert mod.is_git_commit(cmd), f"Should fire on: {cmd}"


# ---------------------------------------------------------------------------
# test_keyword_matching: Maps staged files to vault tasks correctly
# ---------------------------------------------------------------------------

def test_keyword_matching():
    """Staged file paths should be matched against task_mapping keywords."""
    task_mapping = {
        "pcc|repetition": "sentence_repetition",
        "expressive_vocab": "expressive_vocab",
        "story|comprehension": "story_comprehension",
        "parent_survey|kdst": "parent_survey",
    }

    # File matching 'repetition' keyword
    staged = ["app/lib/battery/repetition_screen.dart"]
    matched = mod.match_tasks(staged, task_mapping)
    assert "sentence_repetition" in matched

    # File matching 'story' keyword (OR match)
    staged = ["app/lib/battery/story_task.dart"]
    matched = mod.match_tasks(staged, task_mapping)
    assert "story_comprehension" in matched

    # File matching 'comprehension' keyword (second OR branch)
    staged = ["app/lib/battery/comprehension_widget.dart"]
    matched = mod.match_tasks(staged, task_mapping)
    assert "story_comprehension" in matched

    # File matching 'kdst' (second keyword in OR)
    staged = ["server/app/kdst_scoring.py"]
    matched = mod.match_tasks(staged, task_mapping)
    assert "parent_survey" in matched

    # File matching nothing
    staged = ["README.md", "pubspec.yaml"]
    matched = mod.match_tasks(staged, task_mapping)
    assert len(matched) == 0

    # Multiple matches at once
    staged = [
        "app/lib/battery/pcc_task.dart",
        "app/lib/battery/expressive_vocab_screen.dart",
    ]
    matched = mod.match_tasks(staged, task_mapping)
    assert "sentence_repetition" in matched
    assert "expressive_vocab" in matched


# ---------------------------------------------------------------------------
# test_stale_vault_warning: Produces warning when vault updated date != today
# ---------------------------------------------------------------------------

def test_stale_vault_warning():
    """Vault task files with updated date != today should produce warnings."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tasks_dir = Path(tmpdir) / "projects" / "testproj" / "tasks"
        tasks_dir.mkdir(parents=True)

        # Create a stale task file (updated yesterday)
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        task_file = tasks_dir / "sentence_repetition.md"
        task_file.write_text(
            f"---\nproject: testproj\ntask_id: sentence_repetition\nupdated: {yesterday}\n---\n# Content\n",
            encoding="utf-8",
        )

        today = date.today().isoformat()
        warnings = mod.check_vault_staleness(
            {"sentence_repetition"}, tmpdir, "testproj", today
        )
        assert len(warnings) == 1
        assert "sentence_repetition" in warnings[0]
        assert yesterday in warnings[0]


def test_stale_vault_warning_missing_file():
    """Vault task files that don't exist should produce a 'not found' warning."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tasks_dir = Path(tmpdir) / "projects" / "testproj" / "tasks"
        tasks_dir.mkdir(parents=True)
        # No task file created

        today = date.today().isoformat()
        warnings = mod.check_vault_staleness(
            {"nonexistent_task"}, tmpdir, "testproj", today
        )
        assert len(warnings) == 1
        assert "not found" in warnings[0]


# ---------------------------------------------------------------------------
# test_fresh_vault_no_warning: No warning when vault was updated today
# ---------------------------------------------------------------------------

def test_fresh_vault_no_warning():
    """Vault task files updated today should produce no warnings."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tasks_dir = Path(tmpdir) / "projects" / "testproj" / "tasks"
        tasks_dir.mkdir(parents=True)

        today = date.today().isoformat()
        task_file = tasks_dir / "sentence_repetition.md"
        task_file.write_text(
            f"---\nproject: testproj\ntask_id: sentence_repetition\nupdated: {today}\n---\n# Content\n",
            encoding="utf-8",
        )

        warnings = mod.check_vault_staleness(
            {"sentence_repetition"}, tmpdir, "testproj", today
        )
        assert len(warnings) == 0


# ---------------------------------------------------------------------------
# test_volatile_memory_staleness: Detects stale volatile memory files
# ---------------------------------------------------------------------------

def test_volatile_memory_staleness():
    """Volatile memory files older than stale_days should produce warnings."""
    with tempfile.TemporaryDirectory() as tmpdir:
        memory_dir = Path(tmpdir)

        # Create a volatile memory file
        mem_file = memory_dir / "project_old_plan.md"
        mem_file.write_text(
            "---\nname: old plan\ndescription: desc\ntype: project\nvolatile: true\n---\nContent\n",
            encoding="utf-8",
        )

        # Set modification time to 20 days ago
        old_time = (datetime.now() - timedelta(days=20)).timestamp()
        os.utime(str(mem_file), (old_time, old_time))

        warnings = mod.check_volatile_memory(memory_dir, stale_days=14)
        assert len(warnings) == 1
        assert "project_old_plan.md" in warnings[0]
        assert "20d old" in warnings[0]


def test_volatile_memory_fresh():
    """Fresh volatile memory files should not produce warnings."""
    with tempfile.TemporaryDirectory() as tmpdir:
        memory_dir = Path(tmpdir)

        mem_file = memory_dir / "project_fresh.md"
        mem_file.write_text(
            "---\nname: fresh\ndescription: desc\ntype: project\nvolatile: true\n---\nContent\n",
            encoding="utf-8",
        )
        # File was just created, so mtime is now (< 14 days)

        warnings = mod.check_volatile_memory(memory_dir, stale_days=14)
        assert len(warnings) == 0


def test_volatile_memory_non_volatile_ignored():
    """Non-volatile memory files should be ignored even if old."""
    with tempfile.TemporaryDirectory() as tmpdir:
        memory_dir = Path(tmpdir)

        mem_file = memory_dir / "project_stable.md"
        mem_file.write_text(
            "---\nname: stable\ndescription: desc\ntype: project\n---\nContent\n",
            encoding="utf-8",
        )
        old_time = (datetime.now() - timedelta(days=30)).timestamp()
        os.utime(str(mem_file), (old_time, old_time))

        warnings = mod.check_volatile_memory(memory_dir, stale_days=14)
        assert len(warnings) == 0


# ---------------------------------------------------------------------------
# test_missing_config_silent_exit: Missing config files don't cause errors
# ---------------------------------------------------------------------------

def test_missing_config_silent_exit():
    """Missing config files should return None without errors."""
    # Missing project config
    result = mod.load_project_config("/nonexistent/path")
    assert result is None

    # Missing global config — temporarily override the path
    orig = mod.GLOBAL_CONFIG_PATH
    try:
        mod.GLOBAL_CONFIG_PATH = Path("/nonexistent/obsidian.json")
        result = mod.load_global_config()
        assert result is None
    finally:
        mod.GLOBAL_CONFIG_PATH = orig


def test_normalize_path_msys():
    """MSYS-style paths should be normalized on Windows."""
    if sys.platform == "win32":
        assert mod.normalize_path("/c/dev_projects/malmee") == "C:\\dev_projects\\malmee"
        assert mod.normalize_path("/d/other/path") == "D:\\other\\path"
    # Non-MSYS paths pass through unchanged
    assert mod.normalize_path("C:\\dev_projects\\malmee") == "C:\\dev_projects\\malmee"


def test_parse_frontmatter():
    """Frontmatter parsing should extract key-value pairs."""
    content = '---\nproject: malmee\ntask_id: vocab\nupdated: 2026-04-13\n---\n# Body\n'
    fm = mod.parse_frontmatter(content)
    assert fm["project"] == "malmee"
    assert fm["task_id"] == "vocab"
    assert fm["updated"] == "2026-04-13"


def test_parse_frontmatter_empty():
    """Missing frontmatter should return empty dict."""
    assert mod.parse_frontmatter("# No frontmatter") == {}
    assert mod.parse_frontmatter("") == {}


def test_get_memory_dir():
    """Memory dir derivation from cwd."""
    if sys.platform == "win32":
        mem_dir = mod.get_memory_dir("C:\\dev_projects\\malmee")
        expected_name = "C-dev_projects-malmee"
        assert mem_dir.name == "memory"
        assert mem_dir.parent.name == expected_name
