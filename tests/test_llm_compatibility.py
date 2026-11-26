"""Offline coverage of bilingual hypotheses and staged verification."""

import io
import json
import os
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from scripts.verify_qwen_live import main as verify_cli
from src.context_builder import build_context
from src.data_loader import load_data
from src.llm_analyzer import analyze, render_markdown
from src.llm_client import MockProvider, create_provider
from src.output_validator import OutputValidationError, optional_analysis, validate_output
from src.hypothesis_catalog import CATALOG, eligible_hypotheses
from src.prompts import ANALYSIS_SCHEMA, instructions
from src.reconciliation import reconcile
from src.reporting import write_reports
from tests.fixtures import ROOT, workspace_temp
from tests.test_llm_client import response as openai_reply, transport_provider
from tests.test_qwen_provider import BASE, ENV, KEY, local_transport, reply as qwen_reply


def mock_answer(payload):
    return json.loads(MockProvider().generate(payload["language"], payload).text)


class HypothesisCompatibilityTests(unittest.TestCase):
    def payload(self, language):
        return {
            "language": language, "analysis_scope": "ANOMALY_ANALYSIS",
            "findings": [{
                "anomaly_id": "ANOM-X", "anomaly_type": "MISSING_CONTRACT", "evidence_references": ["TEST-S1"],
                "cause_options": eligible_hypotheses("MISSING_CONTRACT", {"service_record": ["TEST-S1"]}),
            }],
        }

    def check(self, language, selection):
        payload = self.payload(language)
        answer = mock_answer(payload)
        answer["anomaly_findings"][0]["possible_causes"] = [selection]
        return validate_output(json.dumps(answer), payload)

    def test_english_cause_selection_has_a_tentative_catalog_template(self):
        selection = {"cause_code": "MISSING_CONTRACT_RECORD", "evidence_references": ["TEST-S1"]}
        self.assertEqual(self.check("en", selection)["anomaly_findings"][0]["possible_causes"], [selection])
        self.assertEqual(
            CATALOG[selection["cause_code"]].describe("en"),
            "A possible cause is an applicable contract omitted from the supplied records. Further verification is required.",
        )

    def test_simplified_chinese_cause_selection_has_a_tentative_catalog_template(self):
        selection = {"cause_code": "MISSING_CONTRACT_RECORD", "evidence_references": ["TEST-S1"]}
        self.assertEqual(self.check("cn", selection)["anomaly_findings"][0]["possible_causes"], [selection])
        self.assertEqual(
            CATALOG[selection["cause_code"]].describe("cn"),
            "可能原因：提交的源记录遗漏了适用合同。具体原因仍需人工核实。",
        )

    def test_case_and_spacing_do_not_change_catalog_enum_validation(self):
        for code in ("missing_contract_record", " MISSING_CONTRACT_RECORD "):
            with self.subTest(code=code), self.assertRaisesRegex(OutputValidationError, "unknown_cause"):
                self.check("en", {"cause_code": code, "evidence_references": ["TEST-S1"]})

    def test_definitive_cause_strings_are_rejected_in_both_languages(self):
        for language, statement in (
            ("en", "Duplicate importing caused the discrepancy."),
            ("cn", "导入记录出错造成了差异。"),
        ):
            with self.subTest(language=language), self.assertRaisesRegex(OutputValidationError, "expected a JSON object"):
                self.check(language, statement)

    def test_cause_objects_cannot_supply_their_own_prose(self):
        for language, statement in (
            ("en", "May reflect a posting delay, but the cause was confirmed."),
            ("cn", "可能与入账延迟有关，但原因已确认。"),
        ):
            with self.subTest(language=language), self.assertRaisesRegex(OutputValidationError, "unexpected field count: 1"):
                self.check(language, {
                    "cause_code": "MISSING_CONTRACT_RECORD", "evidence_references": ["TEST-S1"],
                    "description": statement,
                })

    def test_prompt_schema_and_validator_require_catalog_objects(self):
        finding = ANALYSIS_SCHEMA["properties"]["anomaly_findings"]["items"]["properties"]
        schema = finding["possible_causes"]
        self.assertEqual((schema["items"]["type"], schema["minItems"], schema["maxItems"]), ("object", 1, 8))
        self.assertEqual(schema["items"]["properties"]["cause_code"]["enum"], list(CATALOG))
        self.assertNotIn("requires_human_review", finding)
        self.assertEqual(finding["priority"]["enum"], ["HIGH", "MEDIUM", "LOW"])
        for language in ("en", "cn"):
            prompt = instructions(language)
            self.assertIn("cause_options", prompt)
            self.assertIn("required_evidence", prompt)
            self.assertIn("INSUFFICIENT_EVIDENCE", prompt)
            self.check(language, {"cause_code": "INSUFFICIENT_EVIDENCE", "evidence_references": []})

    def test_text_rules_identify_field_and_category_without_echoing_content(self):
        for value, rule in (
            ("The amount due is zero.", "financial_numbers"),
            ("The cause was confirmed.", "unverified_conclusion"),
            ("The payment is overdue.", "unverified_conclusion"),
            ("Refer to https://private.example.", "plain_text"),
            ("Pay the invoice.", "unauthorized_operation"),
        ):
            with self.subTest(value=value):
                path = "anomaly_findings[0].optional_analysis"
                note, warning = optional_analysis(value, path)
                self.assertIsNone(note)
                self.assertEqual(warning, {"path": path, "rule": rule})
                self.assertNotIn(value, str(warning))

    def test_invalid_json_reports_position_without_echoing_credentials(self):
        with self.assertRaisesRegex(OutputValidationError, "not valid JSON at line 1, column") as failure:
            validate_output(f'{{"missing": {KEY}}}', self.payload("en"))
        self.assertNotIn(KEY, str(failure.exception))


class StagedLLMCompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(workspace_temp()))
        self.financial = self.root / "financial"
        self.output = self.root / "qwen-verification"
        write_reports(reconcile(load_data(ROOT / "data" / "sample")), self.financial)
        self.context = build_context(self.financial)

    def test_bilingual_mock_validates_all_nine_sample_findings(self):
        for language in ("en", "cn"):
            with self.subTest(language=language):
                report = analyze(self.context, MockProvider(), language)
                self.assertEqual(report["run_mode"], "Mock")
                self.assertEqual(len(report["anomaly_findings"]), 9)
                self.assertTrue(all(item["requires_human_review"] is True for item in report["anomaly_findings"]))

    def test_openai_validates_multiple_findings_with_catalog_objects(self):
        def handler(request):
            body = json.loads(request.content)
            self.assertEqual(body["text"]["format"]["schema"], ANALYSIS_SCHEMA)
            payload = json.loads(body["input"])
            self.assertEqual(body["instructions"], instructions("en"))
            self.assertEqual(len(payload["findings"]), 9)
            return openai_reply(content=json.dumps(mock_answer(payload)))

        provider, substitute = transport_provider(handler)
        with substitute:
            report = analyze(self.context, provider, "en")
        self.assertEqual(report["provider"], "openai")
        self.assertEqual(report["run_mode"], "Live")
        self.assertEqual(set(self.context.findings), {item["anomaly_id"] for item in report["anomaly_findings"]})
        self.assertIn("Possible causes (unverified)", render_markdown(report))

    def run_stage(self, mode, handler, language="cn"):
        arguments = [
            "--live", "--mode", mode, "--input-dir", str(self.financial),
            "--output-dir", str(self.output), "--language", language,
        ]
        with (
            patch.dict(os.environ, ENV, clear=True), local_transport(handler),
            redirect_stdout(io.StringIO()) as stdout, redirect_stderr(io.StringIO()) as stderr,
        ):
            code = verify_cli(arguments)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_explicit_connection_reports_scope_without_financial_input(self):
        def handler(request):
            self.assertEqual(json.loads(request.content)["input"], "Connection check. Reply only with OK.")
            return qwen_reply()

        code, output, errors = self.run_stage("connection", handler)
        self.assertEqual(code, 0, errors)
        metadata = json.loads(output)
        self.assertEqual(metadata["verification_scope"], "connection")
        self.assertEqual(metadata["finding_count"], 0)
        self.assertFalse(metadata["reports_written"])

    def test_single_stage_sends_and_validates_only_first_finding(self):
        def handler(request):
            payload = json.loads(json.loads(request.content)["input"])
            self.assertEqual([item["anomaly_id"] for item in payload["findings"]], [next(iter(self.context.findings))])
            return qwen_reply(json.dumps(mock_answer(payload)))

        code, output, errors = self.run_stage("single", handler)
        self.assertEqual(code, 0, errors)
        self.assertEqual(json.loads(output)["finding_count"], 1)
        self.assertEqual(json.loads(output)["validated_cause_count"], 1)
        self.assertEqual(json.loads(output)["verification_scope"], "single")
        self.assertFalse(self.output.exists())

    def test_full_stage_validates_nine_findings_without_writing_reports(self):
        def handler(request):
            body = json.loads(request.content)
            payload = json.loads(body["input"])
            self.assertEqual(body["text"]["format"]["json_schema"]["schema"], ANALYSIS_SCHEMA)
            self.assertEqual(body["instructions"], instructions("cn"))
            self.assertEqual(len(payload["findings"]), 9)
            return qwen_reply(json.dumps(mock_answer(payload)))

        code, output, errors = self.run_stage("full", handler)
        self.assertEqual(code, 0, errors)
        self.assertEqual(json.loads(output)["finding_count"], 9)
        self.assertEqual(json.loads(output)["validated_cause_count"], 9)
        self.assertFalse(self.output.exists())

    def test_report_stage_writes_validated_artifacts_and_preserves_unknown_amounts(self):
        def handler(request):
            payload = json.loads(json.loads(request.content)["input"])
            return qwen_reply(json.dumps(mock_answer(payload)))

        code, output, errors = self.run_stage("report", handler)
        self.assertEqual(code, 0, errors)
        self.assertTrue(json.loads(output)["reports_written"])
        report_path = self.output / "ai_analysis_cn.json"
        report = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertEqual(set(self.context.findings), {item["anomaly_id"] for item in report["anomaly_findings"]})
        missing = next(item for item in report["anomaly_findings"] if item["anomaly_type"] == "MISSING_CONTRACT")
        self.assertIsNone(missing["engine_group_amounts"]["expected_amount"])
        self.assertEqual(report["financial_summary"]["net_difference"], self.context.summary["net_difference"])
        self.assertIn("可能原因（待核实）", (self.output / "ai_analysis_cn.md").read_text(encoding="utf-8"))

    def test_report_stage_rejects_unsafe_results_without_printing_raw_content(self):
        def handler(request):
            payload = json.loads(json.loads(request.content)["input"])
            answer = mock_answer(payload)
            answer["anomaly_findings"][0]["possible_causes"] = ["The private placeholder caused this finding."]
            return qwen_reply(json.dumps(answer))

        code, output, errors = self.run_stage("report", handler, "en")
        self.assertEqual(code, 1)
        self.assertEqual(output, "")
        self.assertIn("anomaly_findings[0].possible_causes[0]", errors)
        self.assertIn("expected a JSON object", errors)
        for value in (KEY, BASE, "private placeholder"):
            self.assertNotIn(value, errors)
        self.assertFalse(self.output.exists())
