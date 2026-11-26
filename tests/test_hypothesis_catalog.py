"""Independent tests of the structured hypothesis contract and its evidence gates."""

import json
import unittest
from pathlib import Path

from src.anomaly_detector import RECOMMENDED_ACTIONS
from src.context_builder import SOURCE_FILES, build_context
from src.data_loader import load_data
from src.hypothesis_catalog import CATALOG, INSUFFICIENT_EVIDENCE, eligible_hypotheses
from src.llm_analyzer import analyze, write_analysis
from src.llm_client import MockProvider
from src.output_validator import OutputValidationError, validate_output
from src.reconciliation import reconcile
from src.reporting import write_reports
from tests.fixtures import ROOT, load_fixture, payment, service, workspace_temp


class HypothesisSelectionTests(unittest.TestCase):
    def setUp(self):
        self.source = {
            "anomaly_id": "TEST-A",
            "anomaly_type": "PRICE_MISMATCH",
            "evidence_references": ["TEST-S", "TEST-C", "TEST-OTHER"],
            "cause_options": eligible_hypotheses(
                "PRICE_MISMATCH", {"service_record": ["TEST-S"], "matched_contract": ["TEST-C"]},
            ),
        }
        self.payload = {"language": "en", "analysis_scope": "ANOMALY_ANALYSIS", "findings": [self.source]}
        self.response = json.loads(MockProvider().generate("en", self.payload).text)

    def verify(self, *causes):
        self.response["anomaly_findings"][0]["possible_causes"] = list(causes)
        return validate_output(json.dumps(self.response), self.payload)

    def test_valid_code_preserves_selected_evidence(self):
        cause = {"cause_code": "INCORRECT_CONTRACT_PRICE", "evidence_references": ["TEST-C", "TEST-S"]}
        result = self.verify(cause)
        self.assertEqual(result["anomaly_findings"][0]["possible_causes"], [cause])

    def test_unknown_code_is_rejected_without_echoing_value(self):
        with self.assertRaisesRegex(OutputValidationError, r"possible_causes\[0\]\.cause_code.*unknown_cause") as error:
            self.verify({"cause_code": "UNTRUSTED_TEST_VALUE", "evidence_references": []})
        self.assertNotIn("UNTRUSTED_TEST_VALUE", str(error.exception))

    def test_existing_code_for_another_anomaly_is_rejected(self):
        with self.assertRaisesRegex(OutputValidationError, "cause_type"):
            self.verify({"cause_code": "REPORTING_DELAY", "evidence_references": ["TEST-S"]})

    def test_evidence_omission_or_wrong_role_does_not_support_a_cause(self):
        for refs in ([], ["TEST-S"], ["TEST-C"], ["TEST-S", "TEST-OTHER"]):
            with self.subTest(refs=refs), self.assertRaisesRegex(OutputValidationError, "cause_evidence_missing"):
                self.verify({"cause_code": "INCORRECT_CONTRACT_PRICE", "evidence_references": refs})

    def test_foreign_evidence_is_rejected_even_if_present_in_another_finding(self):
        foreign = {
            "anomaly_id": "TEST-B", "anomaly_type": "MISSING_CONTRACT",
            "evidence_references": ["TEST-FOREIGN"],
        }
        self.payload["findings"].append(foreign)
        self.response = json.loads(MockProvider().generate("en", self.payload).text)
        for refs in (["TEST-S", "TEST-C", "TEST-FOREIGN"], ["TEST-X"], ["TEST-S", "TEST-S"]):
            with self.subTest(refs=refs), self.assertRaisesRegex(OutputValidationError, "cause_references"):
                self.verify({"cause_code": "INCORRECT_CONTRACT_PRICE", "evidence_references": refs})

    def test_cause_evidence_must_also_be_cited_in_the_finding(self):
        self.response["anomaly_findings"][0]["evidence_references"] = ["TEST-S"]
        with self.assertRaisesRegex(OutputValidationError, "cause_references"):
            self.verify({"cause_code": "INCORRECT_CONTRACT_PRICE", "evidence_references": ["TEST-S", "TEST-C"]})

    def test_specific_cause_is_rejected_when_source_cannot_offer_it(self):
        self.source["cause_options"] = eligible_hypotheses("PRICE_MISMATCH", {"service_record": ["TEST-S"]})
        with self.assertRaisesRegex(OutputValidationError, "cause_unavailable"):
            self.verify({"cause_code": "INCORRECT_CONTRACT_PRICE", "evidence_references": ["TEST-S"]})

    def test_insufficient_evidence_is_an_explicit_standalone_selection(self):
        fallback = {"cause_code": INSUFFICIENT_EVIDENCE, "evidence_references": []}
        result = self.verify(fallback)
        self.assertEqual(result["anomaly_findings"][0]["possible_causes"], [fallback])
        with self.assertRaisesRegex(OutputValidationError, "cause_selection"):
            self.verify(fallback, {"cause_code": "INCORRECT_CONTRACT_PRICE", "evidence_references": ["TEST-S", "TEST-C"]})

    def test_missing_cause_is_not_filled_in(self):
        with self.assertRaisesRegex(OutputValidationError, r"possible_causes: .*got 0 entries"):
            self.verify()

    def test_duplicate_cause_selection_is_rejected(self):
        cause = {"cause_code": "INCORRECT_CONTRACT_PRICE", "evidence_references": ["TEST-S", "TEST-C"]}
        with self.assertRaisesRegex(OutputValidationError, "cause_selection"):
            self.verify(cause, cause)

    def test_catalog_covers_nine_anomalies_and_all_descriptions_require_review(self):
        self.assertEqual(set().union(
            *(set(item.applicable_anomaly_types) for item in CATALOG.values() if item.required_evidence)
        ), set(RECOMMENDED_ACTIONS))
        for code, entry in CATALOG.items():
            self.assertEqual(entry.cause_code, code)
            self.assertIs(entry.review_required, True)
            self.assertIn("Further verification is required", entry.describe("en"))
            self.assertIn("人工核实", entry.describe("cn"))
        self.assertIn("insufficient", CATALOG[INSUFFICIENT_EVIDENCE].describe("en"))
        self.assertIn("证据不足", CATALOG[INSUFFICIENT_EVIDENCE].describe("cn"))


