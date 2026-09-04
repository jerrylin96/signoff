"""Tests for standalone repo initializer (init.py)."""

import json
import shutil
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
        if cmd[:2] == ["git", "check-ignore"]:
            return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="")
        if cmd[:2] == ["git", "ls-files"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
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
    assert init.SKILL_SOURCE_REF == "init-v5", f"Expected init-v5, got {init.SKILL_SOURCE_REF}"
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
    (dest / "SKILL.md").write_text("# existing skill", encoding="utf-8")
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
    with pytest.raises(RuntimeError, match="Working tree has uncommitted changes"):
        init.ensure_clean_working_tree(temp_git_repo, allow_dirty=False)


def test_mutation_boundary_rejects_dirty_readme_with_allow_dirty(temp_git_repo):
    readme = temp_git_repo / "README.md"
    readme.write_text("# User work that must not be overwritten\n", encoding="utf-8")
    paths = [readme, temp_git_repo / ".claude" / "skills" / "signoff"]

    with pytest.raises(RuntimeError, match="Managed scaffold paths contain uncommitted"):
        init.ensure_mutation_boundary_clean(temp_git_repo, paths)


def test_mutation_boundary_rejects_prestaged_unrelated_change(temp_git_repo):
    unrelated = temp_git_repo / "unrelated.txt"
    unrelated.write_text("staged user work\n", encoding="utf-8")
    subprocess.run(["git", "add", "unrelated.txt"], cwd=temp_git_repo, check=True)

    with pytest.raises(RuntimeError, match="index contains staged changes"):
        init.ensure_mutation_boundary_clean(temp_git_repo, [temp_git_repo / "README.md"])


def test_only_scaffold_paths_staged_rejects_unrelated_path(temp_git_repo):
    unrelated = temp_git_repo / "unrelated.txt"
    unrelated.write_text("staged concurrently\n", encoding="utf-8")
    subprocess.run(["git", "add", "unrelated.txt"], cwd=temp_git_repo, check=True)

    with pytest.raises(RuntimeError, match="unrelated paths became staged"):
        init.ensure_only_scaffold_paths_staged(temp_git_repo, [temp_git_repo / "README.md"])


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


def test_rollback_warns_when_remote_ruleset_remains(temp_git_repo, capsys):
    with (
        patch.object(init, "setup_ruleset", return_value=init.RulesetResult("created")),
        patch.object(init, "stage_signoff_files", side_effect=RuntimeError("fail after ruleset creation")),
    ):
        with pytest.raises(RuntimeError, match="fail after ruleset creation"):
            init.run_init(
                repo_root=temp_git_repo,
                branch="signoff/init",
                non_interactive=True,
                skill_source=SKILL_SRC,
            )

    err = capsys.readouterr().err
    assert "local Git state restored" in err
    assert "GitHub ruleset 'Signoff Enforcement' remains configured" in err
    assert "rollback only restores local Git state" in err


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


# --- Slice 2: Multi-Harness Architecture & Policy A Tests ---

# 1. Policy A Symlink, Parent-Path, Conflict & Git-Ignore Refusal
def test_policy_a_refuses_destination_symlink(temp_git_repo, tmp_path):
    target = tmp_path / "external_target"
    target.mkdir()
    dest = temp_git_repo / ".claude" / "skills" / "signoff"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.symlink_to(target)
    with pytest.raises(RuntimeError, match=r"Destination .claude/skills/signoff is a symbolic link"):
        init.validate_policy_a(dest, temp_git_repo)
    assert target.exists()


def test_policy_a_refuses_parent_symlink(temp_git_repo, tmp_path):
    target = tmp_path / "external_parent"
    target.mkdir()
    parent = temp_git_repo / ".agents"
    parent.symlink_to(target)
    dest = temp_git_repo / ".agents" / "skills" / "signoff"
    with pytest.raises(RuntimeError, match=r"Destination .agents is a symbolic link"):
        init.validate_policy_a(dest, temp_git_repo)
    assert target.exists()


def test_policy_a_refuses_ordinary_file_parent(temp_git_repo):
    parent = temp_git_repo / ".agents"
    parent.write_text("not a directory", encoding="utf-8")
    dest = temp_git_repo / ".agents" / "skills" / "signoff"
    with pytest.raises(RuntimeError, match=r"Parent path .agents exists as an ordinary file"):
        init.validate_policy_a(dest, temp_git_repo)


def test_policy_a_refuses_gitignore_match(temp_git_repo):
    gitignore = temp_git_repo / ".gitignore"
    gitignore.write_text(".claude/skills/signoff\n", encoding="utf-8")
    dest = temp_git_repo / ".claude" / "skills" / "signoff"
    with pytest.raises(RuntimeError, match=r"Destination .claude/skills/signoff is ignored by git"):
        init.validate_policy_a(dest, temp_git_repo)


def test_policy_a_accepts_negated_gitignore(temp_git_repo):
    gitignore = temp_git_repo / ".gitignore"
    gitignore.write_text(".claude/*\n!.claude/skills/\n", encoding="utf-8")
    dest = temp_git_repo / ".claude" / "skills" / "signoff"
    # Should not raise
    init.validate_policy_a(dest, temp_git_repo)


def test_policy_a_refuses_preexisting_ignored_untracked_files(temp_git_repo):
    dest = temp_git_repo / ".claude" / "skills" / "signoff"
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "SKILL.md").write_text("# existing skill", encoding="utf-8")
    gitignore = temp_git_repo / ".gitignore"
    gitignore.write_text("*.tmp\n", encoding="utf-8")
    (dest / "scratch.tmp").write_text("ignored untracked", encoding="utf-8")

    with pytest.raises(RuntimeError, match=r"contains ignored untracked files"):
        init.validate_policy_a(dest, temp_git_repo, allow_dirty=False)


