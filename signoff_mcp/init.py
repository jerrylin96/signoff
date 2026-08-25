"""Zero-touch repository initializer for /signoff (Git Signoff Attestation).

Scaffolds CI workflows, domain interview profiles, agent plugins, README badges,
and GitHub ruleset enforcement.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

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
    try:
        root_str = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=target_dir,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        root = Path(root_str).resolve()
    except subprocess.CalledProcessError:
        raise RuntimeError(f"Not a git repository: {target_dir}")

    # 2. Check Unborn HEAD
    is_unborn = False
    try:
        subprocess.check_output(["git", "rev-parse", "--verify", "HEAD"], cwd=root, stderr=subprocess.DEVNULL)
    except subprocess.CalledProcessError:
        is_unborn = True

    # 3. Current Branch
    current_branch = None
    try:
        b = subprocess.check_output(["git", "branch", "--show-current"], cwd=root, text=True, stderr=subprocess.DEVNULL).strip()
        if b:
            current_branch = b
    except subprocess.CalledProcessError:
        pass

    # 4. Default Branch
    default_branch = "main"
    try:
        ref = subprocess.check_output(
            ["git", "symbolic-ref", "--short", "refs/remotes/origin/HEAD"],
            cwd=root,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        if "/" in ref:
            default_branch = ref.split("/", 1)[1]
    except subprocess.CalledProcessError:
        # Fallback detection
        for candidate in ("main", "master", "trunk", "dev"):
            check = subprocess.run(["git", "show-ref", "--verify", f"refs/heads/{candidate}"], cwd=root, capture_output=True)
            if check.returncode == 0:
                default_branch = candidate
                break

    # 5. Remote Slug
    slug = None
    try:
        remote_url = subprocess.check_output(
            ["git", "remote", "get-url", "origin"],
            cwd=root,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        slug = parse_github_slug(remote_url)
    except subprocess.CalledProcessError:
        pass

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


def merge_claude_settings(repo_root: Path) -> Path:
    claude_dir = repo_root / ".claude"
    claude_dir.mkdir(parents=True, exist_ok=True)
    settings_file = claude_dir / "settings.json"
    
    data: dict = {}
    if settings_file.is_file():
        content = settings_file.read_text(encoding="utf-8").strip()
        if content:
            try:
                parsed = json.loads(content)
                if not isinstance(parsed, dict):
                    raise RuntimeError(f"Existing {settings_file} is not a valid JSON object")
                data = parsed
            except json.JSONDecodeError as e:
                raise RuntimeError(f"Failed to parse existing {settings_file}: {e}")
            
    # Schema: extraKnownMarketplaces nested object and enabledPlugins object map
    marketplaces = data.get("extraKnownMarketplaces", {})
    if not isinstance(marketplaces, dict):
        marketplaces = {}
    marketplaces.setdefault("signoff", {"source": {"source": "github", "repo": "jerrylin96/signoff"}})
    data["extraKnownMarketplaces"] = marketplaces

    plugins = data.get("enabledPlugins", {})
    if isinstance(plugins, list):
        # Migrate legacy array to object map
        plugins = {p: True for p in plugins if isinstance(p, str)}
    elif not isinstance(plugins, dict):
        plugins = {}

    plugins.setdefault("signoff@signoff", True)
    data["enabledPlugins"] = plugins
    
    settings_file.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return settings_file


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
    proc = subprocess.run(["git", "status", "--porcelain"], cwd=repo_root, capture_output=True, text=True, check=True)
    status = proc.stdout
    if not status.strip():
        return

    signoff_prefixes = (
        ".github/workflows/signoff.yml",
        ".signoff/",
        ".signoff",
        ".claude/settings.json",
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
        if any(path_part == p or path_part.startswith(p) for p in signoff_prefixes):
            allowlisted_modifications.append(path_part)
        else:
            unrelated_changes.append(raw_line)

    if unrelated_changes:
        unrelated_str = "\n".join(unrelated_changes)
        raise RuntimeError(f"Working tree has uncommitted changes:\n{unrelated_str}\nUse --allow-dirty to override.")

    if allowlisted_modifications:
        print(f"  ℹ️  Note: Existing modifications to {', '.join(set(allowlisted_modifications))} will be staged.")


def stage_signoff_files(repo_root: Path):
    files = [
        ".github/workflows/signoff.yml",
        ".signoff/profile.md",
        ".signoff/ruleset.json",
        ".claude/settings.json",
        "README.md",
    ]
    for f in files:
        target = repo_root / f
        if target.is_file():
            subprocess.run(["git", "add", f], cwd=repo_root, check=True)


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
) -> InitResult:
    ctx = detect_git_context(repo_root)
    root = ctx.root
    effective_slug = slug or ctx.slug

    # Step 1: Clean tree guard
    ensure_clean_working_tree(root, allow_dirty=allow_dirty)

    # Step 2: Profile selection
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

    # Step 3: Scaffold files
    scaffold_workflow(root, default_branch=ctx.default_branch)
    scaffold_profile(root, profile_id=effective_profile)
    merge_claude_settings(root)
    if effective_slug and not skip_badge:
        inject_readme_badge(root, slug=effective_slug)

    # Step 4: Ruleset setup
    ruleset_res = setup_ruleset(
        root,
        slug=effective_slug,
        open_browser=open_browser,
        skip_ruleset=skip_ruleset,
    )

    # Step 5: Checkout target branch & Commit scaffold files
    target_branch = resolve_branch_name(root, branch)
    if ctx.is_unborn:
        subprocess.run(["git", "checkout", "-b", target_branch], cwd=root, check=True, capture_output=True)
    else:
        # Branch from the default branch to prevent dragging unmerged commits
        subprocess.run(
            ["git", "checkout", "-b", target_branch, ctx.default_branch],
            cwd=root,
            check=True,
            capture_output=True,
        )

    stage_signoff_files(root)
    subprocess.run(["git", "commit", "-m", "chore: scaffold git signoff attestation"], cwd=root, check=True, capture_output=True)

    pr_url = f"https://github.com/{effective_slug}/compare/{ctx.default_branch}...{target_branch}?expand=1" if effective_slug else None

    return InitResult(
        success=True,
        branch=target_branch,
        ruleset=ruleset_res,
        pr_url=pr_url,
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
        )
        print("\n[3/5] 📝 Scaffolded workflow, profile, and settings files.")
        print(f"[4/5] 🌿 Created feature branch '{res.branch}' with scaffold commit.")
        
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
