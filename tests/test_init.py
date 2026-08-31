"""Tests for standalone repo initializer (init.py)."""

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
import init

SKILL_SRC = Path(__file__).parent.parent / "skills" / "signoff"


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
        "https://github.com/owner/../repo",
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
    assert ctx.is_unborn is True


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


def test_vendor_skill_from_local_source(temp_git_repo):
    init.vendor_skill(temp_git_repo, source=SKILL_SRC)
    dest = temp_git_repo / ".claude" / "skills" / "signoff"
    assert (dest / "SKILL.md").is_file()
    head = (dest / "SKILL.md").read_text(encoding="utf-8")[:2048]
    assert "name: signoff" in head
    # Self-contained copy: relative links into specs/ and profiles/ must resolve
    assert (dest / "specs" / "gsa-core.md").is_file()
    assert (dest / "profiles" / "domain-science.md").is_file()
    assert (dest / "HARNESSES.md").is_file()
    # Every vendored copy is self-describing: local installs stamp too
    stamp = (dest / init.VENDOR_STAMP_FILENAME).read_text(encoding="utf-8")
    assert "ref: local (--skill-source)" in stamp
    assert str(SKILL_SRC.resolve()) in stamp
    assert "commit: " in stamp


def test_vendor_skill_clones_pinned_ref(temp_git_repo):
    """The default vendor path clones at SKILL_SOURCE_REF, never the default
    branch, and stamps the source commit — the v0.4.0 'unpinned vendor
    payload' caveat closed."""
    import shutil as _shutil

    clone_cmds = []
    fake_sha = "d" * 40

    def fake_run(cmd, **kwargs):
        if cmd[:2] == ["git", "clone"]:
            clone_cmds.append(cmd)
            _shutil.copytree(SKILL_SRC, Path(cmd[-1]) / "skills" / "signoff")
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        if cmd[:2] == ["git", "-C"] and "rev-parse" in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout=fake_sha + "\n", stderr="")
        raise AssertionError(f"unexpected subprocess call: {cmd}")

    with patch.object(init.subprocess, "run", side_effect=fake_run):
        init.vendor_skill(temp_git_repo)

    (clone_cmd,) = clone_cmds
    ref_idx = clone_cmd.index("--branch") + 1
    assert clone_cmd[ref_idx] == init.SKILL_SOURCE_REF
    stamp = (
        temp_git_repo / ".claude" / "skills" / "signoff" / init.VENDOR_STAMP_FILENAME
    ).read_text(encoding="utf-8")
    assert f"ref: {init.SKILL_SOURCE_REF}" in stamp
    assert f"commit: {fake_sha}" in stamp
    assert f"source: {init.SKILL_SOURCE_REPO}" in stamp


def test_skill_source_ref_pin_consistency():
    """SKILL_SOURCE_REF must be a tag tag.yml actually creates, and the tag
    every install snippet serves init.py from — one moving part, bumped
    together, or pinned-script runs vendor a payload that doesn't exist or
    doesn't match."""
    import re

    repo_root = Path(__file__).parent.parent
    ref = init.SKILL_SOURCE_REF

    tag_wf = (repo_root / ".github" / "workflows" / "tag.yml").read_text(encoding="utf-8")
    m = re.search(r"^\s*PINS:\s*(.+?)\s*$", tag_wf, re.MULTILINE)
    assert m, "PINS not declared in tag.yml"
    assert ref in m.group(1).split(), (
        f"SKILL_SOURCE_REF {ref!r} missing from tag.yml PINS — the pin tag would never be created"
    )

    snippet_re = re.compile(r"jerrylin96/signoff/(init-v[\w.]+)/init\.py")
    for rel in ("README.md", "verify/README.md", "site/index.html"):
        text = (repo_root / rel).read_text(encoding="utf-8")
        served = snippet_re.findall(text)
        assert served, f"{rel} has no pinned init.py install snippet"
        assert set(served) == {ref}, (
            f"{rel} serves init.py at {sorted(set(served))}, but SKILL_SOURCE_REF is {ref!r}"
        )