def test_policy_a_refuses_preexisting_ignored_untracked_files_with_allow_dirty(temp_git_repo):
    dest = temp_git_repo / ".claude" / "skills" / "signoff"
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "SKILL.md").write_text("# existing skill", encoding="utf-8")
    gitignore = temp_git_repo / ".gitignore"
    gitignore.write_text("*.tmp\n", encoding="utf-8")
    (dest / "scratch.tmp").write_text("ignored untracked", encoding="utf-8")

    with pytest.raises(RuntimeError, match=r"contains ignored untracked files"):
        init.validate_policy_a(dest, temp_git_repo, allow_dirty=True)


def test_policy_a_refuses_destination_ordinary_file(temp_git_repo):
    dest = temp_git_repo / ".claude" / "skills" / "signoff"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("regular file collision", encoding="utf-8")
    with pytest.raises(RuntimeError, match=r"Destination .claude/skills/signoff exists as an ordinary file"):
        init.validate_policy_a(dest, temp_git_repo)


def test_policy_a_refuses_unrelated_nonempty_directory(temp_git_repo):
    dest = temp_git_repo / ".claude" / "skills" / "signoff"
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "other.txt").write_text("unrelated data", encoding="utf-8")
    with pytest.raises(RuntimeError, match=r"is a non-empty directory not recognized as a /signoff skill"):
        init.validate_policy_a(dest, temp_git_repo)


