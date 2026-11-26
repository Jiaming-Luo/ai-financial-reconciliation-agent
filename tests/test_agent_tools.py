import json
import unittest
from pathlib import Path

from src.agent_tools import AgentTools
from src.context_builder import SOURCE_FILES, ContextError, build_context
from src.data_loader import load_data
from src.llm_analyzer import analyze, write_analysis
from src.llm_client import MockProvider
from src.reconciliation import reconcile
from src.reporting import write_reports
from src.tool_registry import RecordNotFound
from tests.fixtures import ROOT, load_fixture, service, workspace_temp


class AgentToolsTests(unittest.TestCase):
    def setUp(self):
        root = Path(self.enterContext(workspace_temp()))
        self.financial = root / "financial"
        self.analysis = root / "analysis"
        write_reports(reconcile(load_data(ROOT / "data" / "sample")), self.financial)
        self.tools = AgentTools(self.financial, "en")

    def test_summary_preserves_authoritative_amounts_and_held_records(self):
        result = self.tools.get_reconciliation_summary()
        data = result["data"]
        self.assertEqual(data["net_difference"], "9568.30")
        self.assertEqual(data["reliable_receivable_amount"], "287468.40")
        self.assertEqual(data["eligible_payment_amount"], "308785.10")
        self.assertEqual((data["held_group_count"], data["anomalous_group_count"]), (3, 9))
        self.assertEqual(len(data["held_groups"]), 3)
        self.assertTrue(all(row["difference_amount"] is None for row in data["held_groups"]))
        self.assertIn("summary.json", result["source_files"])

    def test_list_anomalies_filters_and_limits_without_losing_match_count(self):
        full = self.tools.list_anomalies(limit=2)["data"]
        self.assertEqual(full["matched_count"], 9)
        self.assertEqual(len(full["anomalies"]), 2)
        self.assertTrue(full["truncated"])
        selected = self.tools.list_anomalies("SIM-H003", "2026-04", "PRICE_MISMATCH")["data"]
        self.assertEqual([row["anomaly_id"] for row in selected["anomalies"]], ["ANOM-000005"])
        self.assertEqual(self.tools.list_anomalies(hospital_id="TEST-NOT-FOUND")["data"]["matched_count"], 0)

    def test_details_projects_engine_amounts_references_and_manual_actions(self):
        details = AgentTools(self.financial, "cn").get_anomaly_details("ANOM-000005")["data"]
        self.assertEqual(details["amounts"]["difference_amount"], "-4.00")
        self.assertEqual(details["group_amounts"]["difference_amount"], "0.00")
        self.assertIn("SIM-S0187", details["related_record_ids"])
        self.assertTrue(details["review_required"])
        self.assertTrue(all(action["review_required"] for action in details["manual_review_actions"]))
        self.assertIn("计费", details["manual_review_actions"][0]["description"])

    def test_group_reads_held_and_matched_with_exception_without_conflating_statuses(self):
        held = self.tools.get_hospital_reconciliation("SIM-H004", "2026-05")["data"]
        self.assertIsNone(held["expected_amount"])
        self.assertIsNone(held["difference_amount"])
        self.assertEqual(held["settlement_status"], "REVIEW_REQUIRED")
        matched = self.tools.get_hospital_reconciliation("SIM-H003", "2026-04")["data"]
        self.assertEqual(matched["difference_amount"], "0.00")
        self.assertEqual(matched["settlement_status"], "MATCHED")
        self.assertEqual(matched["anomaly_types"], ["PRICE_MISMATCH"])
        self.assertTrue(matched["review_required"])

    def test_unknown_records_do_not_create_zero_balances(self):
        with self.assertRaises(RecordNotFound):
            self.tools.get_anomaly_details("ANOM-NOT-FOUND")
        with self.assertRaises(RecordNotFound):
            self.tools.get_hospital_reconciliation("SIM-H004", "2026-11")

    def test_priority_policy_is_independent_of_optional_ai_suggestions(self):
        baseline = self.tools.get_review_priorities(limit=10)["data"]
        self.assertIsNone(baseline["ai_priority_source"])
        self.assertTrue(all(item["ai_suggested_priority"] is None for item in baseline["priorities"]))
        report = analyze(build_context(self.financial), MockProvider(), "en")
        report["anomaly_findings"][0]["priority"] = "LOW"
        write_analysis(report, self.analysis)
        with_ai = AgentTools(self.financial, "en", self.analysis).get_review_priorities(limit=10)["data"]
        self.assertEqual(with_ai["ai_priority_source"], "v3 analysis (Mock)")
        self.assertEqual([r["business_priority"] for r in baseline["priorities"]],
                         [r["business_priority"] for r in with_ai["priorities"]])
        row = next(item for item in with_ai["priorities"] if item["anomaly_id"] == report["anomaly_findings"][0]["anomaly_id"])
        self.assertEqual((row["business_priority"], row["ai_suggested_priority"]), ("MEDIUM", "LOW"))

    def test_stale_ai_report_cannot_override_engine_evidence(self):
        report = analyze(build_context(self.financial), MockProvider(), "en")
        report["anomaly_findings"][0]["engine_amounts"]["difference_amount"] = "0.00"
        self.analysis.mkdir()
        (self.analysis / "ai_analysis_en.json").write_text(json.dumps(report), encoding="utf-8")
        with self.assertRaisesRegex(ContextError, "do not agree"):
            AgentTools(self.financial, "en", self.analysis)

    def test_provisional_summary_withholds_aggregate_money(self):
        write_reports(reconcile(load_fixture(services=[service(settlement_period="")])), self.financial)
        tools = AgentTools(self.financial, "en")
        data = tools.get_reconciliation_summary()["data"]
        self.assertTrue(tools.provisional)
        self.assertIsNone(data["net_difference"])
        self.assertIsNone(data["eligible_payment_amount"])
        self.assertGreater(data["unassigned_issue_count"], 0)

    def test_read_only_tools_work_without_expected_case_file_and_preserve_reports(self):
        before = {name: (self.financial / name).read_bytes() for name in SOURCE_FILES}
        self.tools.get_reconciliation_summary()
        self.tools.list_anomalies()
        self.tools.get_anomaly_details("ANOM-000005")
        self.tools.get_hospital_reconciliation("SIM-H004", "2026-05")
        self.tools.get_review_priorities()
        self.assertEqual({p.name for p in self.financial.iterdir()}, set(SOURCE_FILES))
        self.assertEqual(before, {name: (self.financial / name).read_bytes() for name in SOURCE_FILES})