def test_vendor_skill_replaces_existing(temp_git_repo):
    dest = temp_git_repo / ".claude" / "skills" / "signoff"
    dest.mkdir(parents=True)
    (dest / "stale.md").write_text("old copy", encoding="utf-8")
    init.vendor_skill(temp_git_repo, source=SKILL_SRC)
    assert not (dest / "stale.md").exists()
    assert (dest / "SKILL.md").is_file()


def test_vendor_skill_invalid_source_fails(temp_git_repo, tmp_path):
    empty_src = tmp_path / "not-a-skill"
    empty_src.mkdir()
    with pytest.raises(RuntimeError, match="does not contain SKILL.md"):
        init.vendor_skill(temp_git_repo, source=empty_src)


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


def test_inject_readme_badge_code_fence(tmp_path):
    repo = tmp_path / "fence_repo"
    repo.mkdir()
    readme = repo / "README.md"
    readme.write_text("```bash\n# install curl\ncurl -O x\n```\n\n# Actual Title\n\nSome body.\n", encoding="utf-8")
    init.inject_readme_badge(repo, slug="org/fenced-project")
    content = readme.read_text(encoding="utf-8")
    assert "# Actual Title\n\n[![attested by humans]" in content


# --- T1.4: Working Tree Safety & Branch Management ---

def test_dirty_working_tree_guard(temp_git_repo):
    dirty_file = temp_git_repo / "unrelated.txt"
    dirty_file.write_text("unstaged change", encoding="utf-8")
    
    with pytest.raises(RuntimeError, match="Working tree has uncommitted changes"):
        init.ensure_clean_working_tree(temp_git_repo, allow_dirty=False)
        
    init.ensure_clean_working_tree(temp_git_repo, allow_dirty=True)


def test_dirty_working_tree_unstaged_readme(temp_git_repo):
    readme = temp_git_repo / "README.md"
    readme.write_text("# Modified Header\n\nBody text\n", encoding="utf-8")
    # README is on the allowlist, so this should not raise
    init.ensure_clean_working_tree(temp_git_repo, allow_dirty=False)


def test_selective_staging(temp_git_repo):
    unrelated = temp_git_repo / "unrelated.txt"
    unrelated.write_text("must not be staged", encoding="utf-8")
    
    init.scaffold_workflow(temp_git_repo, default_branch="main")
    init.scaffold_profile(temp_git_repo, profile_id="domain-science")
    init.vendor_skill(temp_git_repo, source=SKILL_SRC)
    init.inject_readme_badge(temp_git_repo, slug="example-org/test-project")

    init.stage_signoff_files(temp_git_repo)

    status = subprocess.check_output(["git", "status", "--porcelain"], cwd=temp_git_repo, text=True)
    assert "?? unrelated.txt" in status
    assert "A  .github/workflows/signoff.yml" in status or "M  .github/workflows/signoff.yml" in status
    assert "A  .signoff/profile.md" in status
    assert "A  .claude/skills/signoff/SKILL.md" in status
    assert "M  README.md" in status


def test_branch_collision_handling(temp_git_repo):
    subprocess.run(["git", "branch", "signoff/init"], cwd=temp_git_repo, check=True)
    resolved = init.resolve_branch_name(temp_git_repo, "signoff/init")
    assert resolved != "signoff/init"
    assert resolved.startswith("signoff/init-")


# --- T1.5: GitHub Ruleset Automation & Degradation ---

