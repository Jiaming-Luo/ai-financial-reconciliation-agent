"""Coverage of mandatory structured findings and optional prose failures."""

import io
import json
import os
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from scripts.verify_qwen_live import main as verify_cli
from src.action_catalog import ACTION_CATALOG, REQUEST_ADDITIONAL_EVIDENCE, eligible_actions
from src.anomaly_detector import RECOMMENDED_ACTIONS
from src.context_builder import SOURCE_FILES, build_context
from src.data_loader import load_data
from src.llm_analyzer import analyze, render_markdown
from src.llm_client import LLMResponse, MockProvider
from src.output_validator import OutputValidationError, validate_output
from src.prompts import ACTION_SCHEMA
from src.reconciliation import reconcile
from src.reporting import write_reports
from tests.fixtures import ROOT, workspace_temp
from tests.test_qwen_provider import ENV, local_transport, reply


class ActionContractTests(unittest.TestCase):
    def setUp(self):
        self.source = {
            "anomaly_id": "TEST-A", "anomaly_type": "PRICE_MISMATCH",
            "evidence_references": ["TEST-S", "TEST-C", "TEST-OTHER"],
            "action_options": eligible_actions(
                "PRICE_MISMATCH", {"service_record": ["TEST-S"], "matched_contract": ["TEST-C"]},
            ),
        }
        self.payload = {"language": "en", "analysis_scope": "ANOMALY_ANALYSIS", "findings": [self.source]}
        self.answer = json.loads(MockProvider().generate("en", self.payload).text)

    def verify(self, action_code, refs):
        action = {"action_code": action_code, "evidence_references": refs}
        self.answer["anomaly_findings"][0]["recommended_actions"] = [action]
        return validate_output(json.dumps(self.answer), self.payload)

    def test_valid_manual_action_enum_preserves_citations(self):
        result = self.verify("CONFIRM_BILLING_QUANTITY", ["TEST-C", "TEST-S"])
        self.assertEqual(result["anomaly_findings"][0]["recommended_actions"], [{
            "action_code": "CONFIRM_BILLING_QUANTITY", "evidence_references": ["TEST-C", "TEST-S"],
        }])
        self.assertEqual(set(ACTION_SCHEMA["properties"]["action_code"]["enum"]), set(ACTION_CATALOG))
        self.assertEqual(set().union(
            *(set(entry.applicable_anomaly_types) for entry in ACTION_CATALOG.values() if entry.required_evidence)
        ), set(RECOMMENDED_ACTIONS))
        self.assertTrue(all(entry.review_required is True for entry in ACTION_CATALOG.values()))

    def test_unknown_or_unauthorized_action_is_rejected(self):
        for code in ("EXECUTE_PAYMENT", "MODIFY_SETTLEMENT", "TEST-NO-SUCH-CODE"):
            with self.subTest(code=code), self.assertRaisesRegex(OutputValidationError, "unknown_action") as error:
                self.verify(code, [])
            self.assertNotIn(code, str(error.exception))

    def test_known_action_for_another_anomaly_is_rejected(self):
        with self.assertRaisesRegex(OutputValidationError, "action_type"):
            self.verify("VERIFY_PAYMENT_RECORDS", ["TEST-S"])

    def test_action_rejects_foreign_invented_and_wrong_role_references(self):
        self.payload["findings"].append({
            "anomaly_id": "TEST-B", "anomaly_type": "MISSING_CONTRACT", "evidence_references": ["TEST-FOREIGN"],
        })
        self.answer = json.loads(MockProvider().generate("en", self.payload).text)
        for refs, rule in (
            (["TEST-S", "TEST-C", "TEST-FOREIGN"], "action_references"),
            (["TEST-FAKE"], "action_references"),
            (["TEST-S", "TEST-OTHER"], "action_evidence_missing"),
            (["TEST-C", "TEST-C"], "action_references"),
        ):
            with self.subTest(refs=refs), self.assertRaisesRegex(OutputValidationError, rule):
                self.verify("CONFIRM_BILLING_QUANTITY", refs)

    def test_generic_manual_action_can_explicitly_request_evidence_without_citations(self):
        result = self.verify(REQUEST_ADDITIONAL_EVIDENCE, [])
        self.assertEqual(result["anomaly_findings"][0]["recommended_actions"][0]["action_code"],
                         REQUEST_ADDITIONAL_EVIDENCE)


