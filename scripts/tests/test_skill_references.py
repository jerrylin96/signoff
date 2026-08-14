"""Skill contract tests for the standalone signoff repo.

Trimmed from dotgemini's scripts/tests/test_skill_references.py (whose history
this file carries): only the signoff-relevant contracts remain. Cross-skill
references to skills not shipped in this repo (e.g. @skill:explain-diff) are
allowed when documented as degrading gracefully in HARNESSES.md portability
rules; everything else must resolve to a valid in-repo skill.
"""

import glob
import os
import re

# External skills referenced by signoff that degrade gracefully when absent
# (HARNESSES.md, Portability Rules #3).
GRACEFUL_EXTERNAL_SKILLS = {"explain-diff", "make-feature"}


def parse_frontmatter_name(skill_md_path):
    """Parse name from YAML frontmatter without external YAML parser dependency."""
    if not os.path.exists(skill_md_path):
        return None
    with open(skill_md_path, "r", encoding="utf-8") as f:
        content = f.read()

    if not content.startswith("---"):
        return None

    lines = content.splitlines()
    if not lines or lines[0] != "---":
        return None

    closing_idx = -1
    for i in range(1, len(lines)):
        if lines[i] == "---":
            closing_idx = i
            break

    if closing_idx == -1:
        return None

    frontmatter_lines = lines[1:closing_idx]

    name_value = None
    for line in frontmatter_lines:
        match = re.match(r"^name:\s*(.+)$", line)
        if match:
            name_value = match.group(1).strip()
            break

    if not name_value:
        return None

    if (name_value.startswith('"') and name_value.endswith('"')) or (name_value.startswith("'") and name_value.endswith("'")):
        name_value = name_value[1:-1].strip()

    if not re.match(r"^[a-zA-Z0-9_-]+$", name_value):
        return None

    return name_value


def validate_skill_resolution(skills_dir, skill_name):
    """Validate skill folder structure and frontmatter name."""
    skill_path = os.path.join(skills_dir, skill_name)
    if not os.path.exists(skill_path) or not os.path.isdir(skill_path):
        return f"Directory skills/{skill_name} does not exist."

    skill_md_path = os.path.join(skill_path, "SKILL.md")
    if not os.path.exists(skill_md_path):
        return f"File skills/{skill_name}/SKILL.md does not exist."

    fm_name = parse_frontmatter_name(skill_md_path)
    if not fm_name:
        return f"skills/{skill_name}/SKILL.md is missing name in frontmatter."

    if fm_name != skill_name:
        return f"skills/{skill_name}/SKILL.md has mismatched frontmatter name '{fm_name}' (expected '{skill_name}')."

    return None


def _skills_dir():
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "../../skills"))


def test_all_skill_references_resolve_or_degrade_gracefully():
    """Every @skill:<name> reference resolves in-repo or is a documented graceful-degradation external."""
    skills_dir = _skills_dir()
    skill_ref_pattern = re.compile(r"@skill:([a-zA-Z0-9_-]+)")

    errors = []
    markdown_files = glob.glob(os.path.join(skills_dir, "**/*.md"), recursive=True)
    assert markdown_files, "no markdown files found under skills/"
    for filepath in markdown_files:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        for ref in skill_ref_pattern.findall(content):
            if ref in GRACEFUL_EXTERNAL_SKILLS:
                continue
            err = validate_skill_resolution(skills_dir, ref)
            if err:
                rel_path = os.path.relpath(filepath, skills_dir)
                errors.append(f"In {rel_path}: reference '@skill:{ref}' failed validation: {err}")

    assert not errors, "\n".join(errors)


def test_all_skills_have_correct_frontmatter_name():
    """Verify all existing skill directories match their frontmatter names."""
    skills_dir = _skills_dir()
    for skill_name in os.listdir(skills_dir):
        skill_path = os.path.join(skills_dir, skill_name)
        if os.path.isdir(skill_path) and not skill_name.startswith("."):
            err = validate_skill_resolution(skills_dir, skill_name)
            assert err is None, f"Skill '{skill_name}' failed validation: {err}"


