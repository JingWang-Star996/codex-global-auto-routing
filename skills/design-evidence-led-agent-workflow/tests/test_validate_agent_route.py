import importlib.util
import json
from pathlib import Path
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("validate_agent_route", ROOT / "scripts/validate_agent_route.py")
ROUTE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ROUTE)
CHILD, PARENT = "child-001", "root-001"


class AgentRouteTests(unittest.TestCase):
    def setUp(self):
        self.folder = ROOT / "tests/.release-test-output" / ("route-" + uuid.uuid4().hex)
        self.folder.mkdir(parents=True)
        self.profile = self.folder / "profile.toml"
        self.profile.write_text('name = "reader"\nmodel = "target"\nmodel_reasoning_effort = "low"\nsandbox_mode = "read-only"\n', encoding="utf-8")
        self.transcript = self.folder / "child.jsonl"
        self.records = [
            {"type": "session_meta", "payload": {"id": CHILD, "parent_thread_id": PARENT, "agent_role": "reader"}},
            {"type": "turn_context", "payload": {"turn_id": "turn-1", "model": "target", "effort": "low", "sandbox_policy": {"type": "read-only"}}},
        ]

    def check_route(self, **overrides):
        self.transcript.write_text("\n".join(json.dumps(item) for item in self.records), encoding="utf-8")
        kwargs = dict(child_id=CHILD, parent_id=PARENT, requested_model="target", requested_effort="low", registered_model="target")
        kwargs.update(overrides)
        return ROUTE.validate(self.profile, self.transcript, **kwargs)

    def test_matching_metadata_passes(self):
        self.assertTrue(self.check_route()["route_model_verified"])

    def test_cached_role_ignores_requested_model(self):
        self.records[1]["payload"]["model"] = "old-model"
        result = self.check_route(registered_model="old-model")
        self.assertFalse(result["route_model_verified"])
        self.assertEqual(result["actual_model"], "old-model")

    def test_ignored_effort_fails(self):
        self.records[1]["payload"]["effort"] = "high"
        self.assertFalse(self.check_route()["route_model_verified"])

    def test_child_identity_mismatch_fails(self):
        self.assertFalse(self.check_route(child_id="another-child")["route_model_verified"])

    def test_missing_metadata_is_unknown(self):
        self.records.pop()
        result = self.check_route()
        self.assertFalse(result["route_model_verified"])
        self.assertIsNone(result["actual_model"])

    def test_sandbox_override_is_not_isolation_proof(self):
        self.records[1]["payload"]["sandbox_policy"]["type"] = "danger-full-access"
        result = self.check_route()
        self.assertTrue(result["route_model_verified"])
        self.assertFalse(result["sandbox_matches_profile"])
        self.assertFalse(result["host_enforcement_proven"])

    def test_multiple_turns_need_exact_identity(self):
        self.records.append({"type": "turn_context", "payload": {"turn_id": "turn-2", "model": "target", "effort": "low"}})
        self.assertFalse(self.check_route()["route_model_verified"])
        self.assertTrue(self.check_route(turn_id="turn-1")["route_model_verified"])

    def test_self_asserted_success_does_not_override_metadata(self):
        self.records[1]["payload"]["model"] = "wrong-model"
        self.records.append({"type": "event_msg", "payload": {"type": "agent_message", "message": "matches_expected=true"}})
        self.assertFalse(self.check_route()["route_model_verified"])


if __name__ == "__main__":
    unittest.main()