# 2. Detection & Resolution Tests
def test_detect_skill_destinations_scenarios(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    claude = repo / ".claude" / "skills" / "signoff"
    agents = repo / ".agents" / "skills" / "signoff"

    # Tier 3: Greenfield -> None
    assert init.detect_skill_destinations(repo) is None

    # Tier 2: claude signals only
    (repo / "CLAUDE.md").write_text("instructions", encoding="utf-8")
    assert init.detect_skill_destinations(repo) == [claude]
    (repo / "CLAUDE.md").unlink()

    # Tier 2: agents signals only
    (repo / "AGENTS.md").write_text("instructions", encoding="utf-8")
    assert init.detect_skill_destinations(repo) == [agents]
    (repo / "AGENTS.md").unlink()

    # Tier 2: mixed signals -> both
    (repo / ".claude").mkdir()
    (repo / ".cursor").mkdir()
    assert init.detect_skill_destinations(repo) == [claude, agents]
    shutil.rmtree(repo / ".claude")
    shutil.rmtree(repo / ".cursor")

    # Tier 1: existing installs take precedence
    claude.mkdir(parents=True)
    (claude / "SKILL.md").write_text("# manual install", encoding="utf-8")
    assert init.detect_skill_destinations(repo) == [claude]

    agents.mkdir(parents=True)
    (agents / "SKILL.md").write_text("# agents install", encoding="utf-8")
    assert init.detect_skill_destinations(repo) == [claude, agents]


def test_resolve_skill_destinations_expansion_union(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    claude = repo / ".claude" / "skills" / "signoff"
    agents = repo / ".agents" / "skills" / "signoff"

    # Greenfield with explicit targets
    assert init.resolve_skill_destinations(repo, skill_target="claude") == [claude]
    assert init.resolve_skill_destinations(repo, skill_target="agents") == [agents]
    assert init.resolve_skill_destinations(repo, skill_target="both") == [claude, agents]

    # Expansion guarantee: existing claude install + skill_target="agents" -> [claude, agents]
    claude.mkdir(parents=True)
    (claude / "SKILL.md").write_text("# claude skill", encoding="utf-8")
    assert init.resolve_skill_destinations(repo, skill_target="agents") == [claude, agents]


def test_resolve_skill_destinations_invalid_target(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    with pytest.raises(ValueError, match="Invalid skill_target"):
        init.resolve_skill_destinations(repo, skill_target="invalid")


def test_resolve_skill_destinations_interactive_prompt(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    claude = repo / ".claude" / "skills" / "signoff"
    agents = repo / ".agents" / "skills" / "signoff"

    # Greenfield non-interactive -> [claude, agents]
    assert init.resolve_skill_destinations(repo, skill_target="auto", non_interactive=True) == [claude, agents]

    # Greenfield interactive choice 2 -> [claude]
    monkeypatch.setattr(init, "prompt_user", lambda *args, **kwargs: "2")
    assert init.resolve_skill_destinations(repo, skill_target="auto", non_interactive=False) == [claude]

    # Greenfield interactive choice 3 -> [agents]
    monkeypatch.setattr(init, "prompt_user", lambda *args, **kwargs: "3")
    assert init.resolve_skill_destinations(repo, skill_target="auto", non_interactive=False) == [agents]

    # Greenfield interactive choice 1 (or default) -> [claude, agents]
    monkeypatch.setattr(init, "prompt_user", lambda *args, **kwargs: "1")
    assert init.resolve_skill_destinations(repo, skill_target="auto", non_interactive=False) == [claude, agents]


# 3. Clean-Tree Boundary & Working Tree Isolation
def test_clean_tree_dirty_skill_destination_aborts(temp_git_repo):
    # Tracked skill destination modified in working tree must abort when allow_dirty=False
    claude_skill = temp_git_repo / ".claude" / "skills" / "signoff"
    claude_skill.mkdir(parents=True)
    (claude_skill / "SKILL.md").write_text("# initial skill", encoding="utf-8")
    subprocess.run(["git", "add", ".claude/skills/signoff"], cwd=temp_git_repo, check=True)
    subprocess.run(["git", "commit", "-m", "Commit skill"], cwd=temp_git_repo, check=True)

    # Now make it dirty by modifying the tracked skill file
    (claude_skill / "SKILL.md").write_text("# dirty modified skill", encoding="utf-8")

    with pytest.raises(RuntimeError, match="Working tree has uncommitted changes"):
        init.ensure_clean_working_tree(temp_git_repo, allow_dirty=False)


def test_clean_tree_tracked_skill_destination_accepted(temp_git_repo):
    claude_skill = temp_git_repo / ".claude" / "skills" / "signoff"
    claude_skill.mkdir(parents=True)
    (claude_skill / "SKILL.md").write_text("# tracked skill", encoding="utf-8")
    subprocess.run(["git", "add", ".claude/skills/signoff"], cwd=temp_git_repo, check=True)
    subprocess.run(["git", "commit", "-m", "Commit skill"], cwd=temp_git_repo, check=True)

    # Clean working tree with tracked skill should not raise
    init.ensure_clean_working_tree(temp_git_repo, allow_dirty=False)


def test_clean_tree_boundary_prefix_check(temp_git_repo):
    # .signoff-old must never match .signoff, and .agents/skills/signoff-old must never match .agents/skills/signoff
    diff_dir = temp_git_repo / ".signoff-old"
    diff_dir.mkdir(parents=True)
    (diff_dir / "file.txt").write_text("unrelated change", encoding="utf-8")
    subprocess.run(["git", "add", ".signoff-old"], cwd=temp_git_repo, check=True)

    with pytest.raises(RuntimeError, match="Working tree has uncommitted changes"):
        init.ensure_clean_working_tree(temp_git_repo, allow_dirty=False)


def test_clean_tree_allow_dirty_bypasses(temp_git_repo):
    claude_skill = temp_git_repo / ".claude" / "skills" / "signoff"
    claude_skill.mkdir(parents=True)
    (claude_skill / "SKILL.md").write_text("# initial skill", encoding="utf-8")
    subprocess.run(["git", "add", ".claude/skills/signoff"], cwd=temp_git_repo, check=True)
    subprocess.run(["git", "commit", "-m", "Commit skill"], cwd=temp_git_repo, check=True)
    (claude_skill / "SKILL.md").write_text("# dirty modified skill", encoding="utf-8")

    # Bypassed via allow_dirty=True
    init.ensure_clean_working_tree(temp_git_repo, allow_dirty=True)


# 4. Normalization, Signatures & Return Types
def test_normalize_skill_destinations(tmp_path):
    repo = tmp_path / "repo"
    claude = repo / ".claude" / "skills" / "signoff"
    agents = repo / ".agents" / "skills" / "signoff"

    # Default None -> [claude]
    assert init._normalize_skill_destinations(repo) == [claude]
    assert init._normalize_skill_destinations(repo, destinations=None) == [claude]

    # Valid candidates deduplicated and sorted in canonical order
    assert init._normalize_skill_destinations(repo, [agents, claude, agents]) == [claude, agents]

    # Empty list raises ValueError
    with pytest.raises(ValueError, match="cannot be empty"):
        init._normalize_skill_destinations(repo, [])

    # Path outside SKILL_DEST_CANDIDATES raises ValueError
    with pytest.raises(ValueError, match="not a valid candidate"):
        init._normalize_skill_destinations(repo, [repo / ".custom" / "skills"])


def test_vendor_skill_callable_compatibility_and_return(temp_git_repo):
    # Calling vendor_skill without keywords succeeds and returns Path
    ret = init.vendor_skill(temp_git_repo, source=SKILL_SRC)
    assert isinstance(ret, Path)
    assert ret == temp_git_repo / ".claude" / "skills" / "signoff"
    assert (ret / "SKILL.md").is_file()

    # Multi-target returns dests[0] as Path
    agents = temp_git_repo / ".agents" / "skills" / "signoff"
    ret_multi = init.vendor_skill(temp_git_repo, source=SKILL_SRC, destinations=[agents, ret])
    assert isinstance(ret_multi, Path)
    assert ret_multi == ret
    assert (agents / "SKILL.md").is_file()


def test_init_result_destinations_dataclass():
    # 4 positional arguments map 4th arg to pr_url and defaults destinations to []
    res = init.InitResult(True, "branch-1", init.RulesetResult("created"), "https://pr.url")
    assert res.pr_url == "https://pr.url"
    assert res.destinations == []


def test_parse_args_skill_target_flag():
    args = init.parse_args(["--skill-target", "agents"])
    assert args.skill_target == "agents"
    args_def = init.parse_args([])
    assert args_def.skill_target == "auto"


# 5. Multi-Destination Vendoring, Staging Force-Add & Rollback
def test_multi_target_vendoring_single_clone(temp_git_repo):
    claude = temp_git_repo / ".claude" / "skills" / "signoff"
    agents = temp_git_repo / ".agents" / "skills" / "signoff"
    init.vendor_skill(temp_git_repo, source=SKILL_SRC, destinations=[claude, agents])

    assert (claude / "SKILL.md").is_file()
    assert (agents / "SKILL.md").is_file()
    claude_stamp = (claude / init.VENDOR_STAMP_FILENAME).read_text(encoding="utf-8")
    agents_stamp = (agents / init.VENDOR_STAMP_FILENAME).read_text(encoding="utf-8")
    assert claude_stamp == agents_stamp


def test_stage_signoff_files_force_adds_ignored_payload(temp_git_repo):
    gitignore = temp_git_repo / ".gitignore"
    gitignore.write_text("*.jsonl\n", encoding="utf-8")
    subprocess.run(["git", "add", ".gitignore"], cwd=temp_git_repo, check=True)
    subprocess.run(["git", "commit", "-m", "ignore jsonl"], cwd=temp_git_repo, check=True)

    claude = temp_git_repo / ".claude" / "skills" / "signoff"
    init.vendor_skill(temp_git_repo, source=SKILL_SRC, destinations=[claude])
    (claude / "payload.jsonl").write_bytes(b'{"test":1}\n')

    init.stage_signoff_files(temp_git_repo, destinations=[claude])

    status = subprocess.check_output(["git", "status", "--porcelain"], cwd=temp_git_repo, text=True)
    assert "A  .claude/skills/signoff/payload.jsonl" in status


def test_rollback_prunes_empty_parents(temp_git_repo):
    claude = temp_git_repo / ".claude" / "skills" / "signoff"
    agents = temp_git_repo / ".agents" / "skills" / "signoff"
    scaffold_paths = [claude, agents]
    preexisting = set()

    claude.mkdir(parents=True)
    (claude / "SKILL.md").write_text("skill", encoding="utf-8")
    agents.mkdir(parents=True)
    (agents / "SKILL.md").write_text("skill", encoding="utf-8")

    init._rollback_scaffold(
        temp_git_repo,
        original_branch="main",
        target_branch="signoff/init",
        scaffold_paths=scaffold_paths,
        preexisting=preexisting,
    )

    assert not (temp_git_repo / ".claude").exists()
    assert not (temp_git_repo / ".agents").exists()


def test_rollback_preserves_nonempty_parents(temp_git_repo):
    claude = temp_git_repo / ".claude" / "skills" / "signoff"
    agents = temp_git_repo / ".agents" / "skills" / "signoff"
    scaffold_paths = [claude, agents]
    preexisting = set()

    claude.mkdir(parents=True)
    (claude / "SKILL.md").write_text("skill", encoding="utf-8")
    agents.mkdir(parents=True)
    (agents / "SKILL.md").write_text("skill", encoding="utf-8")
    # Pre-existing user content in .agents
    (temp_git_repo / ".agents" / "custom.txt").write_text("user content", encoding="utf-8")

    init._rollback_scaffold(
        temp_git_repo,
        original_branch="main",
        target_branch="signoff/init",
        scaffold_paths=scaffold_paths,
        preexisting=preexisting,
    )

    assert not (temp_git_repo / ".claude").exists()
    assert not claude.exists()
    assert not agents.exists()
    assert (temp_git_repo / ".agents" / "custom.txt").exists()


def test_end_to_end_multi_target_greenfield(temp_git_repo):
    result = init.run_init(
        repo_root=temp_git_repo,
        skip_ruleset=True,
        non_interactive=True,
        skill_source=SKILL_SRC,
        skill_target="auto",
    )
    assert result.success is True
    claude = temp_git_repo / ".claude" / "skills" / "signoff"
    agents = temp_git_repo / ".agents" / "skills" / "signoff"
    assert (claude / "SKILL.md").is_file()
    assert (agents / "SKILL.md").is_file()
    assert result.destinations == [claude, agents]


def test_end_to_end_explicit_target(temp_git_repo):
    result = init.run_init(
        repo_root=temp_git_repo,
        skip_ruleset=True,
        non_interactive=True,
        skill_source=SKILL_SRC,
        skill_target="agents",
    )
    assert result.success is True
    claude = temp_git_repo / ".claude" / "skills" / "signoff"
    agents = temp_git_repo / ".agents" / "skills" / "signoff"
    assert not claude.exists()
    assert (agents / "SKILL.md").is_file()
    assert result.destinations == [agents]


def test_allow_dirty_preserves_unrelated_unstaged_work(temp_git_repo):
    unrelated = temp_git_repo / "unrelated.txt"
    unrelated.write_text("committed\n", encoding="utf-8")
    subprocess.run(["git", "add", "unrelated.txt"], cwd=temp_git_repo, check=True)
    subprocess.run(["git", "commit", "-m", "add unrelated file"], cwd=temp_git_repo, check=True)
    unrelated.write_text("user work\n", encoding="utf-8")

    init.run_init(
        repo_root=temp_git_repo,
        skip_ruleset=True,
        non_interactive=True,
        skill_source=SKILL_SRC,
        skill_target="agents",
        allow_dirty=True,
    )

    assert unrelated.read_text(encoding="utf-8") == "user work\n"
    status = subprocess.check_output(["git", "status", "--porcelain"], cwd=temp_git_repo, text=True)
    assert " M unrelated.txt" in status
    committed = subprocess.check_output(["git", "show", "--format=", "--name-only", "HEAD"], cwd=temp_git_repo, text=True)
    assert "unrelated.txt" not in committed.splitlines()


def _dir_snapshot(dir_path: Path) -> dict[str, str | None]:
    import hashlib
    snapshot = {}
    for p in sorted(dir_path.rglob("*")):
        rel = p.relative_to(dir_path).as_posix()
        if p.is_dir():
            snapshot[rel] = None
        elif p.is_file() or p.is_symlink():
            snapshot[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
    return snapshot


def test_rollback_preserves_preexisting_empty_ancestor_dirs_claude_to_agents(temp_git_repo):
    """Empty pre-existing .agents/ or .agents/skills/ is NOT pruned on a claude-only run failure."""
    empty_agents_skills = temp_git_repo / ".agents" / "skills"
    empty_agents_skills.mkdir(parents=True)

    with patch.object(init, "stage_signoff_files", side_effect=RuntimeError("forced post-scaffold failure")):
        with pytest.raises(RuntimeError, match="forced post-scaffold failure"):
            init.run_init(
                repo_root=temp_git_repo,
                skip_ruleset=True,
                non_interactive=True,
                skill_source=SKILL_SRC,
                skill_target="claude",
            )

    assert empty_agents_skills.is_dir()
    assert (temp_git_repo / ".agents").is_dir()
    assert not (temp_git_repo / ".claude").exists()


def test_rollback_preserves_preexisting_empty_ancestor_dirs_agents_to_claude(temp_git_repo):
    """Empty pre-existing .claude/ is NOT pruned on an agents-only run failure."""
    empty_claude_skills = temp_git_repo / ".claude" / "skills"
    empty_claude_skills.mkdir(parents=True)

    with patch.object(init, "stage_signoff_files", side_effect=RuntimeError("forced post-scaffold failure")):
        with pytest.raises(RuntimeError, match="forced post-scaffold failure"):
            init.run_init(
                repo_root=temp_git_repo,
                skip_ruleset=True,
                non_interactive=True,
                skill_source=SKILL_SRC,
                skill_target="agents",
            )

    assert empty_claude_skills.is_dir()
    assert (temp_git_repo / ".claude").is_dir()
    assert not (temp_git_repo / ".agents").exists()


def test_rollback_preexisting_skill_destination_unstamped_install(temp_git_repo):
    """Commit an unstamped install, force failure after vendor_skill(), verify pristine restore including empty dirs."""
    dest = temp_git_repo / ".claude" / "skills" / "signoff"
    shutil.copytree(SKILL_SRC, dest)
    (dest / init.VENDOR_STAMP_FILENAME).unlink(missing_ok=True)
    subprocess.run(["git", "add", ".claude/skills/signoff"], cwd=temp_git_repo, check=True)
    subprocess.run(["git", "commit", "-m", "Commit unstamped skill"], cwd=temp_git_repo, check=True)

    # Add empty nested directory inside dest (invisible to git, but pre-existing on disk)
    nested_empty = dest / "nested" / "local-empty"
    nested_empty.mkdir(parents=True)

    before_snapshot = _dir_snapshot(dest)
    assert "nested/local-empty" in before_snapshot

    with patch.object(init, "stage_signoff_files", side_effect=RuntimeError("forced failure after vendoring")):
        with pytest.raises(RuntimeError, match="forced failure after vendoring"):
            init.run_init(
                repo_root=temp_git_repo,
                skip_ruleset=True,
                non_interactive=True,
                skill_source=SKILL_SRC,
                skill_target="claude",
            )

    after_snapshot = _dir_snapshot(dest)
    assert after_snapshot == before_snapshot
    assert nested_empty.is_dir()
    status = subprocess.check_output(
        ["git", "status", "--porcelain", "--ignored", "--untracked-files=all", "--", ".claude/skills/signoff"],
        cwd=temp_git_repo,
        text=True,
    )
    assert status.strip() == ""


def test_rollback_preexisting_skill_destination_ignored_files(temp_git_repo, tmp_path):
    """Custom skill source with payload.jsonl, .gitignore with *.jsonl, verify rollback clears ignored files."""
    custom_src = tmp_path / "custom_skill"
    shutil.copytree(SKILL_SRC, custom_src)
    (custom_src / "payload.jsonl").write_bytes(b'{"key": "value"}\n')

    dest = temp_git_repo / ".claude" / "skills" / "signoff"
    dest.mkdir(parents=True)
    (dest / "SKILL.md").write_text("# prior install\n", encoding="utf-8")
    gitignore = temp_git_repo / ".gitignore"
    gitignore.write_text("*.jsonl\n", encoding="utf-8")
    subprocess.run(["git", "add", ".claude/skills/signoff", ".gitignore"], cwd=temp_git_repo, check=True)
    subprocess.run(["git", "commit", "-m", "Commit prior install and gitignore"], cwd=temp_git_repo, check=True)

    empty_sub = dest / "empty_dir"
    empty_sub.mkdir()

    before_snapshot = _dir_snapshot(dest)
    assert "empty_dir" in before_snapshot

    with patch.object(init, "stage_signoff_files", side_effect=RuntimeError("forced failure after vendoring")):
        with pytest.raises(RuntimeError, match="forced failure after vendoring"):
            init.run_init(
                repo_root=temp_git_repo,
                skip_ruleset=True,
                non_interactive=True,
                skill_source=custom_src,
                skill_target="claude",
            )

    after_snapshot = _dir_snapshot(dest)
    assert after_snapshot == before_snapshot
    assert empty_sub.is_dir()
    status = subprocess.check_output(
        ["git", "status", "--porcelain", "--ignored", "--untracked-files=all", "--", ".claude/skills/signoff"],
        cwd=temp_git_repo,
        text=True,
    )
    assert status.strip() == ""


def test_normalize_skill_destinations_symlink_cross_candidate(temp_git_repo):
    """With .agents/skills/signoff symlinked to .claude/skills/signoff,
    vendor_skill(destinations=[agents]) must raise the Policy A symlink refusal
    and .claude/skills/signoff must be byte-for-byte untouched."""
    claude = temp_git_repo / ".claude" / "skills" / "signoff"
    claude.mkdir(parents=True)
    (claude / "SKILL.md").write_text("# original claude skill", encoding="utf-8")
    (claude / "extra.txt").write_text("original content", encoding="utf-8")
    claude_snapshot = _dir_snapshot(claude)

    agents = temp_git_repo / ".agents" / "skills" / "signoff"
    agents.parent.mkdir(parents=True, exist_ok=True)
    agents.symlink_to(claude)

    with pytest.raises(RuntimeError, match=r"Destination .agents/skills/signoff is a symbolic link"):
        init.vendor_skill(temp_git_repo, source=SKILL_SRC, destinations=[agents])

    assert _dir_snapshot(claude) == claude_snapshot


def test_vendor_skill_clones_pinned_ref_multi_destination_single_clone(temp_git_repo):
    """Multi-destination vendor_skill executes exactly one git clone call."""
    import shutil as _shutil

    clone_cmds = []
    fake_sha = "e" * 40

    def fake_run(cmd, **kwargs):
        if cmd[:2] == ["git", "clone"]:
            clone_cmds.append(cmd)
            _shutil.copytree(SKILL_SRC, Path(cmd[-1]) / "skills" / "signoff")
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        if cmd[:2] == ["git", "-C"] and "rev-parse" in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout=fake_sha + "\n", stderr="")
        if cmd[:2] == ["git", "check-ignore"]:
            return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="")
        if cmd[:2] == ["git", "ls-files"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        raise AssertionError(f"unexpected subprocess call: {cmd}")

    claude = temp_git_repo / ".claude" / "skills" / "signoff"
    agents = temp_git_repo / ".agents" / "skills" / "signoff"

    with patch.object(init.subprocess, "run", side_effect=fake_run):
        ret = init.vendor_skill(temp_git_repo, destinations=[claude, agents])

    assert ret == claude
    assert len(clone_cmds) == 1
    for dest in (claude, agents):
        stamp = (dest / init.VENDOR_STAMP_FILENAME).read_text(encoding="utf-8")
        assert f"ref: {init.SKILL_SOURCE_REF}" in stamp
        assert f"commit: {fake_sha}" in stamp
        assert f"source: {init.SKILL_SOURCE_REPO}" in stamp


def test_rollback_when_snapshotting_raises_permission_error(temp_git_repo):
    """If preexisting_skill_dirs snapshot raises PermissionError, rollback cleans up setup branch."""
    dest = temp_git_repo / ".claude" / "skills" / "signoff"
    shutil.copytree(SKILL_SRC, dest)
    subprocess.run(["git", "add", ".claude/skills/signoff"], cwd=temp_git_repo, check=True)
    subprocess.run(["git", "commit", "-m", "Commit tracked skill"], cwd=temp_git_repo, check=True)

    # Untracked empty directory inside pre-existing destination
    (dest / "preexisting-empty").mkdir()

    orig_branch = subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=temp_git_repo, text=True).strip()
    before_snapshot = _dir_snapshot(dest)
    assert "preexisting-empty" in before_snapshot

    orig_rglob = Path.rglob

    def guarded_rglob(self, pattern, *args, **kwargs):
        if ".claude" in self.parts and "signoff" in self.parts:
            raise PermissionError("Simulated permission error scanning directory")
        return orig_rglob(self, pattern, *args, **kwargs)

    with patch.object(Path, "rglob", side_effect=guarded_rglob, autospec=True):
        with pytest.raises(PermissionError, match="Simulated permission error scanning directory"):
            init.run_init(
                repo_root=temp_git_repo,
                skip_ruleset=True,
                non_interactive=True,
                skill_source=SKILL_SRC,
                skill_target="claude",
            )

    curr_branch = subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=temp_git_repo, text=True).strip()
    assert curr_branch == orig_branch

    branches = subprocess.check_output(["git", "branch"], cwd=temp_git_repo, text=True)
    assert "signoff/init" not in branches

    status = subprocess.check_output(["git", "status", "--porcelain"], cwd=temp_git_repo, text=True)
    assert status.strip() == ""
    assert _dir_snapshot(dest) == before_snapshot


def test_rollback_returns_and_reports_incomplete_recovery(temp_git_repo, capsys):
    empty_src = temp_git_repo.parent / "not-a-skill-rollback-report"
    empty_src.mkdir()

    with patch.object(init, "_rollback_scaffold", return_value=["sentinel restore failure"]):
        with pytest.raises(RuntimeError, match="does not contain SKILL.md"):
            init.run_init(
                repo_root=temp_git_repo,
                skip_ruleset=True,
                non_interactive=True,
                skill_source=empty_src,
                skill_target="claude",
            )

    err = capsys.readouterr().err
    assert "Rollback incomplete" in err
    assert "sentinel restore failure" in err
    assert "repository restored" not in err


def test_rollback_collects_git_invocation_errors(temp_git_repo):
    subprocess.run(["git", "checkout", "-b", "signoff/init"], cwd=temp_git_repo, check=True)
    original_run = init.subprocess.run

    def fail_restore(cmd, *args, **kwargs):
        if cmd == ["git", "checkout", "main"]:
            raise OSError("simulated git execution failure")
        return original_run(cmd, *args, **kwargs)

    with patch.object(init.subprocess, "run", side_effect=fail_restore):
        failures = init._rollback_scaffold(
            temp_git_repo,
            original_branch="main",
            target_branch="signoff/init",
            scaffold_paths=[temp_git_repo / "README.md"],
            preexisting={temp_git_repo / "README.md"},
            scaffold_started=False,
        )

    assert any("restore branch main: simulated git execution failure" in failure for failure in failures)
    assert any("delete abandoned branch signoff/init" in failure for failure in failures)

    subprocess.run(["git", "checkout", "main"], cwd=temp_git_repo, check=True)
    subprocess.run(["git", "branch", "-D", "signoff/init"], cwd=temp_git_repo, check=True)


def test_allow_dirty_untracked_destination_is_rejected_before_mutation(temp_git_repo):
    """--allow-dirty never admits untracked state under a managed destination."""
    dest = temp_git_repo / ".claude" / "skills" / "signoff"
    dest.mkdir(parents=True)
    (dest / "SKILL.md").write_text("# untracked skill\n", encoding="utf-8")
    (dest / "specs").mkdir()
    (dest / "specs" / "gsa-core.md").write_text("# spec\n", encoding="utf-8")
    (dest / "profiles").mkdir()
    (dest / "profiles" / "custom.md").write_text("# profile\n", encoding="utf-8")

    orig_branch = subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=temp_git_repo, text=True).strip()

    before_snapshot = _dir_snapshot(dest)
    with pytest.raises(RuntimeError, match="Managed scaffold paths contain uncommitted"):
        init.run_init(
            repo_root=temp_git_repo,
            skip_ruleset=True,
            non_interactive=True,
            skill_source=SKILL_SRC,
            skill_target="claude",
            allow_dirty=True,
        )

    curr_branch = subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=temp_git_repo, text=True).strip()
    assert curr_branch == orig_branch

    branches = subprocess.check_output(["git", "branch"], cwd=temp_git_repo, text=True)
    assert "signoff/init" not in branches

    assert _dir_snapshot(dest) == before_snapshot