def test_setup_ruleset_gh_already_exists(temp_git_repo):
    with patch("shutil.which", return_value="/usr/local/bin/gh"), \
         patch("subprocess.run") as mock_run:
        mock_auth = MagicMock(returncode=0, stdout="", stderr="")
        mock_list = MagicMock(
            returncode=0,
            stdout=json.dumps([{"id": 123, "name": "Signoff Enforcement"}]),
            stderr="",
        )
        mock_run.side_effect = [mock_auth, mock_list]
        
        result = init.setup_ruleset(temp_git_repo, slug="org/repo")
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
        
        result = init.setup_ruleset(temp_git_repo, slug="org/repo")
        assert result.status == "created"


def test_setup_ruleset_gh_missing_fallback(temp_git_repo):
    with patch("shutil.which", return_value=None), \
         patch("webbrowser.open") as mock_browser:
        result = init.setup_ruleset(temp_git_repo, slug="org/repo", open_browser=True)
        assert result.status == "fallback_manual"
        assert result.rules_url == "https://github.com/org/repo/settings/rules"
        assert (temp_git_repo / ".signoff" / "ruleset.json").is_file()
        mock_browser.assert_called_once_with("https://github.com/org/repo/settings/rules")


def test_setup_ruleset_gh_unauthenticated(temp_git_repo):
    with patch("shutil.which", return_value="/usr/local/bin/gh"), \
         patch("subprocess.run") as mock_run:
        mock_auth = MagicMock(returncode=1, stdout="", stderr="not logged in")
        mock_run.return_value = mock_auth
        
        result = init.setup_ruleset(temp_git_repo, slug="org/repo")
        assert result.status == "fallback_manual"
        assert (temp_git_repo / ".signoff" / "ruleset.json").is_file()


def test_setup_ruleset_gh_permission_denied(temp_git_repo):
    with patch("shutil.which", return_value="/usr/local/bin/gh"), \
         patch("subprocess.run") as mock_run:
        mock_auth = MagicMock(returncode=0, stdout="", stderr="")
        mock_list = MagicMock(returncode=1, stdout="", stderr="HTTP 403: Resource not accessible by integration")
        mock_run.side_effect = [mock_auth, mock_list]
        
        result = init.setup_ruleset(temp_git_repo, slug="org/repo")
        assert result.status == "fallback_manual"


def test_setup_ruleset_skip_flag(temp_git_repo):
    with patch("shutil.which") as mock_which:
        result = init.setup_ruleset(temp_git_repo, slug="org/repo", skip_ruleset=True)
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


# --- T1.7: End-to-End Execution Tests & Honest Attestation ---

def test_end_to_end_init(temp_git_repo):
    result = init.run_init(
        repo_root=temp_git_repo,
        profile_id="domain-science",
        branch="signoff/init",
        slug="example-org/test-project",
        skip_ruleset=True,
        non_interactive=True,
        skill_source=SKILL_SRC,
    )
    assert result.success is True
    assert result.branch == "signoff/init"
    assert result.pr_url == "https://github.com/example-org/test-project/compare/main...signoff/init?expand=1"
    
    # Verify current branch is signoff/init
    current_branch = subprocess.check_output(["git", "branch", "--show-current"], cwd=temp_git_repo, text=True).strip()
    assert current_branch == "signoff/init"
    
    # Verify scaffold commit exists at HEAD and NO fake attestation was created
    head_msg = subprocess.check_output(["git", "log", "-1", "--format=%B"], cwd=temp_git_repo, text=True)
    assert "chore: scaffold git signoff attestation" in head_msg
    assert "[SIGNOFF " not in head_msg

    # Verify setup branch has no upstream tracking set
    up = subprocess.run(["git", "rev-parse", "--abbrev-ref", "signoff/init@{upstream}"], cwd=temp_git_repo, capture_output=True, text=True)
    assert up.returncode != 0



