"""Zero-touch repository initializer for /signoff (Git Signoff Attestation).

Scaffolds CI workflows, domain interview profiles, the vendored /signoff
skill, README badges, and GitHub ruleset enforcement.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
import webbrowser
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

SKILL_DEST_CANDIDATES: tuple[str, ...] = (
    ".claude/skills/signoff",
    ".agents/skills/signoff",
)

PROFILES: dict[str, str] = {
    "domain-science": """<!-- INTERVIEW-PROFILE:BEGIN (sole customization point — replace only this block) -->
### Interview Profile: domain-science
Profile-ID: domain-science

Domain emphases — weight probes within the universal axes; never remove axes
or lower pass criteria:
- **Unit & dimensional validity:** units, coordinate conventions, and
  physical-constant provenance for every computed quantity the diff touches
  (e.g. hPa vs. Pa, mixing ratio vs. specific humidity, model-level vs.
  pressure-level coordinates).
- **Surrogate vs. ground truth:** where approximations knowingly violate
  exact domain laws (e.g. an ML parameterization that leaks energy or
  moisture); the parameter regimes where the surrogate is valid and what
  detects drift outside them.
- **Numerical stability:** conditioning of the chosen formulation,
  catastrophic cancellation, tolerance and convergence-criterion choices,
  and the regimes (e.g. CFL-limited timesteps, near-saturation moist
  thermodynamics) where the algorithm degrades before it visibly fails.
- **Statistical validity:** sampling assumptions, leakage between
  train/validation/test splits (e.g. temporally or spatially overlapping
  reanalysis periods), and multiple-comparison risks behind any reported
  improvement.
- **Uncertainty quantification:** how uncertainty is estimated and
  propagated into every reported quantity; which error sources the reported
  intervals (e.g. ensemble spread) include and which they silently exclude.
- **Reproducibility:** seeds, environment pinning, and data provenance
  required to regenerate the results the diff claims.
<!-- INTERVIEW-PROFILE:END -->
""",
    "software-general": """<!-- INTERVIEW-PROFILE:BEGIN (sole customization point — replace only this block) -->
### Interview Profile: software-general
Profile-ID: software-general

Domain emphases — weight probes within the universal axes; never remove axes
or lower pass criteria:
- **Efficiency:** algorithmic complexity and hot-path cost of the chosen
  design; what input scale breaks the current approach.
- **Data structures:** invariants of the chosen structures, which operations
  can corrupt them, and why this representation over alternatives.
- **API contracts:** caller-visible behavior changes, error contracts, and
  backward compatibility of interfaces the diff touches.
<!-- INTERVIEW-PROFILE:END -->
""",
}

WORKFLOW_TEMPLATE = """name: attested by humans

on:
  pull_request:
  push:
    branches: [ {default_branch} ]

jobs:
  verify-signoff:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0   # full history — attestations live in it
      - uses: jerrylin96/signoff/verify@verify-v1.2