def test_normalize_skill_destinations_rejects_relative_path(temp_git_repo):
    """_normalize_skill_destinations enforces that destinations are absolute candidate paths rooted at repo_root."""
    rel_path = Path(".claude/skills/signoff")
    with pytest.raises(ValueError, match="is not a valid candidate within"):
        init._normalize_skill_destinations(temp_git_repo, [rel_path])


def test_rollback_pre_scaffold_failure_preserves_destination_and_restores_branch(temp_git_repo):
    """Failure before scaffolding begins (e.g. profile detection) skips scaffold rollback and restores branch."""
    dest = temp_git_repo / ".claude" / "skills" / "signoff"
    shutil.copytree(SKILL_SRC, dest)
    subprocess.run(["git", "add", ".claude/skills/signoff"], cwd=temp_git_repo, check=True)
    subprocess.run(["git", "commit", "-m", "Commit tracked skill"], cwd=temp_git_repo, check=True)

    # Add untracked empty subdirectory
    (dest / "nested-empty").mkdir()

    orig_branch = subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=temp_git_repo, text=True).strip()
    before_snapshot = _dir_snapshot(dest)
    assert "nested-empty" in before_snapshot

    with patch.object(init, "detect_recommended_profile", side_effect=RuntimeError("sentinel profile error")):
        with pytest.raises(RuntimeError, match="sentinel profile error"):
            init.run_init(
                repo_root=temp_git_repo,
                skip_ruleset=True,
                non_interactive=True,
                skill_source=SKILL_SRC,
                skill_target="claude",
            )

    curr_branch = subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=temp_git_repo, text=True).strip()
    assert curr_branch == orig_branch

    branches = subprocess.check_output(["git", "branch"], cwd=temp_git_repo, text=True)
    assert "signoff/init" not in branches

    # Destination snapshot, including untracked empty directory, is completely unchanged
    assert _dir_snapshot(dest) == before_snapshot

    # No scaffold files or directories created
    assert not (temp_git_repo / ".github" / "workflows" / "signoff.yml").exists()
    assert not (temp_git_repo / ".signoff" / "profile.md").exists()

    # Scoped and repository-wide git status are clean
    status_scoped = subprocess.check_output(
        ["git", "status", "--porcelain", "--ignored", "--untracked-files=all", "--", ".claude/skills/signoff"],
        cwd=temp_git_repo,
        text=True,
    )
    assert status_scoped.strip() == ""

    status_repo = subprocess.check_output(["git", "status", "--porcelain"], cwd=temp_git_repo, text=True)
    assert status_repo.strip() == ""

