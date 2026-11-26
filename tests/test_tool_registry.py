import json
import unittest
from pathlib import Path

from src.agent_tools import AgentTools
from src.data_loader import load_data
from src.reconciliation import reconcile
from src.reporting import write_reports
from src.tool_registry import TOOLS, ToolError, ToolRegistry
from tests.fixtures import ROOT, workspace_temp


class RegistryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        financial = Path(cls.enterClassContext(workspace_temp()))
        write_reports(reconcile(load_data(ROOT / "data" / "sample")), financial)
        cls.registry = ToolRegistry(AgentTools(financial, "en"))

    def test_responses_style_definitions_are_closed_and_flat(self):
        definitions = self.registry.definitions()
        self.assertEqual({tool["name"] for tool in definitions}, set(TOOLS))
        self.assertEqual(len(definitions), 5)
        for tool in definitions:
            self.assertEqual(tool["type"], "function")
            self.assertIn("parameters", tool)
            self.assertFalse(tool["parameters"]["additionalProperties"])
            self.assertNotIn("function", tool)

    def test_whitelist_rejects_methods_commands_and_unknown_names(self):
        for name in ("__init__", "read_file", "run_shell", "execute_payment", None):
            with self.subTest(name=name), self.assertRaisesRegex(ToolError, "unauthorized"):
                self.registry.prepare(name, "{}")

    def test_rejects_non_object_malformed_duplicate_keys_and_nonfinite_json(self):
        for raw in ("[]", "{", '{"limit":1,"limit":2}', '{"limit":NaN}', " " * 2001):
            with self.subTest(raw=raw), self.assertRaises(ToolError):
                self.registry.prepare("list_anomalies", raw)

    def test_rejects_missing_and_extra_arguments(self):
        for name, raw in (("get_anomaly_details", "{}"), ("get_reconciliation_summary", '{"path":"secret"}'),
                          ("list_anomalies", '{"command":"read file"}')):
            with self.subTest(name=name), self.assertRaisesRegex(ToolError, "missing or unexpected"):
                self.registry.prepare(name, raw)

    def test_validates_numeric_bounds_and_rejects_boolean_limits(self):
        for limit in (0, 11, True, "4", 1.0, None):
            with self.subTest(limit=limit), self.assertRaisesRegex(ToolError, "limit"):
                self.registry.prepare("list_anomalies", json.dumps({"limit": limit}))
        self.assertEqual(self.registry.prepare("list_anomalies", '{"limit":10}'), {"limit": 10})
        self.assertEqual(self.registry.prepare("list_anomalies", "{}"), {"limit": 5})

    def test_rejects_identifier_period_and_anomaly_type_injections(self):
        for name, args in (
            ("get_anomaly_details", {"anomaly_id": "../../.env"}),
            ("get_anomaly_details", {"anomaly_id": "run arbitrary command"}),
            ("list_anomalies", {"hospital_id": "TEST-A\nshell"}),
            ("list_anomalies", {"settlement_period": "2026-13"}),
            ("list_anomalies", {"settlement_period": "0000-01"}),
            ("list_anomalies", {"anomaly_type": "MATCHED"}),
        ):
            with self.subTest(args=args), self.assertRaisesRegex(ToolError, "Invalid tool argument"):
                self.registry.prepare(name, json.dumps(args))

    def test_direct_dispatch_cannot_bypass_validation(self):
        with self.assertRaisesRegex(ToolError, "unauthorized"):
            self.registry.execute("getattr", {})
        with self.assertRaisesRegex(ToolError, "limit"):
            self.registry.execute("get_review_priorities", {"limit": -1})