def test_base_branch_safety(temp_git_repo):
    # Switch to a feature branch and create unmerged commit
    subprocess.run(["git", "checkout", "-b", "feature-wip"], cwd=temp_git_repo, check=True)
    (temp_git_repo / "wip.txt").write_text("unmerged work", encoding="utf-8")
    subprocess.run(["git", "add", "wip.txt"], cwd=temp_git_repo, check=True)
    subprocess.run(["git", "commit", "-m", "WIP commit"], cwd=temp_git_repo, check=True)
    
    # Run init while on feature-wip
    result = init.run_init(
        repo_root=temp_git_repo,
        profile_id="domain-science",
        branch="signoff/init",
        slug="example-org/test-project",
        skip_ruleset=True,
        non_interactive=True,
        skill_source=SKILL_SRC,
    )
    assert result.branch == "signoff/init"
    
    # Verify signoff/init was branched from main, so wip.txt is NOT in signoff/init
    assert not (temp_git_repo / "wip.txt").exists()
    log = subprocess.check_output(["git", "log", "--oneline"], cwd=temp_git_repo, text=True)
    assert "WIP commit" not in log


def test_base_branch_develop_only(tmp_path):
    repo = tmp_path / "dev_repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "develop"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Dev User"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "dev@example.com"], cwd=repo, check=True)
    (repo / "README.md").write_text("# Dev Repo\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=repo, check=True)

    result = init.run_init(
        repo_root=repo,
        profile_id="software-general",
        branch="signoff/init",
        skip_ruleset=True,
        non_interactive=True,
        skill_source=SKILL_SRC,
    )
    assert result.success is True
    assert result.branch == "signoff/init"
    current_branch = subprocess.check_output(["git", "branch", "--show-current"], cwd=repo, text=True).strip()
    assert current_branch == "signoff/init"


def test_base_branch_custom_unlisted_name(tmp_path):
    repo = tmp_path / "custom_repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "my-custom-base-branch"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Custom User"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "custom@example.com"], cwd=repo, check=True)
    (repo / "README.md").write_text("# Custom Base\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=repo, check=True)

    result = init.run_init(
        repo_root=repo,
        profile_id="software-general",
        branch="signoff/init",
        skip_ruleset=True,
        non_interactive=True,
        skill_source=SKILL_SRC,
    )
    assert result.success is True
    assert result.branch == "signoff/init"


def test_checkout_failure_leaves_tree_clean(temp_git_repo):
    # Pass an invalid branch name that git checkout rejects
    with pytest.raises(RuntimeError, match="Failed to create branch"):
        init.run_init(
            repo_root=temp_git_repo,
            branch="bad..branch/name..",
            skip_ruleset=True,
            non_interactive=True,
            skill_source=SKILL_SRC,
        )

    # Verify no scaffold files were created / left stranded
    assert not (temp_git_repo / ".claude").exists()
    assert not (temp_git_repo / ".github").exists()
    assert not (temp_git_repo / ".signoff").exists()
    status = subprocess.check_output(["git", "status", "--porcelain"], cwd=temp_git_repo, text=True)
    assert status.strip() == ""


def test_vendor_failure_rolls_back_scaffold(temp_git_repo):
    # A post-branch failure (here: an invalid skill source, standing in for an
    # offline vendor clone) must leave the repo exactly as it was found — not
    # stranded on the setup branch with half-written files.
    empty_src = temp_git_repo.parent / "not-a-skill"
    empty_src.mkdir()

    with pytest.raises(RuntimeError, match="does not contain SKILL.md"):
        init.run_init(
            repo_root=temp_git_repo,
            branch="signoff/init",
            skip_ruleset=True,
            non_interactive=True,
            skill_source=empty_src,
        )

    # Back on the original branch, setup branch gone.
    current = subprocess.check_output(["git", "branch", "--show-current"], cwd=temp_git_repo, text=True).strip()
    assert current == "main"
    branches = subprocess.check_output(["git", "branch"], cwd=temp_git_repo, text=True)
    assert "signoff/init" not in branches

    # No scaffold artifacts left behind, working tree clean.
    assert not (temp_git_repo / ".github").exists()
    assert not (temp_git_repo / ".signoff").exists()
    assert not (temp_git_repo / ".claude").exists()
    status = subprocess.check_output(["git", "status", "--porcelain"], cwd=temp_git_repo, text=True)
    assert status.strip() == ""


def test_rollback_preserves_unrelated_dir_content(temp_git_repo):
    # Rollback prunes only what init created: a pre-existing .github/ with an
    # unrelated workflow must survive a failed run untouched.
    other_wf = temp_git_repo / ".github" / "workflows" / "ci.yml"
    other_wf.parent.mkdir(parents=True)
    other_wf.write_text("name: ci\n", encoding="utf-8")
    subprocess.run(["git", "add", ".github/workflows/ci.yml"], cwd=temp_git_repo, check=True)
    subprocess.run(["git", "commit", "-m", "add ci"], cwd=temp_git_repo, check=True)

    empty_src = temp_git_repo.parent / "not-a-skill-2"
    empty_src.mkdir()
    with pytest.raises(RuntimeError, match="does not contain SKILL.md"):
        init.run_init(
            repo_root=temp_git_repo,
            branch="signoff/init",
            skip_ruleset=True,
            non_interactive=True,
            skill_source=empty_src,
        )

    # init's workflow is gone; the unrelated one and its dir remain.
    assert not (temp_git_repo / ".github" / "workflows" / "signoff.yml").exists()
    assert other_wf.exists()
    assert other_wf.read_text(encoding="utf-8") == "name: ci\n"
    status = subprocess.check_output(["git", "status", "--porcelain"], cwd=temp_git_repo, text=True)
    assert status.strip() == ""


def test_rollback_reverts_readme_badge(temp_git_repo):
    # A failure after the README badge is injected must restore the committed
    # README, not leave the badge stranded as an uncommitted modification.
    original = (temp_git_repo / "README.md").read_text(encoding="utf-8")
    with patch.object(init, "stage_signoff_files", side_effect=RuntimeError("boom after badge")):
        with pytest.raises(RuntimeError, match="boom after badge"):
            init.run_init(
                repo_root=temp_git_repo,
                slug="org/proj",
                branch="signoff/init",
                skip_ruleset=True,
                non_interactive=True,
                skill_source=SKILL_SRC,
            )
    assert (temp_git_repo / "README.md").read_text(encoding="utf-8") == original
    status = subprocess.check_output(["git", "status", "--porcelain"], cwd=temp_git_repo, text=True)
    assert status.strip() == ""


def test_rollback_unborn_head(tmp_path):
    # A repo with no commits yet must return to its unborn branch on failure.
    repo = tmp_path / "unborn"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@e.com"], cwd=repo, check=True)

    empty_src = tmp_path / "not-a-skill-unborn"
    empty_src.mkdir()
    with pytest.raises(RuntimeError, match="does not contain SKILL.md"):
        init.run_init(
            repo_root=repo,
            branch="signoff/init",
            skip_ruleset=True,
            non_interactive=True,
            skill_source=empty_src,
        )

    current = subprocess.check_output(["git", "branch", "--show-current"], cwd=repo, text=True).strip()
    assert current == "main"
    assert not (repo / ".github").exists()
    assert not (repo / ".signoff").exists()


def test_base_branch_origin_fallback(tmp_path):
    # Setup upstream remote with main branch
    origin_dir = tmp_path / "origin.git"
    origin_dir.mkdir()
    subprocess.run(["git", "init", "--bare", "-b", "main"], cwd=origin_dir, check=True, capture_output=True)

    # Setup local clone
    local_dir = tmp_path / "clone"
    subprocess.run(["git", "clone", str(origin_dir), str(local_dir)], check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Dev"], cwd=local_dir, check=True)
    subprocess.run(["git", "config", "user.email", "dev@example.com"], cwd=local_dir, check=True)

    # Initial commit on main and push
    (local_dir / "README.md").write_text("# Origin Repo\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=local_dir, check=True)
    subprocess.run(["git", "commit", "-m", "Base commit"], cwd=local_dir, check=True)
    subprocess.run(["git", "push", "origin", "main"], cwd=local_dir, check=True)

    # Create feature branch with unmerged commit, then delete local main
    subprocess.run(["git", "checkout", "-b", "feature-x"], cwd=local_dir, check=True)
    (local_dir / "feature.txt").write_text("unmerged feature commit", encoding="utf-8")
    subprocess.run(["git", "add", "feature.txt"], cwd=local_dir, check=True)
    subprocess.run(["git", "commit", "-m", "Unmerged feature work"], cwd=local_dir, check=True)
    subprocess.run(["git", "branch", "-D", "main"], cwd=local_dir, check=True)

    # Run init while on feature-x
    result = init.run_init(
        repo_root=local_dir,
        profile_id="software-general",
        branch="signoff/init",
        skip_ruleset=True,
        non_interactive=True,
        skill_source=SKILL_SRC,
    )
    assert result.success is True
    assert result.branch == "signoff/init"

    # Verify signoff/init branched from origin/main, so feature.txt is NOT in signoff/init
    assert not (local_dir / "feature.txt").exists()
    log = subprocess.check_output(["git", "log", "--oneline"], cwd=local_dir, text=True)
    assert "Unmerged feature work" not in log

    # Verify setup branch does NOT track origin/main
    up = subprocess.run(["git", "rev-parse", "--abbrev-ref", "signoff/init@{upstream}"], cwd=local_dir, capture_output=True, text=True)
    assert up.returncode != 0, "setup branch must not track origin/main or any default branch"



def test_profile_text_byte_parity():
    from signoff_mcp.profile import profile_block_digest

    repo_root = Path(__file__).parent.parent
    for pid in ("domain-science", "software-general"):
        profile_file = repo_root / "skills" / "signoff" / "profiles" / f"{pid}.md"
        assert profile_file.is_file()
        file_lines = profile_file.read_text(encoding="utf-8").splitlines(keepends=True)
        block_lines = []
        recording = False
        for line in file_lines:
            if "INTERVIEW-PROFILE:BEGIN (sole customization point" in line:
                recording = True
            if recording:
                block_lines.append(line)
            if "INTERVIEW-PROFILE:END" in line and recording:
                break
        shipped_block = "".join(block_lines)
        embedded_block = init.PROFILES[pid]
        assert shipped_block == embedded_block
        assert profile_block_digest(shipped_block.encode("utf-8")) == profile_block_digest(
            embedded_block.encode("utf-8")
        )


def test_init_scripts_byte_parity():
    repo_root = Path(__file__).parent.parent
    root_init = (repo_root / "init.py").read_text(encoding="utf-8")
    pkg_init = (repo_root / "signoff_mcp" / "init.py").read_text(encoding="utf-8")
    assert root_init == pkg_init


def test_package_namespaced_init():
    from signoff_mcp import init as mcp_init
    from signoff_mcp import init_cli

    assert init_cli.init is mcp_init
    assert hasattr(mcp_init, "run_init")


def test_pyproject_does_not_package_top_level_init():
    repo_root = Path(__file__).parent.parent
    pyproject_content = (repo_root / "pyproject.toml").read_text(encoding="utf-8")
    assert "py-modules" not in pyproject_content
    assert 'include = ["signoff_mcp*"]' in pyproject_content


def test_versions_are_synchronized():
    """pyproject.toml and signoff_mcp.__version__ agree (release.yml derives tags from pyproject)."""
    import re

    import signoff_mcp

    repo_root = Path(__file__).parent.parent
    pyproject_content = (repo_root / "pyproject.toml").read_text(encoding="utf-8")
    m = re.search(r'^version = "([^"]+)"$', pyproject_content, re.MULTILINE)
    assert m, "pyproject.toml must declare a project version"
    assert m.group(1) == signoff_mcp.__version__





