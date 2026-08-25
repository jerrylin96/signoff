"""Tests for standalone repo initializer (init.py)."""

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
import init


@pytest.fixture
def temp_git_repo(tmp_path):
    """Creates a temporary git repository configured with a default commit and origin remote."""
    repo_dir = tmp_path / "test_repo"
    repo_dir.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo_dir, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_dir, check=True)
    
    readme = repo_dir / "README.md"
    readme.write_text("# Test Project\n\nA test repository.\n", encoding="utf-8")
    
    subprocess.run(["git", "add", "README.md"], cwd=repo_dir, check=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=repo_dir, check=True)
    subprocess.run(["git", "remote", "add", "origin", "https://github.com/example-org/test-project.git"], cwd=repo_dir, check=True)
    return repo_dir


# --- T1.1: Git Context & Remote Slug Detection ---

@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://github.com/jerrylin96/signoff.git", "jerrylin96/signoff"),
        ("https://github.com/jerrylin96/signoff", "jerrylin96/signoff"),
        ("https://x-access-token:ghp_123@github.com/org/repo.git", "org/repo"),
        ("git@github.com:jerrylin96/signoff.git", "jerrylin96/signoff"),
        ("git@github.com:jerrylin96/signoff", "jerrylin96/signoff"),
        ("ssh://git@github.com/org/custom-repo.git", "org/custom-repo"),
        ("ssh://git@github.com:22/org/custom-repo.git", "org/custom-repo"),
    ],
)
def test_parse_github_slug_valid(url, expected):
    assert init.parse_github_slug(url) == expected


@pytest.mark.parametrize(
    "invalid_url",
    [
        "https://gitlab.com/owner/repo.git",
        "https://github.com/invalid_slug_with_semi;rm -rf /",
        "not-a-url",
        "",
    ],
)
def test_parse_github_slug_invalid(invalid_url):
    assert init.parse_github_slug(invalid_url) is None


def test_validate_slug():
    assert init.is_valid_slug("owner/repo") is True
    assert init.is_valid_slug("org.name/repo-123_4") is True
    assert init.is_valid_slug("owner/repo;echo bad") is False
    assert init.is_valid_slug("owner/../repo") is False
    assert init.is_valid_slug("") is False


def test_detect_git_context(temp_git_repo):
    ctx = init.detect_git_context(temp_git_repo)
    assert ctx.root == temp_git_repo
    assert ctx.default_branch == "main"
    assert ctx.slug == "example-org/test-project"


def test_detect_git_context_from_subdirectory(temp_git_repo):
    subdir = temp_git_repo / "src" / "nested"
    subdir.mkdir(parents=True)
    ctx = init.detect_git_context(subdir)
    assert ctx.root == temp_git_repo


def test_detect_git_context_unborn_head(tmp_path):
    repo = tmp_path / "unborn_repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "remote", "add", "origin", "https://github.com/example-org/unborn-project.git"], cwd=repo, check=True)
    ctx = init.detect_git_context(repo)
    assert ctx.root == repo
    assert ctx.default_branch == "main"
    assert ctx.slug == "example-org/unborn-project"


def test_detect_git_context_detached_head(temp_git_repo):
    subprocess.run(["git", "checkout", "--detach", "HEAD"], cwd=temp_git_repo, check=True, capture_output=True)
    ctx = init.detect_git_context(temp_git_repo)
    assert ctx.root == temp_git_repo
    assert ctx.default_branch == "main"


def test_detect_git_context_no_remote(tmp_path):
    repo = tmp_path / "no_remote_repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    ctx = init.detect_git_context(repo)
    assert ctx.root == repo
    assert ctx.slug is None


# --- T1.2: Stack Detection Engine ---

def test_detect_stack_domain_science(tmp_path):
    repo = tmp_path / "science_repo"
    repo.mkdir()
    (repo / "requirements.txt").write_text("torch==2.1.0\nxarray\nnumpy\n", encoding="utf-8")
    assert init.detect_recommended_profile(repo) == "domain-science"


def test_detect_stack_domain_science_ipynb(tmp_path):
    repo = tmp_path / "notebook_repo"
    repo.mkdir()
    (repo / "analysis.ipynb").write_text('{"cells": []}', encoding="utf-8")
    assert init.detect_recommended_profile(repo) == "domain-science"


def test_detect_stack_software_general(tmp_path):
    repo = tmp_path / "web_repo"
    repo.mkdir()
    (repo / "package.json").write_text('{"name": "express-app"}', encoding="utf-8")
    assert init.detect_recommended_profile(repo) == "software-general"


# --- T1.3: Scaffolding, Merging & Templating ---

