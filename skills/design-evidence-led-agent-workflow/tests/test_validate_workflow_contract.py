from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPT_PATH = SKILL_DIR / "scripts" / "validate_workflow_contract.py"
SPEC = importlib.util.spec_from_file_location("workflow_validator", SCRIPT_PATH)
assert SPEC and SPEC.loader
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)

TEMPLATE_PATH = SKILL_DIR / "assets" / "workflow-contract.template.json"
SHA_A = "a" * 64
SHA_B = "b" * 64
NOW = "2026-08-12T12:00:00+08:00"


def load_template() -> dict:
    return json.loads(TEMPLATE_PATH.read_text(encoding="utf-8"))


def validate(document: dict) -> dict:
    document["run"]["contract_sha256"] = VALIDATOR.canonical_contract_sha256(
        document["contract"]
    )
    return VALIDATOR.validate_document(document)


def codes(report: dict) -> set[str]:
    return {item["code"] for item in report["errors"]}


def complete_local_document() -> dict:
    document = load_template()
    run = document["run"]
    run["status"] = "complete"
    run["object_instances"] = [
        {
            "id": "artifact-v1",
            "object_ref": "primary-artifact",
            "version": 1,
            "locator": "deliverables/artifact.bin",
            "digest": {"algorithm": "sha256", "value": SHA_A},
            "status": "current",
        }
    ]
    run["claims"] = [
        {
            "id": "claim-created",
            "type": "artifact_created",
            "subject_ref": "artifact-v1",
            "status": "verified",
            "evidence_refs": ["ev-artifact"],
        },
        {
            "id": "claim-validated",
            "type": "artifact_validated",
            "subject_ref": "artifact-v1",
            "status": "verified",
            "evidence_refs": ["ev-validator"],
        },
    ]
    common_binding = {
        "object_instance_ref": "artifact-v1",
        "object_sha256": SHA_A,
        "remote_object_id": None,
        "action_ref": "build-artifact",
        "contract_revision": 1,
    }
    run["evidence"] = [
        {
            "id": "ev-artifact",
            "kind": "artifact_snapshot",
            "subject_ref": "artifact-v1",
            "supports_claim_refs": ["claim-created"],
            "result": "pass",
            "observed_at": NOW,
            "producer_ref": "build-artifact",
            "collector_ref": "coordinator",
            "locator": {"scheme": "path", "value": "deliverables/artifact.bin"},
            "digest": {"algorithm": "sha256", "value": SHA_A},
            "binding": dict(common_binding),
            "details": {},
            "redaction": {"contains_secret": False, "safe_to_report": True},
        },
        {
            "id": "ev-validator",
            "kind": "validator_result",
            "subject_ref": "artifact-v1",
            "supports_claim_refs": ["claim-validated"],
            "result": "pass",
            "observed_at": NOW,
            "producer_ref": "build-artifact",
            "collector_ref": "coordinator",
            "locator": {"scheme": "path", "value": "qa/validator.json"},
            "digest": {"algorithm": "sha256", "value": SHA_A},
            "binding": dict(common_binding),
            "details": {},
            "redaction": {"contains_secret": False, "safe_to_report": True},
        },
    ]
    run["gate_results"] = [
        {
            "id": "quality-result",
            "gate_ref": "quality-gate",
            "result": "pass",
            "evidence_refs": ["ev-validator"],
        }
    ]
    run["completion"] = {
        "declared": True,
        "declared_by": "coordinator",
        "declared_at": NOW,
        "partial_object_refs": [],
    }
    return document