# 6. Single-destination auto-detection hint
def test_single_destination_hint_auto_claude_only(tmp_path):
    claude = tmp_path / ".claude" / "skills" / "signoff"
    hint = init.single_destination_hint(tmp_path, [claude], "auto")
    assert hint is not None
    assert ".claude/skills/signoff" in hint
    assert ".agents/skills/signoff" in hint
    assert "--skill-target agents" in hint


def test_single_destination_hint_auto_agents_only(tmp_path):
    agents = tmp_path / ".agents" / "skills" / "signoff"
    hint = init.single_destination_hint(tmp_path, [agents], "auto")
    assert hint is not None
    assert "--skill-target claude" in hint


def test_single_destination_hint_silent_when_both_or_explicit(tmp_path):
    claude = tmp_path / ".claude" / "skills" / "signoff"
    agents = tmp_path / ".agents" / "skills" / "signoff"
    assert init.single_destination_hint(tmp_path, [claude, agents], "auto") is None
    # An explicit choice is the user's decision; no hint second-guesses it.
    assert init.single_destination_hint(tmp_path, [claude], "claude") is None
    assert init.single_destination_hint(tmp_path, [agents], "agents") is None


# --- Greenfield Onboarding & Policy A Hardening Tests ---

def test_unborn_repo_auto_commit(tmp_path):
    repo_dir = tmp_path / "unborn_auto_commit"
    repo_dir.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Configured Author"], cwd=repo_dir, check=True)
    subprocess.run(["git", "config", "user.email", "author@example.com"], cwd=repo_dir, check=True)
    subprocess.run(["git", "remote", "add", "origin", "https://github.com/example-org/unborn-test.git"], cwd=repo_dir, check=True)

    res = init.run_init(
        repo_root=repo_dir,
        non_interactive=True,
        skill_source=SKILL_SRC,
        skip_ruleset=True,
    )
    assert res.success is True
    assert res.branch == "signoff/init"

    # Main branch should now have the initial empty commit with configured author preserved
    main_commits = subprocess.check_output(["git", "log", "main", "--oneline"], cwd=repo_dir, text=True).splitlines()
    assert len(main_commits) == 1
    assert "chore: initialize main" in main_commits[0]
    main_author = subprocess.check_output(["git", "log", "main", "-1", "--format=%an <%ae>"], cwd=repo_dir, text=True).strip()
    assert main_author == "Configured Author <author@example.com>"

    # signoff/init should have 2 commits: initial commit + scaffold commit with configured author
    branch_commits = subprocess.check_output(["git", "log", "signoff/init", "--oneline"], cwd=repo_dir, text=True).splitlines()
    assert len(branch_commits) == 2
    assert "chore: scaffold git signoff attestation" in branch_commits[0]
    branch_author = subprocess.check_output(["git", "log", "signoff/init", "-1", "--format=%an <%ae>"], cwd=repo_dir, text=True).strip()
    assert branch_author == "Configured Author <author@example.com>"