def test_scaffold_workflow_file(temp_git_repo):
    init.scaffold_workflow(temp_git_repo, default_branch="master")
    workflow = temp_git_repo / ".github" / "workflows" / "signoff.yml"
    assert workflow.is_file()
    content = workflow.read_text(encoding="utf-8")
    assert "branches: [ master ]" in content
    assert "fetch-depth: 0" in content
    assert "jerrylin96/signoff/verify@verify-v1.2" in content


def test_scaffold_profile_file(temp_git_repo):
    init.scaffold_profile(temp_git_repo, profile_id="domain-science")
    profile = temp_git_repo / ".signoff" / "profile.md"
    assert profile.is_file()
    content = profile.read_text(encoding="utf-8")
    assert "Profile-ID: domain-science" in content
    assert "<!-- INTERVIEW-PROFILE:BEGIN" in content
    assert "<!-- INTERVIEW-PROFILE:END -->" in content


def test_merge_claude_settings_new(temp_git_repo):
    init.merge_claude_settings(temp_git_repo)
    settings_file = temp_git_repo / ".claude" / "settings.json"
    assert settings_file.is_file()
    data = json.loads(settings_file.read_text(encoding="utf-8"))
    assert "signoff@signoff" in data.get("enabledPlugins", [])


def test_merge_claude_settings_existing(temp_git_repo):
    claude_dir = temp_git_repo / ".claude"
    claude_dir.mkdir()
    (claude_dir / "settings.json").write_text(
        json.dumps({"theme": "dark", "enabledPlugins": ["other-plugin"]}),
        encoding="utf-8",
    )
    init.merge_claude_settings(temp_git_repo)
    data = json.loads((claude_dir / "settings.json").read_text(encoding="utf-8"))
    assert data["theme"] == "dark"
    assert "other-plugin" in data["enabledPlugins"]
    assert "signoff@signoff" in data["enabledPlugins"]


def test_inject_readme_badge_under_h1(temp_git_repo):
    init.inject_readme_badge(temp_git_repo, slug="org/my-project")
    content = (temp_git_repo / "README.md").read_text(encoding="utf-8")
    assert content.startswith("# Test Project\n\n[![attested by humans](https://github.com/org/my-project/actions/workflows/signoff.yml/badge.svg)](https://github.com/org/my-project/actions/workflows/signoff.yml)\n")


def test_inject_readme_badge_idempotent(temp_git_repo):
    init.inject_readme_badge(temp_git_repo, slug="org/my-project")
    init.inject_readme_badge(temp_git_repo, slug="org/my-project")
    content = (temp_git_repo / "README.md").read_text(encoding="utf-8")
    assert content.count("actions/workflows/signoff.yml/badge.svg") == 1


def test_inject_readme_badge_crlf(tmp_path):
    repo = tmp_path / "crlf_repo"
    repo.mkdir()
    readme = repo / "README.md"
    readme.write_bytes(b"# Windows Repo\r\n\r\nSome info.\r\n")
    init.inject_readme_badge(repo, slug="org/win-project")
    content = readme.read_bytes()
    assert b"\r\n" in content
    assert b"actions/workflows/signoff.yml/badge.svg" in content


def test_inject_readme_badge_no_h1(tmp_path):
    repo = tmp_path / "no_h1_repo"
    repo.mkdir()
    readme = repo / "README.md"
    readme.write_text("## Subtitle Only\n\nSome body text without H1.\n", encoding="utf-8")
    init.inject_readme_badge(repo, slug="org/no-h1-project")
    content = readme.read_text(encoding="utf-8")
    assert content.startswith("[![attested by humans]")
    assert "## Subtitle Only" in content


def test_inject_readme_badge_missing_readme(tmp_path):
    repo = tmp_path / "missing_readme_repo"
    repo.mkdir()
    init.inject_readme_badge(repo, slug="org/created-readme")
    readme = repo / "README.md"
    assert readme.is_file()
    content = readme.read_text(encoding="utf-8")
    assert "actions/workflows/signoff.yml/badge.svg" in content


def test_inject_readme_badge_empty_readme(tmp_path):
    repo = tmp_path / "empty_readme_repo"
    repo.mkdir()
    readme = repo / "README.md"
    readme.write_text("", encoding="utf-8")
    init.inject_readme_badge(repo, slug="org/empty-readme")
    content = readme.read_text(encoding="utf-8")
    assert "actions/workflows/signoff.yml/badge.svg" in content


# --- T1.4: Working Tree Safety & Branch Management ---

