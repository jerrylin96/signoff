"""Contract tests for the portable GitHub ruleset template (verify/ruleset.json)."""

import json
import os
import re
import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
RULESET_PATH = os.path.join(ROOT, "verify", "ruleset.json")
LEGACY_PATH = os.path.join(ROOT, "Signoff Enforcement.json")
WORKFLOW_PATH = os.path.join(ROOT, ".github", "workflows", "signoff.yml")

ALLOWED_TOP_LEVEL_KEYS = {
    "name",
    "target",
    "enforcement",
    "conditions",
    "rules",
    "bypass_actors",
}

BLACKLISTED_METADATA_KEYS = {
    "id",
    "ruleset_id",
    "node_id",
    "source",
    "source_type",
    "created_at",
    "updated_at",
}

ALLOWED_PR_PARAM_KEYS = {
    "required_approving_review_count",
    "dismiss_stale_reviews_on_push",
    "required_reviewers",
    "require_code_owner_review",
    "require_last_push_approval",
    "required_review_thread_resolution",
    "allowed_merge_methods",
}

ALLOWED_STATUS_CHECK_PARAM_KEYS = {
    "strict_required_status_checks_policy",
    "do_not_enforce_on_create",
    "required_status_checks",
}


@pytest.fixture
def ruleset_data():
    assert os.path.exists(RULESET_PATH), f"Expected ruleset at {RULESET_PATH} does not exist"
    with open(RULESET_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def extract_signoff_workflow_job_name():
    assert os.path.exists(WORKFLOW_PATH), f"Workflow file {WORKFLOW_PATH} does not exist"
    with open(WORKFLOW_PATH, "r", encoding="utf-8") as f:
        content = f.read()
    # Find job names declared under `jobs:` indented by 2 spaces
    m = re.search(r"^jobs:\s*\n\s{2}([a-zA-Z0-9_-]+):", content, re.MULTILINE)
    assert m, "Could not extract primary job name from .github/workflows/signoff.yml"
    return m.group(1)


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


def test_ruleset_allowed_top_level_keys(ruleset_data):
    """Verify ruleset does not contain extraneous or non-standard top-level keys."""
    extra_keys = set(ruleset_data.keys()) - ALLOWED_TOP_LEVEL_KEYS
    assert not extra_keys, f"Found unexpected top-level keys in ruleset: {extra_keys}"


def test_ruleset_no_repo_specific_metadata(ruleset_data):
    """Verify ruleset has no hardcoded instance/repo IDs or metadata."""
    found_blacklisted = set(ruleset_data.keys()) & BLACKLISTED_METADATA_KEYS
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
    """Verify pull_request rule parameters match canonical GitHub ruleset schema and allow merge methods."""
    rules = ruleset_data.get("rules", [])
    pr_rule = next((r for r in rules if r.get("type") == "pull_request"), None)
    assert pr_rule is not None, "pull_request rule must be defined"
    params = pr_rule.get("parameters", {})

    # Disallow invalid / non-standard keys like require_extra_approval_for_unattributed_changes
    extra_params = set(params.keys()) - ALLOWED_PR_PARAM_KEYS
    assert not extra_params, f"Found invalid parameters in pull_request rule: {extra_params}"

    allowed_methods = params.get("allowed_merge_methods", [])
    for method in ["merge", "squash", "rebase"]:
        assert method in allowed_methods, f"Merge method '{method}' should be allowed in {allowed_methods}"


def test_ruleset_status_check_context(ruleset_data):
    """Verify status check parameters match GitHub schema and specify integration_id 15368."""
    rules = ruleset_data.get("rules", [])
    check_rule = next((r for r in rules if r.get("type") == "required_status_checks"), None)
    assert check_rule is not None, "required_status_checks rule must be defined"
    params = check_rule.get("parameters", {})

    extra_params = set(params.keys()) - ALLOWED_STATUS_CHECK_PARAM_KEYS
    assert not extra_params, f"Found invalid parameters in required_status_checks rule: {extra_params}"
    # Freshness requirement: strict mode ensures PR branch is up to date with base before merge,
    # preventing human-reviewed attestation states from silently going stale when base advances.
    assert params.get("strict_required_status_checks_policy") is True

    checks = params.get("required_status_checks", [])
    assert len(checks) >= 1, "At least one required status check must be specified"

    for check in checks:
        assert check.get("integration_id") == 15368, f"Expected integration_id 15368 for Actions, got {check.get('integration_id')}"


def test_ruleset_and_workflow_status_check_synchronized(ruleset_data):
    """Regression test: workflow job name in signoff.yml and required context in ruleset.json are synchronized."""
    workflow_job_name = extract_signoff_workflow_job_name()
    rules = ruleset_data.get("rules", [])
    check_rule = next((r for r in rules if r.get("type") == "required_status_checks"), None)
    assert check_rule is not None, "required_status_checks rule must be defined"
    checks = check_rule.get("parameters", {}).get("required_status_checks", [])
    contexts = [c.get("context") for c in checks]

    assert workflow_job_name in contexts, (
        f"Workflow job name '{workflow_job_name}' in .github/workflows/signoff.yml "
        f"does not match required status checks in verify/ruleset.json ({contexts})"
    )
