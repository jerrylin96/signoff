"""Contract tests for the portable GitHub ruleset template (verify/ruleset.json)."""

import json
import os
import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
RULESET_PATH = os.path.join(ROOT, "verify", "ruleset.json")
LEGACY_PATH = os.path.join(ROOT, "Signoff Enforcement.json")

BLACKLISTED_KEYS = {
    "id",
    "ruleset_id",
    "node_id",
    "source",
    "source_type",
    "created_at",
    "updated_at",
}


@pytest.fixture
def ruleset_data():
    assert os.path.exists(RULESET_PATH), f"Expected ruleset at {RULESET_PATH} does not exist"
    with open(RULESET_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def test_legacy_ruleset_deleted():
    """Verify raw untracked / repo-specific ruleset file does not exist in root."""
    assert not os.path.exists(LEGACY_PATH), f"Legacy unportable ruleset file {LEGACY_PATH} must be removed"


def test_ruleset_json_exists_and_parses(ruleset_data):
    """Verify ruleset.json exists and contains standard top-level fields."""
    assert isinstance(ruleset_data, dict)
    assert ruleset_data.get("name") == "Signoff Enforcement" or "Signoff" in ruleset_data.get("name", "")
    assert ruleset_data.get("target") == "branch"
    assert ruleset_data.get("enforcement") == "active"
    assert "conditions" in ruleset_data
    assert "rules" in ruleset_data
    assert "bypass_actors" in ruleset_data


def test_ruleset_no_repo_specific_metadata(ruleset_data):
    """Verify ruleset has no hardcoded instance/repo IDs or metadata."""
    found_blacklisted = set(ruleset_data.keys()) & BLACKLISTED_KEYS
    assert not found_blacklisted, f"Ruleset contains blacklisted repo-specific keys: {found_blacklisted}"


def test_ruleset_portable_targeting(ruleset_data):
    """Verify ruleset targets generic ~DEFAULT_BRANCH rather than hardcoded branch ref."""
    ref_name = ruleset_data.get("conditions", {}).get("ref_name", {})
    includes = ref_name.get("include", [])
    excludes = ref_name.get("exclude", [])

    assert "~DEFAULT_BRANCH" in includes, f"Expected '~DEFAULT_BRANCH' in ref_name.include, got {includes}"
    assert "refs/heads/main" not in includes, "Hardcoded 'refs/heads/main' must not be used in portable template"
    assert excludes == [], f"Expected empty ref_name.exclude, got {excludes}"


def test_ruleset_enforces_all_four_rules(ruleset_data):
    """Verify all four baseline protection rules are present in rules list."""
    rules = ruleset_data.get("rules", [])
    rule_types = {r.get("type") for r in rules if isinstance(r, dict)}
    expected_types = {"deletion", "non_fast_forward", "pull_request", "required_status_checks"}
    assert expected_types.issubset(rule_types), f"Missing rules: {expected_types - rule_types}"


def test_ruleset_pull_request_parameters(ruleset_data):
    """Verify pull_request rule allows standard merge methods."""
    rules = ruleset_data.get("rules", [])
    pr_rule = next((r for r in rules if r.get("type") == "pull_request"), None)
    assert pr_rule is not None, "pull_request rule must be defined"
    params = pr_rule.get("parameters", {})
    allowed_methods = params.get("allowed_merge_methods", [])
    for method in ["merge", "squash", "rebase"]:
        assert method in allowed_methods, f"Merge method '{method}' should be allowed in {allowed_methods}"


def test_ruleset_status_check_context(ruleset_data):
    """Verify status check matches CI workflow job name ('verify') and GitHub Actions app ID (15368)."""
    rules = ruleset_data.get("rules", [])
    check_rule = next((r for r in rules if r.get("type") == "required_status_checks"), None)
    assert check_rule is not None, "required_status_checks rule must be defined"
    params = check_rule.get("parameters", {})
    assert params.get("strict_required_status_checks_policy") is False

    checks = params.get("required_status_checks", [])
    assert len(checks) >= 1, "At least one required status check must be specified"

    contexts = {c.get("context"): c.get("integration_id") for c in checks}
    assert "verify" in contexts, f"Expected status check context 'verify', got {list(contexts.keys())}"
    assert contexts["verify"] == 15368, f"Expected integration_id 15368 for GitHub Actions, got {contexts['verify']}"