"""

RULESET_PAYLOAD = {
    "name": "Signoff Enforcement",
    "target": "branch",
    "enforcement": "active",
    "conditions": {
        "ref_name": {
            "exclude": [],
            "include": [
                "~DEFAULT_BRANCH",
            ],
        },
    },
    "rules": [
        {"type": "deletion"},
        {"type": "non_fast_forward"},
        {
            "type": "pull_request",
            "parameters": {
                "required_approving_review_count": 0,
                "dismiss_stale_reviews_on_push": False,
                "required_reviewers": [],
                "require_code_owner_review": False,
                "require_last_push_approval": False,
                "required_review_thread_resolution": False,
                "allowed_merge_methods": ["merge", "squash", "rebase"],
            },
        },
        {
            "type": "required_status_checks",
            "parameters": {
                "strict_required_status_checks_policy": True,
                "do_not_enforce_on_create": False,
                "required_status_checks": [
                    {
                        "context": "verify-signoff",
                        "integration_id": 15368,
                    },
                ],
            },
        },
    ],
    "bypass_actors": [],
}


@dataclass
class GitContext:
    root: Path
    default_branch: str
    slug: Optional[str] = None
    current_branch: Optional[str] = None
    is_unborn: bool = False


@dataclass
class RulesetResult:
    status: str
    rules_url: Optional[str] = None


@dataclass
class InitResult:
    success: bool
    branch: str
    ruleset: RulesetResult
    pr_url: Optional[str] = None
    destinations: list[Path] = field(default_factory=list)


def is_valid_slug(slug: str) -> bool:
    if not slug:
        return False
    if ".." in slug:
        return False
    return bool(re.match(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", slug))


def parse_github_slug(url: str) -> Optional[str]:
    if not url:
        return None
    url = url.strip()
    
    # HTTPS patterns: https://github.com/owner/repo(.git) or https://token@github.com/owner/repo
    m = re.match(r"^https?://(?:[^@]+@)?github\.com/([^/]+)/([^/]+?)(?:\.git)?/?$", url)
    if m:
        slug = f"{m.group(1)}/{m.group(2)}"
        return slug if is_valid_slug(slug) else None
        
    # SSH patterns: git@github.com:owner/repo(.git) or ssh://git@github.com(:port)?/owner/repo(.git)
    m = re.match(r"^(?:ssh://)?git@github\.com(?::\d+)?(?:/|:)([^/]+)/([^/]+?)(?:\.git)?/?$", url)
    if m:
        slug = f"{m.group(1)}/{m.group(2)}"
        return slug if is_valid_slug(slug) else None

    return None


def detect_git_context(start_dir: Optional[Path] = None) -> GitContext:
    target_dir = Path(start_dir or Path.cwd()).resolve()
    
    # 1. Resolve Git Root
    proc = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=target_dir,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"Not a git repository: {target_dir}")
    root = Path(proc.stdout.strip()).resolve()

    # 2. Check Unborn HEAD
    is_unborn = False
    proc = subprocess.run(["git", "rev-parse", "--verify", "HEAD"], cwd=root, capture_output=True, text=True)
    if proc.returncode != 0:
        is_unborn = True

    # 3. Current Branch
    current_branch = None
    b_proc = subprocess.run(["git", "branch", "--show-current"], cwd=root, capture_output=True, text=True)
    if b_proc.returncode == 0 and b_proc.stdout.strip():
        current_branch = b_proc.stdout.strip()

    # 4. Default Branch Detection
    default_branch = "main"
    origin_head_proc = subprocess.run(
        ["git", "symbolic-ref", "--short", "refs/remotes/origin/HEAD"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    if origin_head_proc.returncode == 0 and "/" in origin_head_proc.stdout.strip():
        default_branch = origin_head_proc.stdout.strip().split("/", 1)[1]
    else:
        found_candidate = False
        candidates = (
            "main", "master", "trunk", "dev", "develop", "development",
            "staging", "release", "production",
        )
        for candidate in candidates:
            check_local = subprocess.run(["git", "show-ref", "--verify", f"refs/heads/{candidate}"], cwd=root, capture_output=True)
            check_remote = subprocess.run(["git", "show-ref", "--verify", f"refs/remotes/origin/{candidate}"], cwd=root, capture_output=True)
            if check_local.returncode == 0 or check_remote.returncode == 0:
                default_branch = candidate
                found_candidate = True
                break
        if not found_candidate:
            default_branch = current_branch or "main"

    # 5. Remote Slug
    slug = None
    remote_proc = subprocess.run(["git", "remote", "get-url", "origin"], cwd=root, capture_output=True, text=True)
    if remote_proc.returncode == 0:
        slug = parse_github_slug(remote_proc.stdout.strip())

    return GitContext(
        root=root,
        default_branch=default_branch,
        slug=slug,
        current_branch=current_branch,
        is_unborn=is_unborn,
    )


def detect_recommended_profile(repo_root: Path) -> str:
    science_keywords = {
        "torch", "numpy", "scipy", "xarray", "netcdf4", "jupyter", "cbottle",
        "astropy", "jax", "pandas", "polars", "matplotlib", "seaborn",
        "scikit-learn", "sklearn", "tensorflow", "keras", "earth2studio",
    }
    
    # Check manifests
    for manifest_name in ("pyproject.toml", "requirements.txt", "environment.yml", "setup.py", "Pipfile"):
        manifest = repo_root / manifest_name
        if manifest.is_file():
            try:
                content = manifest.read_text(encoding="utf-8", errors="ignore").lower()
                if any(kw in content for kw in science_keywords):
                    return "domain-science"
            except OSError:
                pass

    # Check for Jupyter Notebooks
    if list(repo_root.glob("*.ipynb")) or list((repo_root / "notebooks").glob("*.ipynb") if (repo_root / "notebooks").is_dir() else []):
        return "domain-science"

    return "software-general"


def scaffold_workflow(repo_root: Path, default_branch: str = "main") -> Path:
    wf_dir = repo_root / ".github" / "workflows"
    wf_dir.mkdir(parents=True, exist_ok=True)
    wf_file = wf_dir / "signoff.yml"
    wf_file.write_text(WORKFLOW_TEMPLATE.format(default_branch=default_branch), encoding="utf-8")
    return wf_file


def scaffold_profile(repo_root: Path, profile_id: str = "domain-science") -> Path:
    profile_dir = repo_root / ".signoff"
    profile_dir.mkdir(parents=True, exist_ok=True)
    profile_file = profile_dir / "profile.md"
    content = PROFILES.get(profile_id, PROFILES["software-general"])
    profile_file.write_text(content, encoding="utf-8")
    return profile_file


SKILL_SOURCE_REPO = "https://github.com/jerrylin96/signoff"
# Pin tag the default vendor clone fetches — the same tag the install
# snippets serve this script from, so the vendored payload matches the
# script version instead of silently tracking the default branch. Pin tags
# never move; bump this together with the install snippets (README,
# verify/README.md, site/index.html) and tag.yml's PINS list.
SKILL_SOURCE_REF = "init-v4"
VENDOR_STAMP_FILENAME = "VENDORED-FROM"


def _git_head_commit(git_dir: Path) -> str:
    proc = subprocess.run(
        ["git", "-C", str(git_dir), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
    )
    return proc.stdout.strip() if proc.returncode == 0 else "unknown"


def _existing_skill_installs(repo_root: Path) -> list[Path]:
    """Return existing skill directories containing SKILL.md (following symlinks)."""
    return [
        repo_root / rel
        for rel in SKILL_DEST_CANDIDATES
        if (repo_root / rel / "SKILL.md").is_file()
    ]


def detect_skill_destinations(repo_root: Path) -> list[Path] | None:
    """Detect destination paths based on existing installations or repository signals.
    Returns None if the repository has no unambiguous signals (Tier 3).
    """
    claude_dest = repo_root / ".claude" / "skills" / "signoff"
    agents_dest = repo_root / ".agents" / "skills" / "signoff"

    # Tier 1: Existing Installation Detection
    existing = _existing_skill_installs(repo_root)
    if existing:
        return existing

    # Tier 2: Filesystem Signal Detection
    has_claude = (repo_root / ".claude").is_dir() or (repo_root / "CLAUDE.md").is_file()
    has_agents = (
        (repo_root / ".agents").is_dir()
        or (repo_root / ".cursor").is_dir()
        or (repo_root / "AGENTS.md").is_file()
        or (repo_root / "GEMINI.md").is_file()
    )

    if has_claude and not has_agents:
        return [claude_dest]
    if has_agents and not has_claude:
        return [agents_dest]
    if has_claude and has_agents:
        return [claude_dest, agents_dest]

    # Tier 3: Greenfield / No Signals
    return None


def resolve_skill_destinations(
    repo_root: Path,
    skill_target: str = "auto",
    non_interactive: bool = False,
) -> list[Path]:
    allowed_targets = {"auto", "claude", "agents", "both"}
    if skill_target not in allowed_targets:
        raise ValueError(f"Invalid skill_target '{skill_target}'; must be one of {allowed_targets}")

    claude_dest = repo_root / ".claude" / "skills" / "signoff"
    agents_dest = repo_root / ".agents" / "skills" / "signoff"

    explicit_dests: list[Path] | None = None
    if skill_target == "claude":
        explicit_dests = [claude_dest]
    elif skill_target == "agents":
        explicit_dests = [agents_dest]
    elif skill_target == "both":
        explicit_dests = [claude_dest, agents_dest]

    existing = _existing_skill_installs(repo_root)

    # Expansion Guarantee: Union explicit targets with any existing installations.
    # Running `--skill-target agents` on a `.claude` install re-vendors `.claude`
    # to the new release pin while adding `.agents`, preventing version drift.
    if explicit_dests is not None:
        union_set = set(explicit_dests) | set(existing)
        return [repo_root / rel for rel in SKILL_DEST_CANDIDATES if (repo_root / rel) in union_set]

    # skill_target == "auto"
    detected = detect_skill_destinations(repo_root)
    if detected is not None:
        return detected

    # Tier 3 Greenfield (no signals detected)
    if non_interactive:
        return [claude_dest, agents_dest]

    print("\nNo existing agent configuration detected.")
    print("Which harness(es) should /signoff be installed for?")
    print("  1) Both Claude Code and open-standard agents (Antigravity, Codex, Cursor) [recommended]")
    print("  2) Claude Code only (.claude/skills/signoff)")
    print("  3) Open-standard agents only (.agents/skills/signoff)")
    choice = prompt_user("Select [1-3]", default="1", non_interactive=non_interactive)
    if choice == "2":
        return [claude_dest]
    if choice == "3":
        return [agents_dest]
    return [claude_dest, agents_dest]


def _normalize_skill_destinations(
    repo_root: Path,
    destinations: Optional[list[Path]] = None,
) -> list[Path]:
    if destinations is None:
        return [repo_root / ".claude" / "skills" / "signoff"]
    if not destinations:
        raise ValueError("destinations list cannot be empty")

    norm_set: set[str] = set()
    for d in destinations:
        matched_rel = None
        d_path = Path(d)
        for rel in SKILL_DEST_CANDIDATES:
            cand_path = repo_root / rel
            if d_path == cand_path or d_path.as_posix() == cand_path.as_posix():
                matched_rel = rel
                break
            try:
                if d_path.relative_to(repo_root).as_posix() == rel:
                    matched_rel = rel
                    break
            except ValueError:
                pass
        if matched_rel is None:
            raise ValueError(f"Destination {d} is not a valid candidate within {SKILL_DEST_CANDIDATES}")
        norm_set.add(matched_rel)

    return [repo_root / rel for rel in SKILL_DEST_CANDIDATES if rel in norm_set]


def validate_policy_a(dest: Path, repo_root: Path, *, allow_dirty: bool = False) -> None:
    """Validate destination and all parent path components under repo_root."""
    rel = dest.relative_to(repo_root)

    # 1. Check parent path components and dest for symlinks and ordinary-file collisions
    curr = dest
    components = []
    while curr != repo_root and curr != curr.parent:
        components.append(curr)
        curr = curr.parent

    for part in reversed(components):
        part_rel = part.relative_to(repo_root)
        if part.is_symlink():
            raise RuntimeError(
                f"Destination {part_rel} is a symbolic link. "
                "The signoff initializer vendors real directory copies and "
                "does not replace symlink-managed skill installations. "
                "Remove the symlink or commit a real copy, then re-run."
            )
        if part != dest and part.is_file():
            raise RuntimeError(
                f"Parent path {part_rel} exists as an ordinary file. "
                "Remove the file, then re-run."
            )

    # 2. Check if destination itself is git-ignored (intent-level check)
    proc = subprocess.run(
        ["git", "check-ignore", "--no-index", "-q", "--", str(rel)],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    if proc.returncode == 0:
        raise RuntimeError(
            f"Destination {rel} is ignored by git (.gitignore). "
            "Remove the ignore pattern before running init."
        )
    elif proc.returncode != 1:
        raise RuntimeError(f"git check-ignore failed with exit code {proc.returncode}: {proc.stderr.strip()}")

    # 3. Check for pre-existing ignored untracked files inside destination
    if not allow_dirty and dest.is_dir():
        proc_ls = subprocess.run(
            ["git", "ls-files", "-z", "--others", "--ignored", "--exclude-standard", "--", str(rel)],
            cwd=repo_root,
            capture_output=True,
            text=True,
        )
        if proc_ls.returncode != 0:
            raise RuntimeError(f"git ls-files failed with exit code {proc_ls.returncode}: {proc_ls.stderr.strip()}")
        if proc_ls.stdout:
            ignored_files = [f for f in proc_ls.stdout.split("\0") if f]
            if ignored_files:
                raise RuntimeError(
                    f"Destination {rel} contains ignored untracked files: {', '.join(ignored_files)}. "
                    "Remove them or use --allow-dirty to override."
                )

    # 4. Check for ordinary file conflict at destination
    if dest.is_file():
        raise RuntimeError(
            f"Destination {rel} exists as an ordinary file. "
            "Remove the file, then re-run."
        )

    # 5. Check for unrelated non-empty directory
    if dest.is_dir() and not (dest / "SKILL.md").is_file() and any(dest.iterdir()):
        raise RuntimeError(
            f"Destination {rel} is a non-empty directory not recognized as a /signoff skill. "
            "Aborting to prevent data loss."
        )


def vendor_skill(
    repo_root: Path,
    source: Optional[Path] = None,
    *,
    destinations: Optional[list[Path]] = None,
    allow_dirty: bool = False,
) -> Path:
    """Copy the self-contained skills/signoff folder into destination(s).

    Returns the first canonical destination as Path for backward compatibility.
    """
    dests = _normalize_skill_destinations(repo_root, destinations)
    for d in dests:
        validate_policy_a(d, repo_root, allow_dirty=allow_dirty)

    def _copy(src: Path, source_desc: str, ref: str, commit: str) -> Path:
        if not (src / "SKILL.md").is_file():
            raise RuntimeError(f"Skill source {src} does not contain SKILL.md")
        stamp = (
            "Vendored /signoff skill — provenance stamp written by init.py; do not edit.\n"
            f"source: {source_desc}\n"
            f"ref: {ref}\n"
            f"commit: {commit}\n"
        )
        for dest in dests:
            if dest.exists():
                shutil.rmtree(dest)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(src, dest)
            (dest / VENDOR_STAMP_FILENAME).write_text(stamp, encoding="utf-8")
        return dests[0]

    if source is not None:
        src = Path(source)
        return _copy(
            src,
            source_desc=str(src.resolve()),
            ref="local (--skill-source)",
            commit=_git_head_commit(src),
        )

    with tempfile.TemporaryDirectory(prefix="signoff-skill-") as tmp:
        clone_dir = Path(tmp) / "signoff"
        proc = subprocess.run(
            ["git", "clone", "--depth", "1", "--branch", SKILL_SOURCE_REF, SKILL_SOURCE_REPO, str(clone_dir)],
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            raise RuntimeError(
                f"Failed to fetch the signoff skill at pin {SKILL_SOURCE_REF}"
                f" (offline installs: --skill-source <path>): {proc.stderr.strip()}"
            )
        return _copy(
            clone_dir / "skills" / "signoff",
            source_desc=SKILL_SOURCE_REPO,
            ref=SKILL_SOURCE_REF,
            commit=_git_head_commit(clone_dir),
        )



def inject_readme_badge(repo_root: Path, slug: str) -> Path:
    readme = repo_root / "README.md"
    badge_md = f"[![attested by humans](https://github.com/{slug}/actions/workflows/signoff.yml/badge.svg)](https://github.com/{slug}/actions/workflows/signoff.yml)"
    
    if not readme.is_file():
        readme.write_text(f"# {slug.split('/')[-1]}\n\n{badge_md}\n", encoding="utf-8")
        return readme

    raw_bytes = readme.read_bytes()
    try:
        text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError as e:
        raise RuntimeError(f"README.md is not valid UTF-8: {e}")
        
    if "actions/workflows/signoff.yml/badge.svg" in text or "attested by humans" in text:
        return readme  # already present
        
    is_crlf = b"\r\n" in raw_bytes
    newline = "\r\n" if is_crlf else "\n"
    lines = text.splitlines()
    
    h1_idx = None
    in_code_fence = False
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_code_fence = not in_code_fence
            continue
        if not in_code_fence and stripped.startswith("# ") and not stripped.startswith("##"):
            h1_idx = i
            break
            
    if h1_idx is not None:
        lines.insert(h1_idx + 1, "")
        lines.insert(h1_idx + 2, badge_md)
    else:
        lines.insert(0, badge_md)
        lines.insert(1, "")
        
    new_content = newline.join(lines)
    if not new_content.endswith(newline):
        new_content += newline
    readme.write_bytes(new_content.encode("utf-8"))
    return readme


def ensure_clean_working_tree(repo_root: Path, allow_dirty: bool = False):
    if allow_dirty:
        return
    proc = subprocess.run(["git", "status", "--porcelain"], cwd=repo_root, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"git status failed: {proc.stderr.strip()}")
    status = proc.stdout
    if not status.strip():
        return

    signoff_prefixes = (
        ".github/workflows/signoff.yml",
        ".signoff/",
        ".signoff",
        "README.md",
    )
    unrelated_changes = []
    allowlisted_modifications = []
    for raw_line in status.splitlines():
        if not raw_line:
            continue
        path_part = raw_line[3:].strip()
        if path_part.startswith('"') and path_part.endswith('"'):
            path_part = path_part[1:-1]
        if any(path_part == p or path_part.startswith(p.rstrip("/") + "/") for p in signoff_prefixes):
            allowlisted_modifications.append(path_part)
        else:
            unrelated_changes.append(raw_line)

    if unrelated_changes:
        unrelated_str = "\n".join(unrelated_changes)
        raise RuntimeError(f"Working tree has uncommitted changes:\n{unrelated_str}\nUse --allow-dirty to override.")

    if allowlisted_modifications:
        print(f"  ℹ️  Note: Existing modifications to {', '.join(set(allowlisted_modifications))} will be staged.")


def stage_signoff_files(
    repo_root: Path,
    *,
    destinations: Optional[list[Path]] = None,
) -> None:
    dests = _normalize_skill_destinations(repo_root, destinations)
    files = [
        ".github/workflows/signoff.yml",
        ".signoff/profile.md",
        ".signoff/ruleset.json",
        "README.md",
    ]
    for f in files:
        target = repo_root / f
        if target.exists():
            proc = subprocess.run(["git", "add", f], cwd=repo_root, capture_output=True, text=True)
            if proc.returncode != 0:
                raise RuntimeError(f"git add {f} failed: {proc.stderr.strip()}")

    for dest in dests:
        if dest.exists():
            rel = dest.relative_to(repo_root).as_posix()
            proc = subprocess.run(["git", "add", "-f", "--", rel], cwd=repo_root, capture_output=True, text=True)
            if proc.returncode != 0:
                raise RuntimeError(f"git add -f -- {rel} failed: {proc.stderr.strip()}")


def resolve_branch_name(repo_root: Path, desired_branch: str) -> str:
    check_local = subprocess.run(["git", "show-ref", "--verify", f"refs/heads/{desired_branch}"], cwd=repo_root, capture_output=True)
    check_remote = subprocess.run(["git", "show-ref", "--verify", f"refs/remotes/origin/{desired_branch}"], cwd=repo_root, capture_output=True)
    if check_local.returncode != 0 and check_remote.returncode != 0:
        return desired_branch
    timestamp = int(time.time())
    return f"{desired_branch}-{timestamp}"


def setup_ruleset(
    repo_root: Path,
    slug: Optional[str],
    open_browser: bool = False,
    skip_ruleset: bool = False,
) -> RulesetResult:
    if skip_ruleset:
        return RulesetResult(status="skipped")

    ruleset_path = repo_root / ".signoff" / "ruleset.json"
    ruleset_path.parent.mkdir(parents=True, exist_ok=True)
    ruleset_path.write_text(json.dumps(RULESET_PAYLOAD, indent=2) + "\n", encoding="utf-8")

    if not slug or not shutil.which("gh"):
        url = f"https://github.com/{slug}/settings/rules" if slug else "https://github.com"
        if open_browser:
            try:
                webbrowser.open(url)
            except Exception:
                pass
        return RulesetResult(status="fallback_manual", rules_url=url)

    # Check gh auth
    auth_check = subprocess.run(["gh", "auth", "status"], capture_output=True, text=True)
    if auth_check.returncode != 0:
        url = f"https://github.com/{slug}/settings/rules"
        if open_browser:
            try:
                webbrowser.open(url)
            except Exception:
                pass
        return RulesetResult(status="fallback_manual", rules_url=url)

    # Check existing rulesets
    list_check = subprocess.run(["gh", "api", f"repos/{slug}/rulesets"], capture_output=True, text=True)
    if list_check.returncode == 0:
        try:
            existing = json.loads(list_check.stdout)
            for r in existing:
                if r.get("name") == "Signoff Enforcement":
                    return RulesetResult(status="already_exists")
        except Exception:
            pass
    elif "HTTP 403" in list_check.stderr or "Resource not accessible" in list_check.stderr:
        url = f"https://github.com/{slug}/settings/rules"
        if open_browser:
            try:
                webbrowser.open(url)
            except Exception:
                pass
        return RulesetResult(status="fallback_manual", rules_url=url)

    # Create ruleset
    create_check = subprocess.run(
        ["gh", "api", f"repos/{slug}/rulesets", "--method", "POST", "--input", "-"],
        input=json.dumps(RULESET_PAYLOAD),
        capture_output=True,
        text=True,
    )
    if create_check.returncode == 0:
        return RulesetResult(status="created")

    url = f"https://github.com/{slug}/settings/rules"
    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    return RulesetResult(status="fallback_manual", rules_url=url)


def prompt_user(prompt_text: str, default: str = "", non_interactive: bool = False) -> str:
    if non_interactive:
        return default
    if not sys.stdin.isatty():
        try:
            tty_dev = "CON" if sys.platform == "win32" else "/dev/tty"
            with open(tty_dev, "r") as tty:
                sys.stdout.write(f"{prompt_text} [{default}]: ")
                sys.stdout.flush()
                val = tty.readline().strip()
                return val or default
        except OSError:
            return default
    sys.stdout.write(f"{prompt_text} [{default}]: ")
    sys.stdout.flush()
    val = sys.stdin.readline().strip()
    return val or default


def _remove_scaffold_path(path: Path) -> None:
    """Remove a file, directory, or symlink init created. Never follows a
    symlink (so a user-made symlinked destination is unlinked, not cleared
    through)."""
    try:
        if path.is_symlink() or path.is_file():
            path.unlink()
        elif path.is_dir():
            shutil.rmtree(path)
    except OSError:
        pass


def _prune_empty_dir(path: Path) -> None:
    """Remove a directory only if it exists and is empty, so pruning never
    touches a directory that still holds unrelated user content (e.g. a
    pre-existing .github/ with other workflows)."""
    try:
        if path.is_dir() and not any(path.iterdir()):
            path.rmdir()
    except OSError:
        pass


def _rollback_scaffold(
    root: Path,
    original_branch: Optional[str],
    is_unborn: bool,
    target_branch: str,
    scaffold_paths: list[Path],
    preexisting: set[Path],
    preexisting_dirs: Optional[set[Path]] = None,
) -> None:
    """Undo a partial init when a step after branch creation fails.

    Without this, an offline vendor clone (or any post-branch failure) strands
    the repository on the setup branch with half-written, unstaged scaffold
    files. This restores the repository to exactly the state init found it in:
    paths init created are removed, tracked files it overwrote (e.g. the README
    badge) are reverted to HEAD, and the original branch is restored with the
    abandoned setup branch dropped. Local git state only — a GitHub ruleset
    already created via `gh` is idempotent and left in place. Best-effort:
    every step is guarded so rollback never masks the original error.
    """
    # 1. Undo file scaffolding.
    for path in scaffold_paths:
        if path in preexisting:
            rel = path.relative_to(root).as_posix()
            if any(path == root / cand for cand in SKILL_DEST_CANDIDATES):
                # Pre-existing skill destination: completely remove the destination
                # directory so newly written untracked files (e.g. VENDORED-FROM)
                # and newly vendored ignored files are cleared, then restore tracked
                # content from HEAD.
                if path.is_dir():
                    shutil.rmtree(path, ignore_errors=True)
                elif path.is_file() or path.is_symlink():
                    path.unlink(missing_ok=True)
                subprocess.run(["git", "checkout", "HEAD", "--", rel], cwd=root, capture_output=True, text=True)
            else:
                # Ordinary pre-existing files (e.g. README.md)
                subprocess.run(["git", "checkout", "HEAD", "--", rel], cwd=root, capture_output=True, text=True)
        else:
            _remove_scaffold_path(path)
    # 2. Prune directories init may have created, leaving user content intact.
    for directory in (
        root / ".github" / "workflows",
        root / ".github",
        root / ".signoff",
        root / ".agents" / "skills" / "signoff",
        root / ".agents" / "skills",
        root / ".agents",
        root / ".claude" / "skills" / "signoff",
        root / ".claude" / "skills",
        root / ".claude",
    ):
        if preexisting_dirs is None or directory not in preexisting_dirs:
            _prune_empty_dir(directory)
    # 3. Restore the starting branch and drop the abandoned setup branch.
    if is_unborn:
        # No commits exist, so there is no setup-branch ref to delete; just
        # point HEAD back at the original unborn branch.
        if original_branch:
            subprocess.run(["git", "symbolic-ref", "HEAD", f"refs/heads/{original_branch}"], cwd=root, capture_output=True, text=True)
    elif original_branch:
        subprocess.run(["git", "checkout", original_branch], cwd=root, capture_output=True, text=True)
        subprocess.run(["git", "branch", "-D", target_branch], cwd=root, capture_output=True, text=True)
    else:
        # Detached HEAD at start: re-detach at the current commit (the setup
        # branch shares it), then drop the branch name.
        subprocess.run(["git", "checkout", "--detach"], cwd=root, capture_output=True, text=True)
        subprocess.run(["git", "branch", "-D", target_branch], cwd=root, capture_output=True, text=True)


def run_init(
    repo_root: Optional[Path] = None,
    profile_id: Optional[str] = None,
    branch: str = "signoff/init",
    slug: Optional[str] = None,
    skip_ruleset: bool = False,
    skip_badge: bool = False,
    allow_dirty: bool = False,
    non_interactive: bool = False,
    open_browser: bool = False,
    skill_source: Optional[Path] = None,
    skill_target: str = "auto",
) -> InitResult:
    ctx = detect_git_context(repo_root)
    root = ctx.root
    effective_slug = slug or ctx.slug

    # Step 0.1: Clean tree guard
    ensure_clean_working_tree(root, allow_dirty=allow_dirty)

    # Step 0.2: Resolve skill destinations
    resolved_dests = resolve_skill_destinations(
        root,
        skill_target=skill_target,
        non_interactive=non_interactive,
    )

    # Step 0.3: Policy A verification before branch creation
    for dest in resolved_dests:
        validate_policy_a(dest, root, allow_dirty=allow_dirty)

    # Step 0.4: Checkout target branch FIRST before scaffolding any files
    target_branch = resolve_branch_name(root, branch)
    if ctx.is_unborn:
        proc = subprocess.run(["git", "checkout", "--no-track", "-b", target_branch], cwd=root, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(f"Failed to create branch '{target_branch}': {proc.stderr.strip()}")
    else:
        base_ref = ctx.default_branch
        verify_local = subprocess.run(["git", "rev-parse", "--verify", f"{base_ref}^{{commit}}"], cwd=root, capture_output=True, text=True)
        verify_remote = subprocess.run(["git", "rev-parse", "--verify", f"origin/{base_ref}^{{commit}}"], cwd=root, capture_output=True, text=True)
        if verify_local.returncode == 0:
            proc = subprocess.run(["git", "checkout", "--no-track", "-b", target_branch, base_ref], cwd=root, capture_output=True, text=True)
        elif verify_remote.returncode == 0:
            proc = subprocess.run(["git", "checkout", "--no-track", "-b", target_branch, f"origin/{base_ref}"], cwd=root, capture_output=True, text=True)
        else:
            print(f"  ℹ️  Notice: Base branch '{base_ref}' not found locally or on origin; branching '{target_branch}' from HEAD.")
            proc = subprocess.run(["git", "checkout", "--no-track", "-b", target_branch], cwd=root, capture_output=True, text=True)

        if proc.returncode != 0:
            raise RuntimeError(f"Failed to create branch '{target_branch}': {proc.stderr.strip()}")

    # The branch now exists and later steps write files onto it. If any of them
    # fails (most commonly an offline vendor clone), roll the whole thing back
    # so the run is atomic: either a complete setup commit or no trace at all.
    scaffold_paths = [
        root / ".github" / "workflows" / "signoff.yml",
        root / ".signoff" / "profile.md",
        root / ".signoff" / "ruleset.json",
        *resolved_dests,
        root / "README.md",
    ]
    preexisting = {p for p in scaffold_paths if p.exists()}
    ancestor_candidates = [
        root / ".github",
        root / ".github" / "workflows",
        root / ".signoff",
        root / ".claude",
        root / ".claude" / "skills",
        root / ".claude" / "skills" / "signoff",
        root / ".agents",
        root / ".agents" / "skills",
        root / ".agents" / "skills" / "signoff",
    ]
    preexisting_dirs = {d for d in ancestor_candidates if d.is_dir()}
    try:
        # Step 3: Profile selection
        rec_profile = detect_recommended_profile(root)
        effective_profile = profile_id or rec_profile
        print("\n[2/5] 📦 Selecting interview profile...")
        print(f"  Recommended profile: {rec_profile}")
        if not non_interactive and profile_id is None:
            print("  1) domain-science (research, physics, ML, climate, math)")
            print("  2) software-general (classic engineering, APIs, algorithms)")
            choice = prompt_user("Select profile number or name", default=rec_profile, non_interactive=non_interactive)
            if choice in ("1", "domain-science"):
                effective_profile = "domain-science"
            elif choice in ("2", "software-general"):
                effective_profile = "software-general"
        print(f"  Active profile: {effective_profile}")

        # Step 4: Scaffold files
        scaffold_workflow(root, default_branch=ctx.default_branch)
        scaffold_profile(root, profile_id=effective_profile)
        vendor_skill(root, source=skill_source, destinations=resolved_dests, allow_dirty=allow_dirty)
        if effective_slug and not skip_badge:
            inject_readme_badge(root, slug=effective_slug)

        # Step 5: Ruleset setup
        ruleset_res = setup_ruleset(
            root,
            slug=effective_slug,
            open_browser=open_browser,
            skip_ruleset=skip_ruleset,
        )

        # Step 6: Stage and commit
        stage_signoff_files(root, destinations=resolved_dests)
        commit_proc = subprocess.run(
            ["git", "commit", "-m", "chore: scaffold git signoff attestation"],
            cwd=root,
            capture_output=True,
            text=True,
        )
        if commit_proc.returncode != 0:
            raise RuntimeError(f"Git commit failed: {commit_proc.stderr.strip()}")
    except BaseException:
        _rollback_scaffold(
            root,
            ctx.current_branch,
            ctx.is_unborn,
            target_branch,
            scaffold_paths,
            preexisting,
            preexisting_dirs=preexisting_dirs,
        )
        restored = ctx.current_branch or "the previous state"
        print(f"  ↩️  Rolled back partial setup; repository restored to '{restored}'.", file=sys.stderr)
        raise

    pr_url = f"https://github.com/{effective_slug}/compare/{ctx.default_branch}...{target_branch}?expand=1" if effective_slug else None

    return InitResult(
        success=True,
        branch=target_branch,
        ruleset=ruleset_res,
        pr_url=pr_url,
        destinations=resolved_dests,
    )


def parse_args(args: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Zero-touch repository initializer for /signoff.")
    parser.add_argument("--profile", choices=["domain-science", "software-general"], help="Interview profile ID")
    parser.add_argument("--branch", default="signoff/init", help="Feature branch name (default: signoff/init)")
    parser.add_argument("--skip-ruleset", action="store_true", help="Skip GitHub Ruleset creation")
    parser.add_argument("--skip-badge", action="store_true", help="Skip README badge injection")
    parser.add_argument("--allow-dirty", action="store_true", help="Allow running on dirty working tree")
    parser.add_argument("--non-interactive", action="store_true", help="Run without interactive prompts")
    parser.add_argument("--open-browser", action="store_true", help="Open GitHub settings in browser if manual fallback is needed")
    parser.add_argument("--skill-source", type=Path, help="Local skills/signoff folder to vendor (offline installs; default: shallow clone)")
    parser.add_argument("--skill-target", choices=["auto", "claude", "agents", "both"], default="auto", help="Harness destination target (default: auto)")
    return parser.parse_args(args)


def main() -> int:
    args = parse_args(sys.argv[1:])
    print("=" * 60)
    print("🚀 signoff init — Git Signoff Attestation (GSA) Setup")
    print("=" * 60)
    
    try:
        print("\n[1/5] 🔍 Detecting repository context...")
        res = run_init(
            profile_id=args.profile,
            branch=args.branch,
            skip_ruleset=args.skip_ruleset,
            skip_badge=args.skip_badge,
            allow_dirty=args.allow_dirty,
            non_interactive=args.non_interactive,
            open_browser=args.open_browser,
            skill_source=args.skill_source,
            skill_target=args.skill_target,
        )
        print(f"\n[3/5] 🌿 Created feature branch '{res.branch}' with scaffold commit.")
        root_dir = Path.cwd()
        try:
            root_dir = detect_git_context().root
        except Exception:
            pass
        dests_str = ", ".join(str(d.relative_to(root_dir)) for d in res.destinations) or ".claude/skills/signoff"
        print(f"[4/5] 📝 Scaffolded workflow, profile, and vendored the /signoff skill into {dests_str}.")
        
        # Surfacing ruleset status
        if res.ruleset.status == "created":
            print("[5/5] 🛡️  Created GitHub ruleset 'Signoff Enforcement' via gh CLI.")
        elif res.ruleset.status == "already_exists":
            print("[5/5] 🛡️  GitHub ruleset 'Signoff Enforcement' already configured.")
        elif res.ruleset.status == "skipped":
            print("[5/5] 🛡️  GitHub ruleset setup skipped.")
        elif res.ruleset.status == "fallback_manual":
            print(f"[5/5] 🛡️  Manual Ruleset Setup Required: Open {res.ruleset.rules_url} to import .signoff/ruleset.json")

        print("\n" + "=" * 60)
        print("✅ Signoff initialization complete!")
        print("=" * 60)
        print(f"\nBranch created: {res.branch}")
        print("\nNext Steps:")
        print(f"  1. Push branch: git push -u origin {res.branch}")
        print("  2. Run /signoff on this branch to review and attest your setup before merging")
        if res.pr_url:
            print(f"  3. Open PR:     {res.pr_url}")
        return 0
    except Exception as e:
        print(f"\n❌ Error during initialization: {e}", file=sys.stderr)
        return 1



if __name__ == "__main__":
    sys.exit(main())