def test_no_non_portable_file_links():
    """Verify that no markdown file contains file:// URLs (prohibited for portability)."""
    skills_dir = _skills_dir()
    file_link_pattern = re.compile(r"\]\((file://[^\)]+)\)")

    errors = []
    markdown_files = glob.glob(os.path.join(skills_dir, "**/*.md"), recursive=True)
    for filepath in markdown_files:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        for link in file_link_pattern.findall(content):
            rel_path = os.path.relpath(filepath, skills_dir)
            errors.append(f"In {rel_path}: file:// link found: '{link}' (file:// links are prohibited)")

    assert not errors, "\n".join(errors)


def test_skill_folder_is_self_contained():
    """No relative markdown link inside skills/signoff may escape the folder (Phase 3a)."""
    skills_dir = _skills_dir()
    signoff_dir = os.path.join(skills_dir, "signoff")
    link_pattern = re.compile(r"\]\(([^)#\s]+)")

    errors = []
    for filepath in glob.glob(os.path.join(signoff_dir, "**/*.md"), recursive=True):
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        for target in link_pattern.findall(content):
            if re.match(r"^[a-z][a-z0-9+.-]*:", target):  # URLs (https:, mailto:, ...)
                continue
            resolved = os.path.normpath(os.path.join(os.path.dirname(filepath), target))
            if not resolved.startswith(signoff_dir + os.sep):
                rel = os.path.relpath(filepath, skills_dir)
                errors.append(f"In {rel}: link '{target}' escapes skills/signoff")

    assert not errors, "\n".join(errors)


# Focused test cases using pytest tmp_path
def test_validation_missing_directory(tmp_path):
    err = validate_skill_resolution(str(tmp_path), "missing-skill")
    assert "does not exist" in err


def test_validation_missing_skill_md(tmp_path):
    skill_dir = tmp_path / "no-skill-md"
    skill_dir.mkdir()
    err = validate_skill_resolution(str(tmp_path), "no-skill-md")
    assert "SKILL.md does not exist" in err


def test_validation_mismatched_frontmatter_name(tmp_path):
    skill_dir = tmp_path / "mismatch-name"
    skill_dir.mkdir()
    skill_md = skill_dir / "SKILL.md"
    skill_md.write_text("---\nname: different-name\n---\nbody")
    err = validate_skill_resolution(str(tmp_path), "mismatch-name")
    assert "mismatched frontmatter name" in err


def test_validation_quoted_valid_name(tmp_path):
    skill_dir = tmp_path / "quoted-name"
    skill_dir.mkdir()
    skill_md = skill_dir / "SKILL.md"
    skill_md.write_text("---\nname: \"quoted-name\"\n---\nbody")
    err = validate_skill_resolution(str(tmp_path), "quoted-name")
    assert err is None


def test_signoff_socratic_remediation_rule():
    """Verify skills/signoff/SKILL.md defines hardened Socratic remediation rules."""
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
    signoff_md = os.path.join(root_dir, "skills/signoff/SKILL.md")

    assert os.path.exists(signoff_md), "skills/signoff/SKILL.md does not exist"

    with open(signoff_md, "r", encoding="utf-8") as f:
        signoff_content = f.read()

    assert "Evaluation & Remediation" in signoff_content, "Missing Evaluation & Remediation in skills/signoff/SKILL.md"

    section_match = re.search(r"Evaluation & Remediation:\s*(.*?)(?=\n### |\n## |\Z)", signoff_content, re.DOTALL)
    assert section_match, "Could not extract Evaluation & Remediation section from skills/signoff/SKILL.md"
    remediation_text = section_match.group(1)

    assert any(term in remediation_text for term in ["not sure", "uncertainty"]), "Missing uncertainty trigger in remediation rule"
    assert "vague" in remediation_text or "hand-waving" in remediation_text, "Missing vague/hand-waving trigger in remediation rule"
    assert "pause signoff" in remediation_text, "Missing 'pause signoff' in remediation rule"
    assert "@skill:explain-diff" in remediation_text, "Missing '@skill:explain-diff' reference in remediation rule"
    assert "re-probe" in remediation_text, "Missing re-probing requirement in remediation rule"

    assert "Worktree Target Mandate" in signoff_content, "Missing Worktree Target Mandate in skills/signoff/SKILL.md"
    assert "worktree_path" in signoff_content, "Missing 'worktree_path' in skills/signoff/SKILL.md Section 4"