def test_unborn_repo_fallback_to_signoff_bot_when_identity_unset(tmp_path, monkeypatch):
    repo_dir = tmp_path / "unborn_unset_identity"
    repo_dir.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(["git", "remote", "add", "origin", "https://github.com/example-org/unborn-fallback.git"], cwd=repo_dir, check=True)

    # Clean git identity env to simulate unconfigured container/CI
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/dev/null")
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.delenv("GIT_AUTHOR_NAME", raising=False)
    monkeypatch.delenv("GIT_AUTHOR_EMAIL", raising=False)
    monkeypatch.delenv("GIT_COMMITTER_NAME", raising=False)
    monkeypatch.delenv("GIT_COMMITTER_EMAIL", raising=False)

    res = init.run_init(
        repo_root=repo_dir,
        non_interactive=True,
        skill_source=SKILL_SRC,
        skip_ruleset=True,
    )
    assert res.success is True

    main_author = subprocess.check_output(["git", "log", "main", "-1", "--format=%an <%ae>"], cwd=repo_dir, text=True).strip()
    assert main_author == "Signoff Bot <signoff@example.com>"

    branch_author = subprocess.check_output(["git", "log", "signoff/init", "-1", "--format=%an <%ae>"], cwd=repo_dir, text=True).strip()
    assert branch_author == "Signoff Bot <signoff@example.com>"


