"""Pin the reference verifier against the published conformance vectors.

conformance/ is the seed suite for third-party GSA implementations; this
test guarantees the reference implementation (verify/verify_signoff.py)
reaches exactly the verdicts published in conformance/expected.json, so the
suite and the implementation cannot drift apart silently.
"""

import importlib.util
import json
import os

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

_SPEC = importlib.util.spec_from_file_location(
    "verify_signoff", os.path.join(ROOT, "verify", "verify_signoff.py")
)
verify_signoff = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(verify_signoff)

with open(os.path.join(ROOT, "conformance", "expected.json"), encoding="utf-8") as f:
    EXPECTED = {k: v for k, v in json.load(f).items() if not k.startswith("_")}


def test_every_vector_file_has_expectations_and_vice_versa():
    vectors_dir = os.path.join(ROOT, "conformance", "vectors")
    files = {f"vectors/{name}" for name in os.listdir(vectors_dir)}
    assert files == set(EXPECTED)


@pytest.mark.parametrize("vector", sorted(EXPECTED))
def test_reference_verifier_matches_expected_verdict(vector):
    exp = EXPECTED[vector]
    with open(os.path.join(ROOT, "conformance", vector), encoding="utf-8") as f:
        payload = f.read()

    trailers = verify_signoff.parse_trailers(payload)
    problems = verify_signoff.validate(trailers)

    assert (not problems) == exp["valid"], problems
    for fragment in exp.get("problems_contain", []):
        assert any(fragment in p for p in problems), (fragment, problems)
    if "status" in exp:
        assert sorted(set(trailers.get("Signoff-Status", []))) == sorted(exp["status"])
    if "reviewed_commit_shas" in exp:
        assert sorted(set(trailers.get("Signoff-Reviewed-Commit-SHA", []))) == sorted(
            exp["reviewed_commit_shas"]
        )
    if "agent_contains" in exp:
        assert any(
            exp["agent_contains"] in v for v in trailers.get("Signoff-Agent", [])
        )