class OptionalNoteProvider(MockProvider):
    def __init__(self, change):
        self.change = change

    def generate(self, language, payload):
        response = super().generate(language, payload)
        data = json.loads(response.text)
        self.change(data["anomaly_findings"])
        return LLMResponse(json.dumps(data), response.model)


class ReportContractTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(workspace_temp()))
        self.financial, self.reports = self.root / "financial", self.root / "analysis"
        write_reports(reconcile(load_data(ROOT / "data" / "sample")), self.financial)
        self.context = build_context(self.financial)

    def verify_stage(self, mode, change):
        calls = []

        def handler(request):
            payload = json.loads(json.loads(request.content)["input"])
            calls.append(payload)
            return reply(OptionalNoteProvider(change).generate(payload["language"], payload).text)

        args = ["--live", "--mode", mode, "--input-dir", str(self.financial), "--output-dir", str(self.reports)]
        with (
            patch.dict(os.environ, {**ENV, "LLM_MAX_RETRIES": "3"}, clear=True), local_transport(handler),
            redirect_stdout(io.StringIO()) as stdout, redirect_stderr(io.StringIO()) as stderr,
        ):
            rc = verify_cli(args)
        self.assertEqual(len(calls), 1)
        return rc, stdout.getvalue(), stderr.getvalue(), calls[0]

    def test_all_nine_engine_facts_are_rendered_in_both_languages(self):
        english = analyze(self.context, MockProvider(), "en")
        chinese = analyze(self.context, MockProvider(), "cn")
        self.assertEqual({item["anomaly_type"] for item in english["anomaly_findings"]}, set(RECOMMENDED_ACTIONS))
        self.assertEqual(len({item["explanation"] for item in english["anomaly_findings"]}), 9)
        for en, cn in zip(english["anomaly_findings"], chinese["anomaly_findings"], strict=True):
            with self.subTest(kind=en["anomaly_type"]):
                self.assertEqual(en["anomaly_id"], cn["anomaly_id"])
                self.assertNotEqual(en["explanation"], cn["explanation"])
                self.assertTrue(en["requires_human_review"] and cn["requires_human_review"])
                self.assertTrue(all(item["review_required"] for item in cn["recommended_actions"]))

    def test_financial_figures_and_unknowns_come_from_the_engine(self):
        report = analyze(self.context, MockProvider(), "en")
        for finding in report["anomaly_findings"]:
            source = self.context.findings[finding["anomaly_id"]]
            self.assertEqual(finding["engine_amounts"], source["amounts"])
            self.assertEqual(finding["engine_group_amounts"], source["group_amounts"])
        amount = next(item for item in report["anomaly_findings"] if item["anomaly_type"] == "UNDERPAYMENT")
        self.assertIn("CNY " + amount["engine_amounts"]["difference_amount"], amount["explanation"])
        unmatched = next(item for item in report["anomaly_findings"] if item["anomaly_type"] == "UNMATCHED_PAYMENT")
        self.assertIn("Expected Unknown", unmatched["explanation"])
        self.assertIsNone(unmatched["engine_amounts"]["expected_amount"])
        self.assertNotIn("CNY 0.00", unmatched["explanation"])

    def test_full_reproduces_sixth_finding_financial_number_as_optional_omission(self):
        def change(findings):
            findings[5]["optional_analysis"] = "Private regression sentinel CNY 123.45."

        rc, stdout, stderr, payload = self.verify_stage("full", change)
        self.assertEqual((rc, stderr), (0, ""))
        self.assertEqual(len(payload["findings"]), 9)
        status = json.loads(stdout)
        self.assertEqual(status["status"], "completed_with_omissions")
        self.assertEqual(status["core_validation"], "passed")
        self.assertEqual((status["finding_count"], status["validated_cause_count"], status["validated_action_count"]),
                         (9, 9, 9))
        self.assertEqual(status["omitted_note_count"], 1)
        self.assertEqual(status["warnings"], [{"path": "anomaly_findings[5].optional_analysis", "rule": "financial_numbers"}])
        self.assertFalse(status["reports_written"])
        self.assertNotIn("123.45", stdout)

    def test_report_omits_rejected_notes_preserves_valid_notes_and_saves_nine_findings(self):
        def change(findings):
            findings[5]["optional_analysis"] = "Private regression sentinel CNY 123.45."
            findings[0]["optional_analysis"] = "Review the provenance of the supplied supporting records."

        before = {name: (self.financial / name).read_bytes() for name in SOURCE_FILES}
        rc, stdout, stderr, _ = self.verify_stage("report", change)
        self.assertEqual(rc, 0, stderr)
        self.assertTrue(json.loads(stdout)["reports_written"])
        raw = (self.reports / "ai_analysis_en.json").read_text(encoding="utf-8")
        md = (self.reports / "ai_analysis_en.md").read_text(encoding="utf-8")
        report = json.loads(raw)
        self.assertEqual(report["report_schema_version"], "3.0")
        self.assertEqual(report["analysis_status"], "completed_with_omissions")
        self.assertEqual(report["warnings"], [{"path": "anomaly_findings[5].optional_analysis", "rule": "financial_numbers"}])
        self.assertEqual(len(report["anomaly_findings"]), 9)
        self.assertIsNone(report["anomaly_findings"][5]["optional_analysis"])
        self.assertEqual(report["anomaly_findings"][5]["optional_analysis_status"], "rejected")
        self.assertIn("omitted by validation", md)
        self.assertIn("Review the provenance", raw)
        self.assertIn("Review the provenance", md)
        self.assertNotIn("Private regression sentinel", raw + md)
        self.assertEqual(before, {name: (self.financial / name).read_bytes() for name in SOURCE_FILES})

    def test_single_accepts_absent_optional_text_without_a_warning(self):
        def change(findings):
            findings[0].pop("optional_analysis")

        rc, stdout, stderr, payload = self.verify_stage("single", change)
        self.assertEqual(rc, 0, stderr)
        self.assertEqual(len(payload["findings"]), 1)
        status = json.loads(stdout)
        self.assertEqual(status["validated_action_count"], 1)
        self.assertEqual(status["status"], "completed")
        self.assertEqual(status["omitted_note_count"], 0)

    def test_core_failure_does_not_publish_partial_success_even_with_bad_optional_text(self):
        def change(findings):
            findings[5]["optional_analysis"] = "CNY 123.45"
            findings[5]["recommended_actions"][0]["action_code"] = "EXECUTE_PAYMENT"

        rc, stdout, stderr, _ = self.verify_stage("report", change)
        self.assertEqual(rc, 1)
        self.assertEqual(stdout, "")
        self.assertIn("anomaly_findings[5].recommended_actions[0].action_code", stderr)
        self.assertIn("unknown_action", stderr)
        self.assertFalse(self.reports.exists())

    def test_old_explanation_cannot_override_the_deterministic_explanation(self):
        def change(findings):
            findings[5]["explanation"] = "CNY 123.45"

        with self.assertRaisesRegex(OutputValidationError, r"anomaly_findings\[5\].*unexpected field count: 1"):
            analyze(self.context, OptionalNoteProvider(change), "en")

    def test_optional_non_string_value_cannot_leak_into_either_report(self):
        def change(findings):
            findings[0]["optional_analysis"] = {"private": "invalid"}

        report = analyze(self.context, OptionalNoteProvider(change), "cn")
        self.assertEqual(report["analysis_status"], "completed_with_omissions")
        self.assertEqual(report["warnings"][0]["rule"], "narrative_size")
        self.assertIsNone(report["anomaly_findings"][0]["optional_analysis"])
        self.assertNotIn("private", json.dumps(report) + render_markdown(report))