def test_dirty_working_tree_guard(temp_git_repo):
    dirty_file = temp_git_repo / "unrelated.txt"
    dirty_file.write_text("unstaged change", encoding="utf-8")
    
    with pytest.raises(RuntimeError, match="Working tree has uncommitted changes"):
        init.ensure_clean_working_tree(temp_git_repo, allow_dirty=False)
        
    # Should not raise when allow_dirty is True
    init.ensure_clean_working_tree(temp_git_repo, allow_dirty=True)


def test_selective_staging(temp_git_repo):
    unrelated = temp_git_repo / "unrelated.txt"
    unrelated.write_text("must not be staged", encoding="utf-8")
    
    init.scaffold_workflow(temp_git_repo, default_branch="main")
    init.scaffold_profile(temp_git_repo, profile_id="domain-science")
    init.merge_claude_settings(temp_git_repo)
    init.inject_readme_badge(temp_git_repo, slug="example-org/test-project")
    
    init.stage_signoff_files(temp_git_repo)
    
    status = subprocess.check_output(["git", "status", "--porcelain"], cwd=temp_git_repo, text=True)
    assert "?? unrelated.txt" in status
    assert "A  .github/workflows/signoff.yml" in status or "M  .github/workflows/signoff.yml" in status
    assert "A  .signoff/profile.md" in status
    assert "A  .claude/settings.json" in status
    assert "M  README.md" in status


def test_branch_collision_handling(temp_git_repo):
    # Pre-create the signoff/init branch
    subprocess.run(["git", "branch", "signoff/init"], cwd=temp_git_repo, check=True)
    resolved = init.resolve_branch_name(temp_git_repo, "signoff/init", non_interactive=True)
    assert resolved != "signoff/init"
    assert resolved.startswith("signoff/init-")


# --- T1.5: GitHub Ruleset Automation & Degradation ---

def test_setup_ruleset_gh_already_exists(temp_git_repo):
    with patch("shutil.which", return_value="/usr/local/bin/gh"), \
         patch("subprocess.run") as mock_run:
        # mock gh auth status (success)
        mock_auth = MagicMock(returncode=0, stdout="", stderr="")
        # mock gh api list rulesets (contains Signoff Enforcement)
        mock_list = MagicMock(
            returncode=0,
            stdout=json.dumps([{"id": 123, "name": "Signoff Enforcement"}]),
            stderr="",
        )
        mock_run.side_effect = [mock_auth, mock_list]
        
        result = init.setup_ruleset(temp_git_repo, slug="org/repo", default_branch="main")
        assert result.status == "already_exists"


def test_setup_ruleset_gh_create_success(temp_git_repo):
    with patch("shutil.which", return_value="/usr/local/bin/gh"), \
         patch("subprocess.run") as mock_run:
        mock_auth = MagicMock(returncode=0, stdout="", stderr="")
        mock_list = MagicMock(returncode=0, stdout="[]", stderr="")
        mock_create = MagicMock(
            returncode=0,
            stdout=json.dumps({"id": 456, "name": "Signoff Enforcement"}),
            stderr="",
        )
        mock_run.side_effect = [mock_auth, mock_list, mock_create]
        
        result = init.setup_ruleset(temp_git_repo, slug="org/repo", default_branch="main")
        assert result.status == "created"


def test_setup_ruleset_gh_missing_fallback(temp_git_repo):
    with patch("shutil.which", return_value=None), \
         patch("webbrowser.open") as mock_browser:
        result = init.setup_ruleset(temp_git_repo, slug="org/repo", default_branch="main", open_browser=True)
        assert result.status == "fallback_manual"
        assert result.rules_url == "https://github.com/org/repo/settings/rules"
        assert (temp_git_repo / ".signoff" / "ruleset.json").is_file() or (temp_git_repo / "verify" / "ruleset.json").is_file()
        mock_browser.assert_called_once_with("https://github.com/org/repo/settings/rules")


def test_setup_ruleset_gh_unauthenticated(temp_git_repo):
    with patch("shutil.which", return_value="/usr/local/bin/gh"), \
         patch("subprocess.run") as mock_run:
        mock_auth = MagicMock(returncode=1, stdout="", stderr="not logged in")
        mock_run.return_value = mock_auth
        
        result = init.setup_ruleset(temp_git_repo, slug="org/repo", default_branch="main")
        assert result.status == "fallback_manual"
        assert (temp_git_repo / ".signoff" / "ruleset.json").is_file() or (temp_git_repo / "verify" / "ruleset.json").is_file()