class WorkflowContractTests(unittest.TestCase):
    def test_template_is_strict_valid_after_digest_binding(self) -> None:
        report = validate(load_template())
        self.assertTrue(report["strict_valid"], report)

    def test_prompt_cannot_claim_iteration(self) -> None:
        document = load_template()
        document["contract"]["control_model"]["selected"] = "prompt"
        report = validate(document)
        self.assertIn("E_ARCHITECTURE", codes(report))

    def test_completed_local_artifact_is_valid(self) -> None:
        report = validate(complete_local_document())
        self.assertTrue(report["strict_valid"], report)

    def test_submission_receipt_does_not_prove_public_access(self) -> None:
        document = complete_local_document()
        contract = document["contract"]
        contract["success"]["forbidden_claims"] = []
        contract["success"]["targets"][0]["required_claims"] = [
            "public_access_verified"
        ]
        document["run"]["claims"] = [
            {
                "id": "claim-public",
                "type": "public_access_verified",
                "subject_ref": "artifact-v1",
                "status": "verified",
                "evidence_refs": ["ev-submit"],
            }
        ]
        document["run"]["evidence"] = [
            {
                "id": "ev-submit",
                "kind": "operation_receipt",
                "subject_ref": "artifact-v1",
                "supports_claim_refs": ["claim-public"],
                "result": "pass",
                "observed_at": NOW,
                "producer_ref": "build-artifact",
                "collector_ref": "coordinator",
                "locator": {"scheme": "opaque", "value": "receipt-1"},
                "digest": {"algorithm": "sha256", "value": SHA_A},
                "binding": {
                    "object_instance_ref": "artifact-v1",
                    "object_sha256": SHA_A,
                    "action_ref": "build-artifact",
                    "contract_revision": 1,
                },
                "details": {},
                "redaction": {
                    "contains_secret": False,
                    "safe_to_report": True,
                },
            }
        ]
        document["run"]["gate_results"][0]["evidence_refs"] = ["ev-submit"]
        report = validate(document)
        self.assertIn("E_COMPLETION_GAP", codes(report))

    def test_changed_artifact_invalidates_old_evidence(self) -> None:
        document = complete_local_document()
        document["run"]["object_instances"][0]["digest"]["value"] = SHA_B
        report = validate(document)
        self.assertIn("E_EVIDENCE_BINDING", codes(report))

    def test_multi_agent_requires_baseline_and_case(self) -> None:
        document = load_template()
        model = document["contract"]["execution_model"]
        model["selected"] = "multi_agent"
        model["multi_agent_upgrade"]["status"] = "approved"
        report = validate(document)
        self.assertIn("E_BASELINE", codes(report))
        self.assertIn("E_MULTI_AGENT_CASE", codes(report))

    def test_supported_multi_agent_case_is_valid(self) -> None:
        document = load_template()
        document["contract"]["actors"].append(
            {"id": "researcher", "kind": "agent", "roles": ["worker"]}
        )
        model = document["contract"]["execution_model"]
        model["selected"] = "multi_agent"
        baseline = model["single_agent_baseline"]
        baseline["status"] = "completed"
        baseline["task_set_digest"] = {"algorithm": "sha256", "value": SHA_A}
        baseline["run_refs"] = ["baseline-run-1"]
        upgrade = model["multi_agent_upgrade"]
        upgrade.update(
            {
                "status": "approved",
                "baseline_ref": "baseline-run-1",
                "bottlenecks": ["parallelizable_branches"],
                "failure_refs": ["baseline-failure-1", "baseline-failure-2"],
                "hypothesis": {
                    "condition": "同一任务集",
                    "stable_failure_code": "coverage-miss",
                    "change": "增加独立研究分支",
                    "measure": "quality_gate_pass_rate",
                    "direction": "higher_better",
                    "minimum_delta": 0.1,
                },
                "topology": {
                    "coordinator": "coordinator",
                    "workers": ["researcher"],
                },
                "overhead_budget": ["human_review_minutes"],
            }
        )
        report = validate(document)
        self.assertTrue(report["strict_valid"], report)

    def test_two_writers_cannot_modify_single_writer_object(self) -> None:
        document = load_template()
        second = dict(document["contract"]["steps"][0])
        second["id"] = "second-writer"
        second["depends_on"] = ["build-artifact"]
        document["contract"]["steps"].append(second)
        report = validate(document)
        self.assertIn("E_COLLABORATION", codes(report))

    def test_empty_handoff_and_two_completion_writers_fail(self) -> None:
        document = load_template()
        document["contract"]["actors"].append(
            {
                "id": "second-agent",
                "kind": "agent",
                "roles": ["completion_writer"],
            }
        )
        document["run"]["handoffs"] = [
            {
                "id": "empty-handoff",
                "from_ref": "coordinator",
                "to_ref": "second-agent",
                "artifact_refs": [],
                "evidence_refs": [],
                "decision_refs": [],
                "state_change_refs": [],
            }
        ]
        report = validate(document)
        self.assertIn("E_FINAL_AUTHORITY", codes(report))
        self.assertIn("E_COLLABORATION", codes(report))

    def test_high_risk_success_requires_human_approval(self) -> None:
        document = load_template()
        step = document["contract"]["steps"][0]
        step["side_effect"]["action_class"] = "public_release"
        document["contract"]["permissions"]["rules"] = [
            {
                "id": "public-release-rule",
                "action_class": "public_release",
                "executor_refs": ["coordinator"],
                "target_refs": ["primary-artifact"],
                "approval_mode": "per_run",
                "approval_authority_refs": ["owner"],
            }
        ]
        document["run"]["step_records"] = [
            {
                "id": "release-record",
                "step_ref": "build-artifact",
                "status": "succeeded",
            }
        ]
        report = validate(document)
        self.assertIn("E_AUTHORIZATION", codes(report))

    def test_unknown_external_result_cannot_auto_retry(self) -> None:
        document = load_template()
        step = document["contract"]["steps"][0]
        step["side_effect"]["action_class"] = "external_write"
        step["side_effect"]["idempotency"] = "unknown"
        report = validate(document)
        self.assertIn("E_RECOVERY", codes(report))


if __name__ == "__main__":
    unittest.main()
