import json
import unittest

from src.llm_client import MockProvider
from src.hypothesis_catalog import eligible_hypotheses
from src.output_validator import OutputValidationError, _bounded_list, optional_analysis, validate_output
from src.prompts import ACTION_SCHEMA, ANALYSIS_SCHEMA, CAUSE_SCHEMA, FINDING_SCHEMA, instructions


PAYLOAD = {
    "language": "en", "analysis_scope": "ANOMALY_ANALYSIS",
    "findings": [
        {"anomaly_id": "ANOM-X", "anomaly_type": "MISSING_CONTRACT",
         "evidence_references": ["TEST-S1"], "available_group_amounts": {"expected_amount": False}},
        {"anomaly_id": "ANOM-Y", "anomaly_type": "MISSING_PAYMENT", "evidence_references": ["TEST-S2"],
         "cause_options": eligible_hypotheses("MISSING_PAYMENT", {"service_record": ["TEST-S2"]})},
    ],
}


class OutputValidatorTests(unittest.TestCase):
    def setUp(self):
        self.result = json.loads(MockProvider().generate("en", PAYLOAD).text)

    def verify(self, result=None, payload=PAYLOAD):
        return validate_output(json.dumps(self.result if result is None else result), payload)

    def test_valid_shape_preserves_type_references_and_review(self):
        result = self.verify()
        self.assertEqual(result["anomaly_findings"][0]["evidence_references"], ["TEST-S1"])
        self.assertEqual(result["anomaly_findings"][0]["anomaly_type"], "MISSING_CONTRACT")
        self.assertTrue(all("requires_human_review" not in item for item in result["anomaly_findings"]))

    def test_invalid_json_and_duplicate_json_keys_are_rejected(self):
        for raw in ("unstructured output", "{", '{"executive_summary":"a","executive_summary":"b"}'):
            with self.subTest(raw=raw), self.assertRaises(OutputValidationError):
                validate_output(raw, PAYLOAD)

    def test_unknown_anomaly_id_is_rejected(self):
        self.result["anomaly_findings"][0]["anomaly_id"] = "MADE-UP"
        with self.assertRaisesRegex(OutputValidationError, "unknown or repeated anomaly ID"):
            self.verify()

    def test_missing_or_duplicate_findings_are_rejected(self):
        missing = {**self.result, "anomaly_findings": self.result["anomaly_findings"][:1]}
        with self.assertRaisesRegex(OutputValidationError, "omitted"):
            self.verify(missing)
        self.result["anomaly_findings"][1] = self.result["anomaly_findings"][0]
        with self.assertRaisesRegex(OutputValidationError, "repeated anomaly ID"):
            self.verify()

    def test_record_ids_must_belong_to_the_finding(self):
        for refs in (["UNSUPPORTED"], ["TEST-S2"], []):
            with self.subTest(refs=refs):
                self.result["anomaly_findings"][0]["evidence_references"] = refs
                with self.assertRaisesRegex(OutputValidationError, "evidence references"):
                    self.verify()

    def test_wrong_anomaly_type_is_rejected(self):
        self.result["anomaly_findings"][0]["anomaly_type"] = "PRICE_MISMATCH"
        with self.assertRaisesRegex(OutputValidationError, "does not match"):
            self.verify()

    def test_missing_or_added_fields_are_rejected(self):
        causes = self.result["anomaly_findings"][0].pop("possible_causes")
        with self.assertRaisesRegex(OutputValidationError, "missing or unexpected fields"):
            self.verify()
        self.result["anomaly_findings"][0]["possible_causes"] = causes
        self.result["financial_summary"] = {"expected_amount": "1.00"}
        with self.assertRaisesRegex(OutputValidationError, "missing or unexpected fields"):
            self.verify()

    def test_invented_amounts_and_unknown_as_zero_are_rejected(self):
        for claim in (
            "The amount was CNY 42.50.", "Receivable is zero.", "There is no variance.",
            "The balance is ４２．５０.", "The amount was fifty yuan.", "There are eight held groups.",
            "应收金额为零。", "差额为三十元。",
        ):
            with self.subTest(statement=claim):
                text, warning = optional_analysis(claim, "anomaly_findings[0].optional_analysis")
                self.assertIsNone(text)
                self.assertIn(warning["rule"], ("financial_numbers", "unverified_conclusion"))

    def test_definitive_cause_overdue_and_operations_are_rejected(self):
        finding = self.result["anomaly_findings"][0]
        causes = finding["possible_causes"]
        finding["possible_causes"] = ["A contract owner caused the discrepancy."]
        with self.assertRaisesRegex(OutputValidationError, "possible_causes.*expected a JSON object"):
            self.verify()
        finding["possible_causes"] = causes
        for action in ("Approve the payment.", "Update the ledger.", "The payment is late.", "立即付款。"):
            with self.subTest(action=action):
                finding["recommended_actions"] = [action]
                with self.assertRaisesRegex(OutputValidationError, "recommended_actions.*expected a JSON object"):
                    self.verify()
                self.assertIsNone(optional_analysis(action, "optional_analysis")[0])

    def test_review_flag_cannot_be_removed(self):
        self.result["anomaly_findings"][0]["requires_human_review"] = False
        with self.assertRaisesRegex(OutputValidationError, "unexpected field count: 1"):
            self.verify()

    def test_provisional_model_cannot_inject_an_executive_summary(self):
        self.result["executive_summary"] = "A fabricated summary."
        with self.assertRaisesRegex(OutputValidationError, "unexpected field count: 1"):
            self.verify(payload={**PAYLOAD, "analysis_scope": "REVIEW_ONLY"})

    def _selection_fields(self):
        finding = self.result["anomaly_findings"][1]
        for name in ("possible_causes", "recommended_actions"):
            yield finding, name, rf"anomaly_findings\[1\]\.{name}"

    def test_empty_selection_arrays_are_rejected_at_each_field(self):
        for item, name, path in self._selection_fields():
            with self.subTest(field=name):
                original = item[name]
                item[name] = []
                with self.assertRaisesRegex(OutputValidationError, rf"{path}: .*1 to 8 entries, got 0 entries"):
                    self.verify()
                item[name] = original

    def test_selection_arrays_accept_one_entry(self):
        result = self.verify()
        for item, name, _ in self._selection_fields():
            self.assertEqual(len(item[name]), 1)
        self.assertEqual(result, self.result)

    def test_structural_array_bound_accepts_eight_entries_without_truncating(self):
        original = list(range(8))
        entries = original.copy()
        _bounded_list(entries, "possible_causes")
        self.assertEqual(entries, original)

    def test_selection_arrays_over_eight_entries_report_count_and_path(self):
        for item, name, path in self._selection_fields():
            with self.subTest(field=name):
                original = item[name]
                item[name] = original * 9
                with self.assertRaisesRegex(OutputValidationError, rf"{path}: .*1 to 8 entries, got 9 entries"):
                    self.verify()
                item[name] = original

    def test_incorrect_array_types_report_path_without_echoing_values(self):
        for item, name, path in self._selection_fields():
            original = item[name]
            for value in ("private-test-value", {"private-test-value": "x"}, None, 1):
                with self.subTest(field=name, kind=type(value).__name__):
                    item[name] = value
                    with self.assertRaisesRegex(
                        OutputValidationError, rf"{path}: .*1 to 8 entries, got {type(value).__name__}"
                    ) as failure:
                        self.verify()
                    self.assertNotIn("private-test-value", str(failure.exception))
            item[name] = original

    def test_invalid_narrative_item_reports_its_index(self):
        finding = self.result["anomaly_findings"][1]
        original = finding["possible_causes"][0]
        for value in ("  ", 12):
            with self.subTest(value=value):
                finding["possible_causes"] = [original, value]
                with self.assertRaisesRegex(OutputValidationError, r"anomaly_findings\[1\]\.possible_causes\[1\]"):
                    self.verify()

    def test_prompt_and_schema_match_selection_bounds_only(self):
        fields = ANALYSIS_SCHEMA["properties"]
        finding = FINDING_SCHEMA["properties"]
        for spec in (finding["possible_causes"], finding["recommended_actions"]):
            self.assertEqual((spec["type"], spec["minItems"], spec["maxItems"]), ("array", 1, 8))
            self.assertEqual(spec["items"]["type"], "object")
        self.assertEqual(finding["optional_analysis"]["type"], ["string", "null"])
        for spec in (fields["anomaly_findings"], finding["evidence_references"]):
            self.assertNotIn("minItems", spec)
            self.assertNotIn("maxItems", spec)
        for language in ("en", "cn"):
            prompt = instructions(language)
            self.assertIn("1 to 8 possible_causes and recommended_actions objects per finding", prompt)
            self.assertIn("Prefer null for optional_analysis", prompt)

    def test_catalog_code_type_and_enum_diagnostics_are_distinct(self):
        finding = self.result["anomaly_findings"][1]
        cause = finding["possible_causes"][0]
        valid = cause["cause_code"]
        self.assertEqual(self.verify()["anomaly_findings"][1]["possible_causes"], [cause])
        allowed = tuple(CAUSE_SCHEMA["properties"]["cause_code"]["enum"])
        for value, constraint, kind, length in (
            ("private-unknown-code", "enum", "string", len("private-unknown-code")),
            (valid.lower(), "enum", "string", len(valid)),
            ("", "enum", "string", 0),
            (None, "type", "null", None),
            (12, "type", "integer", None),
            ({"private-unknown-code": True}, "type", "object", None),
        ):
            with self.subTest(constraint=constraint, kind=kind, length=length):
                cause["cause_code"] = value
                with self.assertRaises(OutputValidationError) as failure:
                    self.verify()
                error = failure.exception
                self.assertEqual((error.code, error.path, error.constraint),
                                 ("schema_validation_failed", "anomaly_findings[1].possible_causes[0].cause_code", constraint))
                self.assertEqual((error.expected_type, error.actual_type, error.actual_string_length, error.allowed_values),
                                 ("string", kind, length, allowed))
                self.assertNotIn("private-unknown-code", str(error))

    def test_second_cause_distinguishes_catalog_membership_and_business_rules(self):
        source = {
            "anomaly_id": "ANOM-P", "anomaly_type": "UNDERPAYMENT", "evidence_references": ["TEST-P1"],
            "cause_options": eligible_hypotheses("UNDERPAYMENT", {"payment_record": ["TEST-P1"]}),
        }
        payload = {**PAYLOAD, "findings": [source]}
        response = json.loads(MockProvider().generate("en", payload).text)
        causes = response["anomaly_findings"][0]["possible_causes"]
        causes.append({"cause_code": "PARTIAL_PAYMENT", "evidence_references": ["TEST-P1"]})
        self.assertEqual(self.verify(response, payload), response)
        for code, expected_code, constraint in (
            ("PRIVATE_UNKNOWN_CODE", "schema_validation_failed", "enum"),
            (causes[0]["cause_code"], "business_validation_failed", "distinct_codes"),
            ("INSUFFICIENT_EVIDENCE", "business_validation_failed", "exclusive_fallback"),
            ("REPORTING_DELAY", "evidence_validation_failed", "applicable_code"),
        ):
            with self.subTest(constraint=constraint):
                causes[1]["cause_code"] = code
                with self.assertRaises(OutputValidationError) as failure:
                    self.verify(response, payload)
                error = failure.exception
                self.assertEqual((error.code, error.path, error.constraint),
                                 (expected_code, "anomaly_findings[0].possible_causes[1].cause_code", constraint))

    def test_non_cause_fields_distinguish_json_structure_and_evidence_rules(self):
        for field, value, category, constraint, suffix in (
            ("anomaly_type", False, "schema_validation_failed", "type", ".anomaly_type"),
            ("anomaly_type", "UNDERPAYMENT", "evidence_validation_failed", "matches_engine_anomaly_type", ".anomaly_type"),
            ("evidence_references", [42], "schema_validation_failed", "type", ".evidence_references[0]"),
            ("evidence_references", ["TEST-S2"], "evidence_validation_failed", "scoped_distinct_references", ".evidence_references"),
            ("recommended_actions", [], "schema_validation_failed", "minItems", ".recommended_actions"),
            ("recommended_actions", [{}], "schema_validation_failed", "required", ".recommended_actions[0]"),
            ("settlement_status", "MATCHED", "schema_validation_failed", "additionalProperties", ""),
        ):
            finding = {**self.result["anomaly_findings"][0], field: value}
            with self.subTest(field=field, constraint=constraint), self.assertRaises(OutputValidationError) as failure:
                self.verify({"anomaly_findings": [finding, self.result["anomaly_findings"][1]]})
            error = failure.exception
            self.assertEqual((error.code, error.path, error.constraint), (category, "anomaly_findings[0]" + suffix, constraint))

    def test_prompt_schema_and_validator_share_enum_fields_and_selection_rules(self):
        for language in ("en", "cn"):
            prompt = instructions(language)
            for schema in (FINDING_SCHEMA, CAUSE_SCHEMA, ACTION_SCHEMA):
                self.assertIn(", ".join(schema["required"]), prompt)
            priorities = FINDING_SCHEMA["properties"]["priority"]["enum"]
            self.assertIn(", ".join(priorities), prompt)
            for kind, field, schema in (("cause", "possible_causes", CAUSE_SCHEMA),
                                        ("action", "recommended_actions", ACTION_SCHEMA)):
                code_field = f"{kind}_code"
                self.assertIn(f"Copy {code_field} as a JSON string from an exact key of this finding's {kind}_options", prompt)
                item = self.result["anomaly_findings"][1][field][0]
                original = item[code_field]
                item[code_field] = "NOT_A_CATALOG_CODE"
                with self.assertRaises(OutputValidationError) as failure:
                    self.verify()
                self.assertEqual(failure.exception.allowed_values, tuple(schema["properties"][code_field]["enum"]))
                item[code_field] = original
            self.assertIn("verbatim and case-sensitive in every language", prompt)