def test_setup_ruleset_gh_permission_denied(temp_git_repo):
    with patch("shutil.which", return_value="/usr/local/bin/gh"), \
         patch("subprocess.run") as mock_run:
        mock_auth = MagicMock(returncode=0, stdout="", stderr="")
        mock_list = MagicMock(returncode=1, stdout="", stderr="HTTP 403: Resource not accessible by integration")
        mock_run.side_effect = [mock_auth, mock_list]
        
        result = init.setup_ruleset(temp_git_repo, slug="org/repo", default_branch="main")
        assert result.status == "fallback_manual"


def test_setup_ruleset_skip_flag(temp_git_repo):
    with patch("shutil.which") as mock_which:
        result = init.setup_ruleset(temp_git_repo, slug="org/repo", default_branch="main", skip_ruleset=True)
        assert result.status == "skipped"
        mock_which.assert_not_called()


# --- T1.6: CLI Arguments & TTY Handling ---

def test_parse_cli_arguments():
    args = init.parse_args(["--non-interactive", "--profile", "domain-science", "--branch", "custom/init", "--skip-ruleset", "--skip-badge", "--allow-dirty"])
    assert args.non_interactive is True
    assert args.profile == "domain-science"
    assert args.branch == "custom/init"
    assert args.skip_ruleset is True
    assert args.skip_badge is True
    assert args.allow_dirty is True


def test_non_tty_stdin_fallback(monkeypatch):
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    with patch("builtins.open", side_effect=OSError("No TTY")):
        val = init.prompt_user("Choose option", default="default_val", non_interactive=True)
        assert val == "default_val"


# --- T1.7: End-to-End Execution Tests ---

def test_end_to_end_init(temp_git_repo):
    result = init.run_init(
        repo_root=temp_git_repo,
        profile_id="domain-science",
        branch="signoff/init",
        slug="example-org/test-project",
        skip_ruleset=True,
        non_interactive=True,
    )
    assert result.success is True
    assert result.branch == "signoff/init"
    assert result.pr_url == "https://github.com/example-org/test-project/compare/main...signoff/init?expand=1"
    
    # Verify current branch is signoff/init
    current_branch = subprocess.check_output(["git", "branch", "--show-current"], cwd=temp_git_repo, text=True).strip()
    assert current_branch == "signoff/init"
    
    # Verify attestation commit exists at HEAD
    head_msg = subprocess.check_output(["git", "log", "-1", "--format=%B"], cwd=temp_git_repo, text=True)
    assert "[SIGNOFF " in head_msg
    assert "Signoff-Spec-Version: 1.0" in head_msg
    assert "Signoff-Status: VERIFIED_BY_HUMAN" in head_msg
    assert "Signoff-Verified-By: test@example.com" in head_msg
    assert "interview=cursory/domain-science" in head_msg or "interview=standard/domain-science" in head_msg
    
    # Run reference verifier on the created repo
    verify_script = Path(__file__).parent.parent / "verify" / "verify_signoff.py"
    if verify_script.is_file():
        proc = subprocess.run(
            [sys.executable, str(verify_script), "--mode", "head", "--target", "HEAD"],
            cwd=temp_git_repo,
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 0, f"Verifier failed: {proc.stdout}\n{proc.stderr}"


def test_end_to_end_unborn_head(tmp_path):
    repo = tmp_path / "unborn_e2e"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "remote", "add", "origin", "https://github.com/example-org/unborn-e2e.git"], cwd=repo, check=True)

    result = init.run_init(
        repo_root=repo,
        profile_id="software-general",
        branch="signoff/init",
        slug="example-org/unborn-e2e",
        skip_ruleset=True,
        non_interactive=True,
    )
    assert result.success is True
    assert (repo / ".github" / "workflows" / "signoff.yml").is_file()
    assert (repo / ".signoff" / "profile.md").is_file()
    assert (repo / ".claude" / "settings.json").is_file()
    assert (repo / "README.md").is_file()

    # Verify commit log
    log = subprocess.check_output(["git", "log", "--oneline"], cwd=repo, text=True).strip().splitlines()
    assert len(log) >= 2  # scaffold commit + attestation commit


def test_attestation_carries_profile_digest(temp_git_repo):
    init.scaffold_profile(temp_git_repo, profile_id="domain-science")
    profile_data = (temp_git_repo / ".signoff" / "profile.md").read_bytes()
    expected_digest = init.profile_block_digest(profile_data)
    
    result = init.run_init(
        repo_root=temp_git_repo,
        profile_id="domain-science",
        branch="signoff/init",
        slug="example-org/test-project",
        skip_ruleset=True,
        non_interactive=True,
    )
    assert result.success is True
    head_msg = subprocess.check_output(["git", "log", "-1", "--format=%B"], cwd=temp_git_repo, text=True)
    assert f"sha256:{expected_digest}" in head_msg or f"/domain-science/sha256:{expected_digest}" in head_msg

