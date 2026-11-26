import io
import json
import os
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from scripts.verify_agent_live import accepted, main as verify_cli, verification_failures
from src.agent import render_answer, run_agent
from tests.test_agent import AgentFixture, ScriptedProvider, call, calls, plan, sdk_message, sdk_response
from tests.test_qwen_provider import ENV, KEY, local_transport


SCOPE = {"hospital_id": "SIM-H004", "settlement_period": "2026-05"}


class HospitalVerificationTests(AgentFixture, unittest.TestCase):
    def scripted(self, *turns):
        provider = ScriptedProvider(turns)
        provider.mode = "Live"
        return run_agent("Show the hospital settlement.", "en", provider, self.registry)

    def held_group(self):
        return calls(call("call_group", "get_hospital_reconciliation", SCOPE))

    def query_group(self):
        return self.scripted(self.held_group(), plan("E1"))

    def verify_with_simulated_qwen(self, citations):
        def handler(request):
            body = json.loads(request.content)
            history = body["input"]
            if len(history) == 1:
                return sdk_response(self.held_group().calls[0].input_item())
            source = json.loads(history[2]["output"])
            self.assertEqual(history[2]["call_id"], "call_group")
            self.assertEqual(source["ref"], "E1")
            anomaly_id = source["data"]["anomalies"][0]["anomaly_id"]
            self.assertEqual(anomaly_id, "ANOM-000006")
            if len(history) == 3:
                return sdk_response(call("call_detail", "get_anomaly_details", {"anomaly_id": anomaly_id}).input_item())
            self.assertEqual(history[4]["call_id"], "call_detail")
            self.assertEqual(json.loads(history[4]["output"])["data"]["anomaly_id"], anomaly_id)
            self.assertEqual(body["text"]["format"]["json_schema"]["schema"]["properties"]["citations"]["items"]["enum"],
                             ["E1", "E2"])
            return sdk_response(sdk_message(plan(*citations).answer_plan))

        with patch.dict(os.environ, ENV, clear=True), local_transport(handler), redirect_stdout(io.StringIO()) as output:
            code = verify_cli(["--live", "--scenario", "hospital", "--input-dir", str(self.financial)])
        return code, json.loads(output.getvalue())

    def test_hospital_accepts_extra_detail_and_supplies_all_required_fields_from_refs(self):
        code, report = self.verify_with_simulated_qwen(("E1", "E2"))
        self.assertEqual((code, report["verification"], report["verification_failures"]), (0, "PASS", []))
        self.assertEqual((report["model_requests"], report["tool_calls"]), (3, 2))
        first, detail = report["answer_sections"]
        self.assertEqual((first["ref"], detail["ref"], detail["tool"]), ("E1", "E2", "get_anomaly_details"))
        data = first["data"]
        self.assertEqual({key: data[key] for key in SCOPE}, SCOPE)
        self.assertEqual((data["settlement_status"], data["payment_bucket"]), ("REVIEW_REQUIRED", "HELD"))
        self.assertTrue(data["review_required"])
        self.assertEqual(data["anomaly_types"], ["CONTRACT_OVERLAP"])
        self.assertEqual(data["anomalies"][0]["anomaly_id"], "ANOM-000006")
        self.assertEqual((data["paid_amount"], data["eligible_paid_amount"], data["currency"]), ("10406.50", "10406.50", "CNY"))
        self.assertIsNone(data["expected_amount"])
        self.assertIsNone(data["difference_amount"])
        self.assertEqual(data, report["tool_trace"][0]["result"]["data"])
        self.assertEqual(detail["data"], report["tool_trace"][1]["result"]["data"])

    def test_unknown_amounts_are_rendered_in_both_languages_and_real_zero_is_preserved(self):
        held = self.query_group()
        self.assertIn("Expected amount · Not determinable", render_answer(held, "en"))
        self.assertIn("Difference amount · Not determinable", render_answer(held, "en"))
        self.assertIn("应收或合同预期 · 暂无法确定", render_answer(held, "cn"))
        self.assertIn("差额 · 暂无法确定", render_answer(held, "cn"))
        zero = self.scripted(calls(call("call_zero", "get_hospital_reconciliation", {
            "hospital_id": "SIM-H003", "settlement_period": "2026-04",
        })), plan("E1"))
        self.assertEqual(zero["answer_sections"][0]["data"]["difference_amount"], "0.00")
        self.assertIn("Difference amount · 0.00", render_answer(zero, "en"))

    def test_detail_alone_is_insufficient_for_verification_even_when_agent_answered(self):
        code, report = self.verify_with_simulated_qwen(("E2",))
        self.assertEqual((code, report["verification"], report["status"], report["error"]), (1, "FAIL", "answered", None))
        self.assertEqual([failure["code"] for failure in report["verification_failures"]], ["missing_evidence_reference"])
        self.assertNotIn(KEY, json.dumps(report))

    def test_legacy_citation_object_cannot_select_fields_from_another_hospital_result(self):
        code, report = self.verify_with_simulated_qwen(({"ref": "E1", "fields": ["manual_review_actions"]}, "E2"))
        self.assertEqual((code, report["verification"], report["answer_sections"]), (1, "FAIL", []))
        details = report["verification_failures"][0]["cause"]
        self.assertEqual((details["code"], details["path"], details["actual_type"]),
                         ("invalid_reference_type", "$.citations[0]", "object"))
        self.assertNotIn("manual_review_actions", json.dumps(details))

    def test_exact_hospital_and_settlement_period_are_required_independently(self):
        for field, wrong in (("hospital_id", "SIM-H003"), ("settlement_period", "2026-04")):
            with self.subTest(field=field):
                result = self.scripted(calls(call("call_other", "get_hospital_reconciliation", {**SCOPE, field: wrong})),
                                       plan("E1"))
                self.assertEqual(result["status"], "answered")
                self.assertEqual([failure["code"] for failure in verification_failures("hospital", result)],
                                 ["incorrect_hospital_scope"])

    def test_missing_fields_are_reported_by_name_instead_of_a_bare_failure(self):
        result = self.query_group()
        expected = {"hospital_id", "settlement_period", "expected_amount", "difference_amount", "anomalies"}
        for field in expected:
            del result["answer_sections"][0]["data"][field]
        self.assertFalse(accepted("hospital", result))
        failure, = verification_failures("hospital", result)
        self.assertEqual(failure["code"], "missing_required_answer_field")
        self.assertEqual(set(failure["fields"]), expected)

    def test_modified_amounts_fail_attestation_without_echoing_the_values(self):
        result = self.query_group()
        result["answer_sections"][0]["data"].update(expected_amount="0.00", difference_amount=KEY)
        failure, = verification_failures("hospital", result)
        self.assertEqual(failure["code"], "answer_evidence_mismatch")
        self.assertEqual(failure["fields"], ["expected_amount", "difference_amount"])
        self.assertNotIn(KEY, json.dumps(failure))

    def test_incomplete_hospital_evidence_cannot_supply_an_answer(self):
        execute = self.registry.execute

        def incomplete(tool, arguments):
            result = execute(tool, arguments)
            del result["data"]["expected_amount"]
            return result

        with patch.object(self.registry, "execute", side_effect=incomplete):
            result = self.query_group()
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["answer_sections"], [])
        self.assertEqual(result["error_details"]["code"], "missing_required_evidence")
        self.assertEqual(result["error_details"]["missing_fields"], ["expected_amount"])
        self.assertFalse(accepted("hospital", result))

    def test_unavailable_group_result_cannot_be_replaced_by_other_cited_evidence(self):
        result = self.scripted(
            calls(call("call_summary", "get_reconciliation_summary")),
            plan("E1"),
        )
        failure, = verification_failures("hospital", result)
        self.assertEqual(failure["code"], "missing_hospital_tool_result")
