import io
import json
import os
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

import httpx

from scripts.verify_agent_live import main as verify_cli
from src.agent import QwenAgentProvider, run_agent
from src.qwen_provider import QwenSettings
from src.tool_registry import KNOWLEDGE_TOOL, TOOLS
from tests.fixtures import ROOT
from tests.test_agent import AgentFixture, call, plan, sdk_message, sdk_response
from tests.test_qwen_provider import BASE, ENV, KEY, local_transport


SUMMARY_PLAN = plan("E1").answer_plan
PRIVATE_TEXT = "private-response-sentinel"


class AgentJSONTests(AgentFixture, unittest.TestCase):
    def summary(self, final_response, *, verify=False):
        requests = []

        def handler(request):
            self.assertEqual(str(request.url), BASE + "/responses")
            requests.append(json.loads(request.content))
            if len(requests) == 1:
                return sdk_response(call("call_summary", "get_reconciliation_summary").input_item())
            self.assertEqual(len(requests), 2, "Final output must not trigger any additional requests")
            return final_response

        with local_transport(handler):
            if verify:
                with patch.dict(os.environ, ENV, clear=True), redirect_stdout(io.StringIO()) as stdout:
                    code = verify_cli(["--live", "--scenario", "summary", "--input-dir", str(self.financial)])
                result = json.loads(stdout.getvalue())
                self.assertEqual(code, 0 if result["verification"] == "PASS" else 1)
            else:
                # Agent calls must ignore a configured retry count.
                settings = QwenSettings.from_env({**ENV, "LLM_MAX_RETRIES": "5"})
                result = run_agent("Show comparable net difference and held groups.", "en",
                                   QwenAgentProvider(settings), self.registry)
        self.assertEqual((len(requests), result["model_requests"], result["tool_calls"]), (2, 2, 1))
        self.assertEqual(result["tool_trace"][0]["result"]["ref"], "E1")
        return result, requests

    def assert_failed(self, response, error_code, stage="final_answer"):
        result, _ = self.summary(response)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["run_mode"], "Live")
        self.assertEqual(result["answer_sections"], [])
        details = result["error_details"]
        self.assertEqual((details["code"], details["stage"], details["model_request"]), (error_code, stage, 2))
        output = json.dumps(result)
        for private in (PRIVATE_TEXT, KEY, BASE):
            self.assertNotIn(private, output)
        return details

    def test_summary_uses_strict_schema_and_auto_tools_on_both_http_requests(self):
        result, requests = self.summary(sdk_response(sdk_message(SUMMARY_PLAN)), verify=True)
        self.assertEqual((result["verification"], result["verification_failures"], result["error_details"]), ("PASS", [], None))
        self.assertEqual(result["answer_sections"][0]["data"]["net_difference"], "9568.30")
        self.assertTrue(result["requires_human_review"])
        for index, body in enumerate(requests):
            self.assertEqual(body["tool_choice"], "auto")
            self.assertEqual([tool["name"] for tool in body["tools"]], [*TOOLS, KNOWLEDGE_TOOL])
            self.assertEqual(body["max_output_tokens"], 1024)
            self.assertFalse(body["store"])
            self.assertNotIn("response_format", body)
            self.assertNotIn("previous_response_id", body)
            fmt = body["text"]["format"]
            self.assertEqual(set(fmt), {"type", "json_schema"})
            self.assertEqual(fmt["type"], "json_schema")
            config = fmt["json_schema"]
            self.assertEqual(config["name"], "agent_answer")
            self.assertIs(config["strict"], True)
            schema = config["schema"]
            self.assertEqual(set(schema["required"]), {"status", "citations"})
            self.assertFalse(schema["additionalProperties"])
            statuses = ["answered", "insufficient_evidence", "refused"]
            self.assertEqual(schema["properties"]["status"]["enum"], statuses if index else statuses[1:])
            citations = schema["properties"]["citations"]
            self.assertEqual(citations["maxItems"], index)
            self.assertEqual(citations["items"], {"type": "string", "enum": ["E1"]} if index else {"type": "string"})
            self.assertNotIn("uniqueItems", citations)
            if index:
                self.assertEqual(schema["then"]["properties"]["citations"], {"minItems": 1})
                self.assertEqual(schema["else"]["properties"]["citations"], {"maxItems": 0})
        previous, output = requests[1]["input"][1:]
        self.assertEqual((previous["type"], output["type"]), ("function_call", "function_call_output"))
        self.assertEqual(previous["call_id"], output["call_id"])
        self.assertEqual(json.loads(output["output"])["ref"], "E1")

    def test_extracts_ordered_output_text_parts_without_using_reasoning(self):
        message = sdk_message(SUMMARY_PLAN[:25])
        message["content"].extend(sdk_message(SUMMARY_PLAN[25:])["content"])
        reasoning = {"type": "reasoning", "id": "rs_test", "summary": [
            {"type": "summary_text", "text": PRIVATE_TEXT},
        ]}
        result, _ = self.summary(sdk_response(reasoning, message))
        self.assertEqual(result["status"], "answered")
        self.assertNotIn(PRIVATE_TEXT, json.dumps(result))

    def test_rejects_malformed_json_and_wrappers_with_safe_location(self):
        for text in ('{"' + PRIVATE_TEXT, "```json\n" + SUMMARY_PLAN + "\n```", SUMMARY_PLAN + "\n" + PRIVATE_TEXT):
            with self.subTest(text=text):
                details = self.assert_failed(sdk_response(sdk_message(text)), "invalid_json")
                self.assertGreaterEqual(details["line"], 1)
                self.assertGreaterEqual(details["column"], 1)

    def test_rejects_duplicate_keys_at_root_and_nested_levels(self):
        for text in (
            '{"status":"answered","status":"refused","citations":[]}',
            '{"status":"answered","citations":[{"ref":"E1","ref":"E2","fields":["net_difference"]}]}',
        ):
            with self.subTest(text=text):
                self.assert_failed(sdk_response(sdk_message(text)), "duplicate_json_key")

    def test_rejects_wrong_json_types_and_nonstandard_constants(self):
        for text in ('null', '[]', '"answered"'):
            with self.subTest(text=text):
                self.assert_failed(sdk_response(sdk_message(text)), "invalid_json_type")
        self.assert_failed(sdk_response(sdk_message('{"value":NaN}')), "invalid_json")

    def test_reports_truncated_response_and_keeps_only_known_reason_codes(self):
        for reason in ("max_output_tokens", PRIVATE_TEXT):
            with self.subTest(reason=reason):
                response = sdk_response(sdk_message(SUMMARY_PLAN[:25]), status="incomplete").json()
                response["incomplete_details"] = {"reason": reason}
                details = self.assert_failed(httpx.Response(200, json=response), "incomplete_response", "response")
                self.assertEqual(details["response_status"], "incomplete")
                self.assertEqual(details.get("reason"), "max_output_tokens" if reason == "max_output_tokens" else None)

    def test_rejects_incomplete_message_even_when_response_is_completed(self):
        message = {**sdk_message(SUMMARY_PLAN), "status": "incomplete"}
        self.assert_failed(sdk_response(message), "incomplete_response")

    def test_reports_completed_response_without_final_text(self):
        for response in (sdk_response(), sdk_response(sdk_message(" \r\n ")),
                         sdk_response({"type": "reasoning", "id": "rs_test", "summary": []})):
            with self.subTest(response=response.json()["output"]):
                self.assert_failed(response, "missing_response_text")

    def test_locally_rejects_schema_violations_despite_strict_request(self):
        for text, code, path in (
            ('{"status":"answered"}', "schema_validation_failed", "$"),
            ('{"status":"invented","citations":[]}', "schema_validation_failed", "$.status"),
            ('{"status":null,"citations":[]}', "invalid_field_type", "$.status"),
            ('{"status":"answered","citations":null}', "invalid_field_type", "$.citations"),
            ('{"status":"answered","citations":[{"ref":"E1","fields":[3]}]}', "invalid_reference_type", "$.citations[0]"),
            ('{"status":"answered","citations":[],"amount":4}', "unknown_evidence_field", "$"),
        ):
            with self.subTest(text=text):
                details = self.assert_failed(sdk_response(sdk_message(text)), code)
                self.assertEqual(details["path"], path)

    def test_json_plan_cannot_answer_without_verifiable_evidence(self):
        for turn, code in ((plan(), "missing_required_evidence"),
                           (plan("E9"), "unknown_evidence_reference"),
                           (plan({"ref": "E1", "fields": ["fabricated_field"]}), "invalid_reference_type"),
                           (plan("E1", "E1"), "duplicate_evidence_reference")):
            with self.subTest(plan=turn.answer_plan):
                self.assert_failed(sdk_response(sdk_message(turn.answer_plan)), code)

    def test_citation_diagnostics_include_safe_types_and_lengths(self):
        cases = (
            (plan(None), "invalid_reference_type", {"path": "$.citations[0]", "expected_type": "string", "actual_type": "null"}),
            (plan("E1", status="refused"), "invalid_citation_length", {"path": "$.citations", "max_items": 0, "actual_count": 1}),
            (plan(*(["E1"] * 9)), "invalid_citation_length", {"max_items": 1, "actual_count": 9}),
            (plan(PRIVATE_TEXT), "unknown_evidence_reference", {"path": "$.citations[0]", "available_count": 1}),
            (plan(), "missing_required_evidence", {"path": "$.citations", "min_items": 1, "actual_count": 0}),
        )
        for turn, code, expected in cases:
            with self.subTest(code=code):
                details = self.assert_failed(sdk_response(sdk_message(turn.answer_plan)), code)
                self.assertEqual({key: details[key] for key in expected}, expected)

    def test_failed_tool_result_never_becomes_a_schema_ref_or_answer_section(self):
        def handler(request):
            body = json.loads(request.content)
            history = body["input"]
            if len(history) == 1:
                return sdk_response(call("missing", "get_anomaly_details", {"anomaly_id": "ANOM-UNKNOWN"}).input_item())
            self.assertNotIn("ref", json.loads(history[2]["output"]))
            schema = body["text"]["format"]["json_schema"]["schema"]
            self.assertEqual(schema["properties"]["citations"]["maxItems"], 0)
            self.assertNotIn("enum", schema["properties"]["citations"]["items"])
            self.assertNotIn("answered", schema["properties"]["status"]["enum"])
            return sdk_response(sdk_message(plan("E1").answer_plan))

        with local_transport(handler):
            result = run_agent("Show the anomaly details.", "en", QwenAgentProvider(QwenSettings.from_env(ENV)), self.registry)
        self.assertEqual((result["status"], result["answer_sections"]), ("failed", []))
        self.assertEqual(result["error_details"]["code"], "unknown_evidence_reference")

    def test_service_rejection_does_not_retry_or_drop_the_schema(self):
        response = httpx.Response(400, json={"error": {"message": PRIVATE_TEXT}})
        self.assert_failed(response, "request_failed", "request")

    def test_verifier_exposes_safe_parse_cause_and_preserves_financial_files(self):
        files = [*(ROOT / "data" / "sample").glob("*.csv"), *self.financial.iterdir()]
        before = {file: file.read_bytes() for file in files}
        result, _ = self.summary(sdk_response(sdk_message(SUMMARY_PLAN + PRIVATE_TEXT)), verify=True)
        self.assertEqual(result["verification"], "FAIL")
        failure, = result["verification_failures"]
        self.assertEqual(failure["code"], "not_answered")
        self.assertEqual(failure["cause"], result["error_details"])
        self.assertEqual(failure["cause"]["code"], "invalid_json")
        self.assertNotIn(PRIVATE_TEXT, json.dumps(result))
        self.assertEqual({file: file.read_bytes() for file in files}, before)