def test_signoff_gsa_protocol_spec_and_trailers():
    """Verify the GSA Protocol core spec exists and skills/signoff/SKILL.md implements its portable trailer schema, harness adapters, and Git Notes persistence."""
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
    spec_md = os.path.join(root_dir, "skills/signoff/specs/gsa-core.md")
    signoff_md = os.path.join(root_dir, "skills/signoff/SKILL.md")

    assert os.path.exists(spec_md), "skills/signoff/specs/gsa-core.md does not exist"

    with open(spec_md, "r", encoding="utf-8") as f:
        spec_content = f.read()

    for anchor in [
        "Protocol Specification",
        "Cryptographic Developer Identity Binding",
        "cat_sort_uniq",
        "ack_no_transcript",
    ]:
        assert anchor in spec_content, f"Missing '{anchor}' in skills/signoff/specs/gsa-core.md"

    with open(signoff_md, "r", encoding="utf-8") as f:
        signoff_content = f.read()

    for trailer in [
        "Signoff-Spec-Version: 1.0",
        "Signoff-Harness-ID",
        "Signoff-Transcript-Bytes",
    ]:
        assert trailer in signoff_content, f"Missing '{trailer}' trailer in skills/signoff/SKILL.md"

    for adapter_env in [
        "SIGNOFF_TRANSCRIPT_FILE",
        "ANTIGRAVITY_CONVERSATION_ID",
        "CLAUDE_CODE_SESSION_ID",
    ]:
        assert adapter_env in signoff_content, f"Missing '{adapter_env}' adapter resolution in skills/signoff/SKILL.md"

    assert "--git-common-dir" in signoff_content, "Missing worktree git-common-dir fallback in skills/signoff/SKILL.md"

    assert "refs/notes/signoff" in signoff_content, "Missing 'refs/notes/signoff' persistence in skills/signoff/SKILL.md"
    assert "cat_sort_uniq" in signoff_content, "Missing 'cat_sort_uniq' notes merge strategy in skills/signoff/SKILL.md"
    assert "refs/notes/signoff-remote" in signoff_content, "Missing tracking-ref fetch for notes merge in skills/signoff/SKILL.md"

    assert "user.signingkey" in signoff_content, "Missing signed-commit support (user.signingkey) in skills/signoff/SKILL.md"

    assert "specs/gsa-core.md" in signoff_content, "Missing specs/gsa-core.md reference in skills/signoff/SKILL.md"


PROFILE_BLOCK_RE = re.compile(
    r"<!-- INTERVIEW-PROFILE:BEGIN[^>]*-->\n(.*?)<!-- INTERVIEW-PROFILE:END -->",
    re.DOTALL,
)


def _extract_profile_block(content, source):
    blocks = PROFILE_BLOCK_RE.findall(content)
    assert len(blocks) == 1, f"Expected exactly one INTERVIEW PROFILE block in {source}, found {len(blocks)}"
    return blocks[0]