@pytest.mark.parametrize("allow_dirty", [False, True])
def test_unborn_repo_with_staged_changes_fails(tmp_path, allow_dirty):
    repo_dir = tmp_path / f"unborn_staged_{allow_dirty}"
    repo_dir.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo_dir, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_dir, check=True)
    (repo_dir / "unreviewed.txt").write_text("unreviewed")
    subprocess.run(["git", "add", "unreviewed.txt"], cwd=repo_dir, check=True)

    with pytest.raises(RuntimeError, match="staged changes"):
        init.run_init(
            repo_root=repo_dir,
            non_interactive=True,
            skill_source=SKILL_SRC,
            skip_ruleset=True,
            allow_dirty=allow_dirty,
        )


def test_unborn_repo_rollback_on_failure(tmp_path):
    repo_dir = tmp_path / "unborn_rollback"
    repo_dir.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo_dir, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_dir, check=True)
    bad_skill_src = tmp_path / "nonexistent_skills_dir"

    with pytest.raises(RuntimeError):
        init.run_init(
            repo_root=repo_dir,
            non_interactive=True,
            skill_source=bad_skill_src,
            skip_ruleset=True,
        )

    # Branch signoff/init should be cleaned up
    branches = subprocess.check_output(["git", "branch", "--list"], cwd=repo_dir, text=True)
    assert "signoff/init" not in branches

    # HEAD should be on main at the empty initial commit
    head_branch = subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_dir, text=True).strip()
    assert head_branch == "main"
    commits = subprocess.check_output(["git", "log", "main", "--oneline"], cwd=repo_dir, text=True).splitlines()
    assert len(commits) == 1
    assert "chore: initialize main" in commits[0]