class HypothesisReportTests(unittest.TestCase):
    def setUp(self):
        self.directory = Path(self.enterContext(workspace_temp()))
        self.financial = self.directory / "financial"

    def test_conflicting_payment_evidence_does_not_offer_duplicate_import(self):
        source = load_fixture(payments=[payment(), payment(payment_id="P2", payment_amount="0.31")])
        write_reports(reconcile(source), self.financial)
        context = build_context(self.financial)
        for language in ("en", "cn"):
            item = context.model_input(language)["findings"][0]
            self.assertEqual(item["payment_reference_resolution"], "UNRESOLVED_REFERENCE")
            self.assertEqual(set(item["cause_options"]), {INSUFFICIENT_EVIDENCE})
            cause = analyze(context, MockProvider(), language)["anomaly_findings"][0]["possible_causes"][0]
            self.assertEqual(cause["cause_code"], INSUFFICIENT_EVIDENCE)
            self.assertEqual(cause["evidence_references"], [])
            self.assertEqual(cause["description"], CATALOG[INSUFFICIENT_EVIDENCE].describe(language))
            self.assertTrue(cause["review_required"])

    def test_aliases_are_resolved_after_valid_cause_selection(self):
        raw_id = "Source identifier with spaces"
        write_reports(reconcile(load_fixture(services=[service(service_id=raw_id)])), self.financial)
        context = build_context(self.financial)
        item = context.model_input("en")["findings"][0]
        self.assertNotIn(raw_id, json.dumps(item))
        self.assertEqual(item["cause_options"]["MISSING_CONTRACT_RECORD"]["required_evidence"][0]["references"],
                         ["[REF-1]"])
        for language in ("en", "cn"):
            result = analyze(context, MockProvider(), language)
            cause = result["anomaly_findings"][0]["possible_causes"][0]
            self.assertEqual(cause["evidence_references"], [raw_id])
            self.assertEqual(cause["description"], CATALOG[cause["cause_code"]].describe(language))
            self.assertIs(cause["review_required"], True)

    def test_overlap_requires_both_candidates_and_reports_never_change_financial_files(self):
        write_reports(reconcile(load_data(ROOT / "data" / "sample")), self.financial)
        before = {name: (self.financial / name).read_bytes() for name in SOURCE_FILES}
        context = build_context(self.financial)
        payload = context.model_input("en")
        overlap = next(item for item in payload["findings"] if item["anomaly_type"] == "CONTRACT_OVERLAP")
        rule, = overlap["cause_options"]["CONTRACT_VERSION_CONFLICT"]["required_evidence"]
        self.assertEqual(rule["minimum"], 2)
        self.assertEqual(len(rule["references"]), 2)
        answer = json.loads(MockProvider().generate("en", payload).text)
        finding = next(item for item in answer["anomaly_findings"] if item["anomaly_id"] == overlap["anomaly_id"])
        finding["possible_causes"][0]["evidence_references"].pop()
        with self.assertRaisesRegex(OutputValidationError, "cause_evidence_missing"):
            validate_output(json.dumps(answer), payload)

        report = analyze(context, MockProvider(), "cn")
        write_analysis(report, self.directory / "analysis")
        self.assertEqual(report["financial_summary"]["net_difference"], context.summary["net_difference"])
        for finding in report["anomaly_findings"]:
            self.assertEqual(finding["engine_amounts"], context.findings[finding["anomaly_id"]]["amounts"])
            self.assertTrue(all(cause["review_required"] for cause in finding["possible_causes"]))
        self.assertEqual(before, {name: (self.financial / name).read_bytes() for name in SOURCE_FILES})