def test_signoff_phase3c_interview_contract():
    """Verify Phase 3c: Signoff-Agent provenance grammar, named intensity levels, and the single swappable INTERVIEW PROFILE block."""
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
    signoff_md = os.path.join(root_dir, "skills/signoff/SKILL.md")
    spec_md = os.path.join(root_dir, "skills/signoff/specs/gsa-core.md")
    harnesses_md = os.path.join(root_dir, "skills/signoff/HARNESSES.md")
    default_profile_md = os.path.join(root_dir, "skills/signoff/profiles/software-general.md")
    science_profile_md = os.path.join(root_dir, "skills/signoff/profiles/domain-science.md")

    for path in [signoff_md, spec_md, harnesses_md, default_profile_md, science_profile_md]:
        assert os.path.exists(path), f"{os.path.relpath(path, root_dir)} does not exist"

    with open(signoff_md, "r", encoding="utf-8") as f:
        signoff_content = f.read()
    with open(spec_md, "r", encoding="utf-8") as f:
        spec_content = f.read()
    with open(harnesses_md, "r", encoding="utf-8") as f:
        harnesses_content = f.read()
    with open(default_profile_md, "r", encoding="utf-8") as f:
        default_profile_content = f.read()
    with open(science_profile_md, "r", encoding="utf-8") as f:
        science_profile_content = f.read()

    # (1) Signoff-Agent provenance grammar defined in the spec and used by the skill
    for token in ["harness=", "model=", "reasoning=", "interview="]:
        assert token in signoff_content, f"Signoff-Agent grammar token '{token}' missing from skills/signoff/SKILL.md"
        assert token in spec_content, f"Signoff-Agent grammar token '{token}' missing from skills/signoff/specs/gsa-core.md"
    assert "N/A" in spec_content, "Missing N/A convention for unexposed provenance fields in gsa-core.md"
    for env_var in ["CLAUDE_CODE_VERSION", "CLAUDE_EFFORT", "ANTHROPIC_MODEL"]:
        assert env_var in signoff_content, f"Deterministic provenance source '{env_var}' missing from skills/signoff/SKILL.md"

    # (2) Named intensity levels formalizing --quick/--deep
    for level in ["cursory", "standard", "skeptical"]:
        assert level in signoff_content, f"Intensity level '{level}' missing from skills/signoff/SKILL.md"
    assert "--quick" in signoff_content and "--deep" in signoff_content, "Missing --quick/--deep modifier mapping in skills/signoff/SKILL.md"
    assert "Interview Intensity Levels" in signoff_content, "Missing Interview Intensity Levels section in skills/signoff/SKILL.md"
    assert "prediction challenge" in signoff_content, "Missing skeptical-level prediction challenges in skills/signoff/SKILL.md"

    # (3) Exactly one delimited INTERVIEW PROFILE block, byte-identical to the shipped default
    embedded_block = _extract_profile_block(signoff_content, "skills/signoff/SKILL.md")
    default_block = _extract_profile_block(default_profile_content, "skills/signoff/profiles/software-general.md")
    assert embedded_block == default_block, (
        "Embedded INTERVIEW PROFILE block in SKILL.md diverged from profiles/software-general.md"
    )

    for block, source in [
        (embedded_block, "skills/signoff/SKILL.md"),
        (science_profile_content, "skills/signoff/profiles/domain-science.md"),
    ]:
        pid = re.search(r"^Profile-ID:\s*([a-z0-9-]+)\s*$", block, re.MULTILINE)
        assert pid, f"Missing or malformed Profile-ID in {source}"
    assert "Profile-ID: software-general" in embedded_block, "Default embedded profile must be software-general"
    assert "Profile-ID: domain-science" in science_profile_content, "domain-science profile must declare its Profile-ID"

    assert "sole customization point" in signoff_content, "Missing 'sole customization point' marker in skills/signoff/SKILL.md"
    assert "sole customization point" in harnesses_content, "Missing 'sole customization point' documentation in skills/signoff/HARNESSES.md"
    assert "profiles/software-general.md" in harnesses_content, "Missing software-general profile reference in HARNESSES.md"
    assert "profiles/domain-science.md" in harnesses_content, "Missing domain-science profile reference in HARNESSES.md"