@pytest.mark.parametrize("benign_name", [".DS_Store", "Thumbs.db", "desktop.ini"])
def test_policy_a_ignores_benign_metadata(temp_git_repo, benign_name):
    dest = temp_git_repo / ".claude" / "skills" / "signoff"
    dest.mkdir(parents=True, exist_ok=True)
    (dest / benign_name).write_bytes(b"\x00\x00\x00\x01")
    (temp_git_repo / ".gitignore").write_text(f"{benign_name}\n")
    subprocess.run(["git", "add", ".gitignore"], cwd=temp_git_repo, check=True)
    subprocess.run(["git", "commit", "-m", f"ignore {benign_name}"], cwd=temp_git_repo, check=True)

    # Should not raise Policy A error
    init.validate_policy_a(dest, temp_git_repo, allow_dirty=False)


def test_policy_a_benign_metadata_with_real_ignored_file_fails(temp_git_repo):
    dest = temp_git_repo / ".claude" / "skills" / "signoff"
    dest.mkdir(parents=True, exist_ok=True)
    (dest / ".DS_Store").write_bytes(b"\x00\x00\x00\x01")
    (dest / "secret.key").write_text("secret")
    (temp_git_repo / ".gitignore").write_text(".DS_Store\n*.key\n")
    subprocess.run(["git", "add", ".gitignore"], cwd=temp_git_repo, check=True)
    subprocess.run(["git", "commit", "-m", "ignore files"], cwd=temp_git_repo, check=True)

    with pytest.raises(RuntimeError) as exc_info:
        init.validate_policy_a(dest, temp_git_repo, allow_dirty=False)
    err = str(exc_info.value)
    assert 'rm -f ".claude/skills/signoff/secret.key"' in err
    assert ".DS_Store" not in err


def test_policy_a_diagnostic_exact_path(temp_git_repo):
    dest = temp_git_repo / ".claude" / "skills" / "signoff"
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "ignored_file.log").write_text("log content")
    (temp_git_repo / ".gitignore").write_text("*.log\n")
    subprocess.run(["git", "add", ".gitignore"], cwd=temp_git_repo, check=True)
    subprocess.run(["git", "commit", "-m", "ignore logs"], cwd=temp_git_repo, check=True)

    with pytest.raises(RuntimeError) as exc_info:
        init.validate_policy_a(dest, temp_git_repo, allow_dirty=False)
    err = str(exc_info.value)
    assert 'rm -f ".claude/skills/signoff/ignored_file.log"' in err
    assert "--allow-dirty" not in err


@pytest.mark.parametrize("marker", [".gemini", ".codex", ".opencode"])
def test_tier2_markers_gemini_codex_opencode(tmp_path, marker):
    repo = tmp_path / f"repo_{marker.strip('.')}"
    repo.mkdir()
    (repo / marker).mkdir()
    dest = init.detect_skill_destinations(repo)
    assert dest == [repo / ".agents" / "skills" / "signoff"]


def test_tier2_marker_gemini_md(tmp_path):
    repo = tmp_path / "repo_gemini_md"
    repo.mkdir()
    (repo / "GEMINI.md").write_text("# Gemini Guide\n")
    dest = init.detect_skill_destinations(repo)
    assert dest == [repo / ".agents" / "skills" / "signoff"]


def test_no_remote_next_steps(tmp_path, monkeypatch, capsys):
    repo_dir = tmp_path / "local_only"
    repo_dir.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo_dir, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_dir, check=True)
    (repo_dir / "README.md").write_text("# Local\n")
    subprocess.run(["git", "add", "README.md"], cwd=repo_dir, check=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=repo_dir, check=True)

    monkeypatch.chdir(repo_dir)
    with patch.object(sys, "argv", ["init.py", "--non-interactive", "--skill-source", str(SKILL_SRC), "--skip-ruleset"]):
        init.main()

    out = capsys.readouterr().out
    assert "git remote add origin" in out


def test_with_remote_next_steps(tmp_path, monkeypatch, capsys):
    repo_dir = tmp_path / "with_remote"
    repo_dir.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo_dir, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_dir, check=True)
    subprocess.run(["git", "remote", "add", "origin", "https://github.com/example-org/with-remote.git"], cwd=repo_dir, check=True)
    (repo_dir / "README.md").write_text("# Remote\n")
    subprocess.run(["git", "add", "README.md"], cwd=repo_dir, check=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=repo_dir, check=True)

    monkeypatch.chdir(repo_dir)
    with patch.object(sys, "argv", ["init.py", "--non-interactive", "--skill-source", str(SKILL_SRC), "--skip-ruleset"]):
        init.main()

    out = capsys.readouterr().out
    assert "git push -u origin signoff/init" in out
    assert "git remote add origin" not in out


