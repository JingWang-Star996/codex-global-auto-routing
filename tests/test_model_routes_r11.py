import json
from pathlib import Path
import re
import tomllib
import unittest

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = {
    "luna-explorer": ("gpt-6-luna", "low", "read-only"),
    "luna-batch-worker": ("gpt-6-luna", "low", "read-only"),
    "luna-worker": ("gpt-6-luna", "medium", "workspace-write"),
    "terra-explorer": ("gpt-6.1-sol", "medium", "read-only"),
    "terra-worker": ("gpt-6.1-sol", "medium", "workspace-write"),
    "sol-specialist": ("gpt-6.1-sol", "high", "read-only"),
}


class ModelRoutesR11(unittest.TestCase):
    def test_actual_profile_fields_and_receipts_in_both_languages(self):
        for language in (ROOT, ROOT / "i18n/en"):
            for role, expected in EXPECTED.items():
                with self.subTest(language=str(language), role=role):
                    profile = tomllib.loads((language / "agents" / (role + ".toml")).read_text(encoding="utf-8-sig"))
                    self.assertEqual(profile["name"], role.replace("-", "_"))
                    self.assertEqual(tuple(profile[key] for key in ("model", "model_reasoning_effort", "sandbox_mode")), expected)
                    receipts = re.findall(r'\{[^\n]*"configured_model"[^\n]*\}', profile["developer_instructions"])
                    self.assertEqual(len(receipts), 1)
                    receipt = json.loads(receipts[0])
                    self.assertEqual(receipt["agent"], profile["name"])
                    self.assertEqual(receipt["configured_model"], expected[0])
                    self.assertEqual(receipt["configured_sandbox"], expected[2])

    def test_default_changes_only_child_model(self):
        config = tomllib.loads((ROOT / "config.example.toml").read_text(encoding="utf-8-sig"))
        self.assertEqual(config["agents"]["default_subagent_model"], "gpt-6-luna")
        self.assertEqual(config["agents"]["default_subagent_reasoning_effort"], "low")
        self.assertNotIn("model", config)

    def test_original_astra_gate_stays_narrow(self):
        path = ROOT / "scripts/upward_assist.py"
        import importlib.util
        spec = importlib.util.spec_from_file_location("r11_upward", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        root_id = "12345678-1234-4234-9234-123456789abc"
        value = {
            "schema_version": 1, "root_thread_id": root_id,
            "requester_thread_id": root_id, "work_unit_id": "review-1",
            "coordinator_model": "gpt-6.1-sol",
            "authorization": {"approved": True, "scope": "current_root_task",
                              "root_thread_id": root_id, "message_ref": "synthetic-approval"},
            "trigger": "bounded_complexity", "evidence_refs": ["synthetic evidence"],
            "blockers": [], "read_only": True, "task_packet": "Read-only review",
            "max_output_chars": 3000, "max_attempts": 1,
        }
        with self.assertRaises(module.GateError):
            module._validate(value, "0" * 64)
        value["coordinator_model"] = "gpt-5.6-sol"
        self.assertIsInstance(module._validate(value, "0" * 64), dict)


if __name__ == "__main__":
    unittest.main()