def test_signoff_phase3d_research_accessibility_contract():
    """Verify Phase 3d: repo-local profile resolution, science-detection guard, profile provenance digest, and expanded science profile."""
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
    paths = {
        "skills/signoff/SKILL.md": None,
        "skills/signoff/specs/gsa-core.md": None,
        "skills/signoff/HARNESSES.md": None,
        "skills/signoff/profiles/domain-science.md": None,
    }
    for rel in paths:
        path = os.path.join(root_dir, rel)
        assert os.path.exists(path), f"{rel} does not exist"
        with open(path, "r", encoding="utf-8") as f:
            paths[rel] = f.read()
    signoff_content = paths["skills/signoff/SKILL.md"]
    spec_content = paths["skills/signoff/specs/gsa-core.md"]
    harnesses_content = paths["skills/signoff/HARNESSES.md"]
    science_profile_content = paths["skills/signoff/profiles/domain-science.md"]

    # (1) Repo-local profile resolution: env override -> repo-local file -> embedded default
    for needle in ["SIGNOFF_PROFILE_FILE", ".signoff/profile.md"]:
        for content, source in [
            (signoff_content, "skills/signoff/SKILL.md"),
            (spec_content, "skills/signoff/specs/gsa-core.md"),
            (harnesses_content, "skills/signoff/HARNESSES.md"),
        ]:
            assert needle in content, f"Missing '{needle}' in {source}"
    assert "fall back to the embedded default" in signoff_content, (
        "Missing malformed-profile fallback rule in skills/signoff/SKILL.md"
    )
    # Resolution must not introduce a second literal block in SKILL.md
    _extract_profile_block(signoff_content, "skills/signoff/SKILL.md")

    # (2) Science-detection guard: additive, default-on, wired into cursory eligibility
    assert "Science-detection escalation" in signoff_content, "Missing science-detection guard in skills/signoff/SKILL.md"
    assert "profiles/domain-science.md" in signoff_content, "Science guard must reference profiles/domain-science.md"
    for signal in ["numpy", "ipynb", "netCDF"]:
        assert signal in signoff_content, f"Missing science-detection signal '{signal}' in skills/signoff/SKILL.md"
    assert "Additive only" in signoff_content, "Science guard must be additive-only in skills/signoff/SKILL.md"
    assert "cursory MUST be refused" in signoff_content, "Science-flagged diffs must refuse cursory in skills/signoff/SKILL.md"

    # (3) Profile provenance: digest-extended interview= token
    assert "PROFILE_DIGEST" in signoff_content, "Missing PROFILE_DIGEST computation in skills/signoff/SKILL.md"
    assert "/sha256:" in signoff_content, "Missing /sha256: digest segment in skills/signoff/SKILL.md"
    assert "[/sha256:<profile-digest-prefix>]" in spec_content, (
        "Missing optional profile-digest segment in gsa-core.md Signoff-Agent grammar"
    )
    assert "interview=<level>/<profile-id>/sha256:<digest>" in harnesses_content, (
        "Missing profile provenance documentation in HARNESSES.md"
    )

    # (4) Expanded science emphases (numerical stability, uncertainty quantification)
    for term in ["Numerical stability", "cancellation", "Uncertainty quantification"]:
        assert term in science_profile_content, (
            f"Missing '{term}' emphasis in skills/signoff/profiles/domain-science.md"
        )


def test_signoff_phase3f_adaptive_intensity_contract():
    """Verify Phase 3f: Adaptive signoff interview intensity based on semantic impact and code churn."""
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
    paths = {
        "skills/signoff/SKILL.md": None,
        "skills/signoff/specs/gsa-core.md": None,
        "skills/signoff/HARNESSES.md": None,
        "README.md": None,
        "site/index.html": None,
    }
    for rel in paths:
        path = os.path.join(root_dir, rel)
        assert os.path.exists(path), f"{rel} does not exist"
        with open(path, "r", encoding="utf-8") as f:
            paths[rel] = f.read()
    signoff_content = paths["skills/signoff/SKILL.md"]
    spec_content = paths["skills/signoff/specs/gsa-core.md"]
    harnesses_content = paths["skills/signoff/HARNESSES.md"]
    readme_content = paths["README.md"]
    site_content = paths["site/index.html"]

    # (1) Phase 3f identifier and cross-references
    assert "Phase 3f (Adaptive Signoff Interview Intensity)" in spec_content, "Missing Phase 3f entry in gsa-core.md"
    assert "test_signoff_phase3f_adaptive_intensity_contract" in spec_content, (
        "Phase 3f in gsa-core.md must reference test_signoff_phase3f_adaptive_intensity_contract"
    )
    assert "live classification dogfood pending" in spec_content, (
        "Phase 3f status in gsa-core.md must note live classification dogfood pending"
    )

    # (2) Adaptive classification matrix & naming
    assert "Interview Intensity Levels & Adaptive Classification Matrix" in signoff_content, (
        "Missing intensity matrix heading in skills/signoff/SKILL.md"
    )
    assert "governs auto-classification for bare" in signoff_content, (
        "Missing bare /signoff auto-classification scoping sentence in SKILL.md"
    )
    for tier in ["Tier 0", "Tier 1", "Tier 2"]:
        assert tier in signoff_content, f"Missing '{tier}' classification in skills/signoff/SKILL.md"

    # (3) Probe count floors (no silent lowering of rigor)
    assert "2 (one turn)" in signoff_content, "Tier 0 / cursory probe count must be 2"
    assert "4–6 (2–3 turns)" in signoff_content, "Tier 1 / standard probe count must be 4–6"
    assert "8+ (4+ turns)" in signoff_content, "Tier 2 / skeptical probe count must be 8+"

    # (4) Pass criteria invariants
    assert "riskiest consequence" in signoff_content, "Tier 0 must require riskiest consequence acceptance"
    assert "At least one probe per universal axis" in signoff_content, "Tier 1 must require 1 probe per axis"
    assert "At least two probes per universal axis" in signoff_content, "Tier 2 must require 2 probes per axis"
    assert "prediction challenges" in signoff_content, "Tier 2 must require prediction challenges"
    assert "Restating the diff does not pass" in signoff_content, "Tier 2 must enforce anti-restating rule"

    # (5) Canonical High-Impact Tier 2 triggers
    assert "Canonical High-Impact Tier 2 Heuristic Triggers" in signoff_content, (
        "Missing Canonical Tier 2 triggers block in skills/signoff/SKILL.md"
    )
    for trigger_signal in [
        "auth/", "crypto/", "permissions/", "migrations/", "schema.sql", "ALTER TABLE",
        "proto", "OpenAPI", "numpy", "scipy", "jax", "torch", "astropy", "pandas", "xarray",
        ".ipynb", "netCDF", "GRIB", "zarr"
    ]:
        assert trigger_signal in signoff_content, f"Missing Tier 2 trigger '{trigger_signal}' in skills/signoff/SKILL.md"
    assert ">5 files or >200 lines" in signoff_content, "Missing blast radius threshold in skills/signoff/SKILL.md"

    # (6) Evaluation order & documentation capping
    assert "Classification Precedence & Evaluation Order" in signoff_content, (
        "Missing evaluation order in skills/signoff/SKILL.md"
    )
    assert "<50" in signoff_content, "Missing Tier 0 LoC threshold in skills/signoff/SKILL.md"
    assert "capped at max Tier 1" in signoff_content or "capped at Tier 1" in signoff_content, (
        "Missing pure docs Tier 1 capping rule in skills/signoff/SKILL.md"
    )

    # (7) Modifier precedence, safety clamps, and graduated escalation
    assert "4-row safety clamp" in signoff_content or "4-row" in signoff_content, (
        "Missing 4-row safety clamp definition in skills/signoff/SKILL.md"
    )
    assert "refuse cursory and auto-escalate to Tier 1" in signoff_content, (
        "Missing Tier 1 docs blast radius escalation in SKILL.md"
    )
    assert "refuse cursory and auto-escalate to Tier 2" in signoff_content, (
        "Missing Tier 2 high-impact/executable blast radius escalation in SKILL.md"
    )
    assert "--deep" in signoff_content, "Missing --deep mapping in skills/signoff/SKILL.md"
    assert "Graduated One-Way Escalation" in signoff_content, "Missing graduated escalation heading in SKILL.md"
    assert "Never de-escalate within a session" in signoff_content, "Missing no de-escalation rule in SKILL.md"

    # (8) Science probe requirement (additive rigor)
    assert "at least two of the skeptical probes MUST apply domain-science emphases" in signoff_content, (
        "Science guard must explicitly require at least two domain-science emphasis probes"
    )
    assert "satisfied by Tier 2's two-per-axis requirement" not in signoff_content, (
        "Removed cop-out claim that science probe requirement is automatically satisfied"
    )

    # (9) Attestation trailer level name rule & LaTeX rendering check
    assert "never record the tier label" in signoff_content, "Missing trailer level naming rule in SKILL.md"
    assert "$\\to$" not in signoff_content, "Found non-rendering LaTeX $\\to$ in SKILL.md"

    # (10) Cross-surface synchronization
    assert "adaptive intensity by default" in harnesses_content.lower(), "Missing adaptive intensity in HARNESSES.md"
    assert "capped at tier 1" in harnesses_content.lower(), "Missing docs cap mention in HARNESSES.md"
    assert "adaptive default auto-selects intensity" in readme_content.lower(), "Missing adaptive default in README.md"
    assert "adaptive default auto-selects intensity" in site_content.lower(), "Missing adaptive default in site/index.html"


