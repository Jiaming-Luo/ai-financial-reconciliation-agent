import io
import json
import os
import unittest
from contextlib import redirect_stdout
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import httpx
from streamlit.testing.v1 import AppTest

from analyze import main as analyze_cli
from src.anomaly_detector import RECOMMENDED_ACTIONS
from src.data_loader import load_data
from src.llm_client import MockProvider
from src.prompts import ANALYSIS_SCHEMA, CAUSE_SCHEMA
from src.qwen_provider import QwenSettings
from src.reconciliation import reconcile
from src.reporting import summarize
from tests.fixtures import workspace_temp
from tests.test_agent import call, plan, sdk_message, sdk_response
from tests.test_qwen_provider import BASE, ENV, KEY, local_transport
from ui import services
from ui.text import chart_label


ROOT = Path(__file__).resolve().parents[1]


class StreamlitTests(unittest.TestCase):
    def start(self):
        app = AppTest.from_file(ROOT / "app.py", default_timeout=25).run()
        self.assertFalse(list(app.exception))
        return app

    def page(self, app, page):
        app.radio(key="ui_page").set_value(page).run()
        self.assertFalse(list(app.exception))

    def click(self, app, label):
        next(widget for widget in app.button if widget.label == label).click().run()
        self.assertFalse(list(app.exception))

    def live_form(self, app, namespace):
        for field, value in (("base", BASE), ("key", KEY)):
            next(widget for widget in app.text_input if widget.key.startswith(f"{namespace}_live_")
                 and widget.key.endswith(f"_{field}")).set_value(value)
        app.checkbox[0].check()

    def test_pages_and_language_switch_work_without_api_access(self):
        def deny(request):
            self.fail("UI initialization must not call a provider")

        with local_transport(deny):
            app = self.start()
            self.assertEqual(app.radio(key="ui_mode").value, "mock")
            self.assertIn("Dashboard", app.title.values)
            for page, title in (("reconciliation", "Reconciliation"), ("anomalies", "Anomaly Review"),
                                ("assistant", "AI Assistant"), ("knowledge", "Knowledge Base")):
                self.page(app, page)
                self.assertIn(title, app.title.values)
            self.page(app, "dashboard")
            app.selectbox(key="ui_language").set_value("cn").run()
            self.assertFalse(list(app.exception))
            self.assertIn("财务总览", app.title.values)
            self.assertIn("结算组数", [metric.label for metric in app.metric])

    def test_dashboard_matches_engine_artifacts_and_preserves_unknown_amounts(self):
        app = self.start()
        baseline = summarize(reconcile(load_data(services.SAMPLE_ROOT)))
        self.assertEqual(app.session_state["snapshot"].summary, baseline)
        metrics = {metric.label: metric.value for metric in app.metric}
        self.assertEqual(metrics["Settlement group count"], str(baseline["settlement_group_count"]))
        for field in ("comparable_receivable_amount", "comparable_paid_amount", "net_difference", "held_eligible_payment_amount"):
            self.assertIn(f"**CNY {Decimal(baseline[field]):,.2f}**", app.markdown.values)
        for field, value in (("hospital_id", "SIM-H004"), ("settlement_period", "2026-05")):
            next(widget for widget in app.selectbox if widget.key.startswith(f"dashboard_{field}_")).set_value(value).run()
        row = app.dataframe[0].value.to_dict("records")[0]
        self.assertEqual(row["Expected amount"], "Not determinable")
        self.assertEqual(row["Difference amount"], "Not determinable")
        self.assertEqual(row["Paid amount"], "10406.50")

    def test_mock_analysis_anomaly_evidence_and_combined_answer(self):
        app = self.start()
        self.page(app, "anomalies")
        self.click(app, "Run AI analysis")
        report = app.session_state["analysis"]
        self.assertEqual((report["report_schema_version"], report["core_validation"], report["run_mode"]), ("3.0", "passed", "Mock"))
        next(item for item in app.selectbox if item.key.startswith("anomaly_anomaly_type_")).set_value("CONTRACT_OVERLAP").run()
        self.assertFalse(list(app.exception))
        self.assertTrue(any("CONTRACT_OVERLAP" in item or "Contract overlap" in item for item in app.subheader.values))
        self.assertTrue(any("SIM-C0024" in item.value for item in app.text))
        self.assertTrue(any({"SIM-C0024", "SIM-C0032"} <= set(item.value.splitlines()) for item in app.text))
        self.page(app, "assistant")
        app.selectbox(key="example_mock").set_value("combined").run()
        self.click(app, "Ask assistant")
        _, answer = app.session_state["answer"]
        self.assertEqual((answer["run_mode"], answer["status"]), ("Mock", "answered"))
        self.assertEqual([item["ref"] for item in answer["answer_sections"]], ["E1", "K1"])
        self.assertEqual(answer["answer_sections"][0]["data"]["paid_amount"], "10406.50")
        self.assertIsNone(answer["answer_sections"][0]["data"]["expected_amount"])
        self.assertTrue(any("KB-02" in item.value for item in app.text))
        labels = {item.label for item in app.metric}
        self.assertIn("Simulated model requests", labels)
        self.assertNotIn("Model requests", labels)
        self.assertIn("Answered · evidence references validated", [message.value for message in app.success])

    def test_upload_change_clears_analysis_and_isolates_refresh_and_other_sessions(self):
        app = self.start()
        original_count = app.session_state["snapshot"].summary["raw_payment_count"]
        self.page(app, "anomalies")
        self.click(app, "Run AI analysis")
        self.page(app, "assistant")
        self.click(app, "Ask assistant")
        self.page(app, "reconciliation")
        app.radio(key="source_widget").set_value("upload").run()
        for key in ("snapshot", "analysis", "answer"):
            self.assertNotIn(key, app.session_state)
        self.assertTrue(app.button(key="run_finance").proto.disabled)
        samples = services.sample_files()
        header, _, *rest = samples["payments.csv"].splitlines(keepends=True)
        samples["payments.csv"] = b"".join((header, *rest))
        for name in services.SOURCE_FIELDS:
            app.file_uploader(key=f"upload_{name}_0").upload(name, samples[name], "text/csv").run()
        self.assertFalse(list(app.exception))
        self.click(app, "Run reconciliation")
        self.assertEqual(app.session_state["snapshot"].summary["run_status"], "COMPLETED")
        self.assertEqual(app.session_state["snapshot"].summary["raw_payment_count"], original_count - 1)
        self.page(app, "dashboard")
        self.page(app, "reconciliation")
        self.assertEqual(app.radio(key="source_widget").value, "upload")
        self.assertEqual(set(app.session_state["uploads"]), set(services.SOURCE_FIELDS))
        app.file_uploader(key="upload_contracts.csv_0").upload("custom.csv", b"wrong,header\n1,2\n", "text/csv").run()
        self.click(app, "Run reconciliation")
        self.assertNotIn("snapshot", app.session_state)
        self.assertIn("CSV header", app.error[-1].value)
        separate = self.start()
        self.assertEqual(separate.session_state["source_mode"], "sample")
        self.assertEqual(separate.session_state["uploads"], {})

    def test_knowledge_page_returns_local_ranked_source_and_no_match(self):
        app = self.start()
        self.page(app, "knowledge")
        app.text_input(key="kb_query").set_value("contract overlap").run()
        self.assertTrue(any("KB-02 §2" in item.value for item in app.text))
        self.assertTrue(any("BM25 relevance" in item.value for item in app.text))
        app.text_input(key="kb_query").set_value("lunar eclipse").run()
        self.assertTrue(any("Insufficient verified evidence" in item.value for item in app.info))

    def test_live_only_on_submit_clears_credentials_and_survives_reruns(self):
        requests = []

        def handler(request):
            body = json.loads(request.content)
            requests.append(body)
            self.assertEqual(str(request.url), BASE + "/responses")
            if len(requests) == 1:
                return sdk_response(call("summary", "get_reconciliation_summary").input_item())
            return sdk_response(sdk_message(plan("E1").answer_plan))

        with local_transport(handler):
            app = self.start()
            self.page(app, "assistant")
            app.radio(key="ui_mode").set_value("live").run()
            self.assertEqual(requests, [])
            app.selectbox(key="example_live").set_value("summary").run()
            self.live_form(app, "assistant")
            self.click(app, "Ask assistant")
            self.assertEqual(len(requests), 2)
            self.assertEqual(app.session_state["answer"][1]["status"], "answered")
            self.assertFalse(KEY in str(app.session_state))
            self.assertFalse(BASE in str(app.session_state))
            app.run()
            self.page(app, "dashboard")
            app.selectbox(key="ui_language").set_value("cn").run()
            self.page(app, "assistant")
            self.assertEqual(len(requests), 2)

    def test_live_rejection_and_insufficient_evidence_keep_financial_results(self):
        hits = []

        def handler(request):
            hits.append(request.url.path)
            if len(hits) == 1:
                return httpx.Response(401, json={"error": {"message": KEY}})
            return sdk_response(sdk_message(plan(status="insufficient_evidence").answer_plan))

        with local_transport(handler):
            app = self.start()
            self.page(app, "anomalies")
            app.radio(key="ui_mode").set_value("live").run()
            self.click(app, "Run AI analysis")
            self.assertEqual(hits, [])
            self.live_form(app, "analysis")
            self.click(app, "Run AI analysis")
            self.assertEqual(len(hits), 1)
            self.assertNotIn("analysis", app.session_state)
            self.assertIn("Financial results are still available", app.error[-1].value)
            self.assertEqual(app.session_state["analysis_diagnostic"], {
                "error_code": "authentication_failed", "error_stage": "request", "http_status": 401,
                "model_request_count": 1,
            })
            self.assertIn("Error diagnostics", [element.label for element in app.expander])
            self.assertFalse(KEY in str(app.session_state))
            self.page(app, "assistant")
            app.selectbox(key="example_live").set_value("duplicate").run()
            self.live_form(app, "assistant")
            self.click(app, "Ask assistant")
            self.assertEqual(app.session_state["answer"][1]["status"], "insufficient_evidence")
            self.assertEqual(app.session_state["snapshot"].summary["run_status"], "COMPLETED")

    def test_live_analysis_uses_validated_v3_schema_and_clears_form(self):
        requests = []

        def handler(request):
            body = json.loads(request.content)
            requests.append(body)
            format_config = body["text"]["format"]["json_schema"]
            self.assertEqual(format_config["name"], "anomaly_analysis")
            self.assertTrue(format_config["strict"])
            payload = json.loads(body["input"])
            return sdk_response(sdk_message(MockProvider().generate(payload["language"], payload).text))

        with local_transport(handler):
            app = self.start()
            self.page(app, "anomalies")
            app.radio(key="ui_mode").set_value("live").run()
            self.assertEqual(requests, [])
            self.live_form(app, "analysis")
            self.click(app, "Run AI analysis")
            report = app.session_state["analysis"]
            self.assertEqual((report["run_mode"], report["core_validation"], report["report_schema_version"]), ("Live", "passed", "3.0"))
            self.assertEqual(len(report["anomaly_findings"]), 9)
            self.assertFalse(KEY in str(app.session_state))
            self.assertFalse(BASE in str(app.session_state))
            app.run()
            self.assertEqual(len(requests), 1)

    def test_live_schema_failure_clears_old_report_and_persists_only_redacted_diagnostics(self):
        requests = []
        sentinel = "private-priority-model-value"

        def handler(request):
            requests.append(request)
            self.assertEqual(request.headers["Authorization"], f"Bearer {KEY}")
            payload = json.loads(json.loads(request.content)["input"])
            answer = json.loads(MockProvider().generate(payload["language"], payload).text)
            answer["anomaly_findings"][0]["priority"] = {"private": sentinel}
            return sdk_response(sdk_message(json.dumps(answer)))

        with local_transport(handler):
            app = self.start()
            self.page(app, "anomalies")
            self.click(app, "Run AI analysis")
            self.assertIn("analysis", app.session_state)
            self.page(app, "assistant")
            self.click(app, "Ask assistant")
            self.assertIn("answer", app.session_state)
            self.page(app, "anomalies")
            financial = app.session_state["snapshot"].files.copy()
            priorities = app.session_state["snapshot"].priorities.copy()
            app.radio(key="ui_mode").set_value("live").run()
            self.live_form(app, "analysis")
            self.click(app, "Run AI analysis")
            self.assertNotIn("analysis", app.session_state)
            self.assertNotIn("answer", app.session_state)
            self.assertEqual(app.session_state["analysis_diagnostic"], {
                "error_code": "schema_validation_failed", "error_stage": "validation", "model_request_count": 1,
                "validation_path": "anomaly_findings[0].priority", "expected_type": "string", "actual_type": "object",
                "validation_constraint": "type", "allowed_values": ["HIGH", "MEDIUM", "LOW"],
            })
            self.assertEqual(app.session_state["snapshot"].files, financial)
            self.assertEqual(app.session_state["snapshot"].priorities, priorities)
            self.assertIn("Error diagnostics", [element.label for element in app.expander])
            self.assertTrue(any("`HIGH`, `MEDIUM`, `LOW`" in item.value for item in app.markdown))
            self.assertFalse(any(value in str(app.session_state) for value in (sentinel, KEY, BASE)))
            next(widget for widget in app.selectbox if widget.key.startswith("anomaly_anomaly_type_")).set_value("CONTRACT_OVERLAP").run()
            self.page(app, "dashboard")
            self.page(app, "anomalies")
            app.run()
            self.assertEqual(len(requests), 1)

    def test_second_cause_failure_rejects_live_report_without_exposing_model_values(self):
        requests = []
        sentinel = "private-cause-model-value"

        def handler(request):
            requests.append(request)
            payload = json.loads(json.loads(request.content)["input"])
            answer = json.loads(MockProvider().generate(payload["language"], payload).text)
            causes = answer["anomaly_findings"][0]["possible_causes"]
            causes.append({"cause_code": sentinel, "evidence_references": []})
            return sdk_response(sdk_message(json.dumps(answer)))

        with local_transport(handler):
            app = self.start()
            self.page(app, "anomalies")
            self.click(app, "Run AI analysis")
            self.assertIn("analysis", app.session_state)
            financial = app.session_state["snapshot"].files.copy()
            priorities = app.session_state["snapshot"].priorities.copy()
            app.radio(key="ui_mode").set_value("live").run()
            self.live_form(app, "analysis")
            self.click(app, "Run AI analysis")
            self.assertNotIn("analysis", app.session_state)
            allowed = CAUSE_SCHEMA["properties"]["cause_code"]["enum"]
            self.assertEqual(app.session_state["analysis_diagnostic"], {
                "error_code": "schema_validation_failed", "error_stage": "validation", "model_request_count": 1,
                "validation_path": "anomaly_findings[0].possible_causes[1].cause_code", "validation_constraint": "enum",
                "expected_type": "string", "actual_type": "string", "actual_string_length": len(sentinel),
                "allowed_values": allowed,
            })
            self.assertTrue(any(all(f"`{code}`" in item.value for code in allowed) for item in app.markdown))
            visible = str([item.value for item in (*app.markdown, *app.caption)])
            for value in (sentinel, KEY, BASE):
                self.assertNotIn(value, visible)
                self.assertNotIn(value, str(app.session_state))
            self.assertEqual(app.session_state["snapshot"].files, financial)
            self.assertEqual(app.session_state["snapshot"].priorities, priorities)
            self.assertEqual(len(requests), 1)

    def test_invalid_json_and_unsupported_references_remain_fail_closed(self):
        for problem, code, path in (("json", "invalid_json", "$"),
                                    ("reference", "evidence_validation_failed", "anomaly_findings[0].evidence_references")):
            def handler(request):
                payload = json.loads(json.loads(request.content)["input"])
                if problem == "json":
                    return sdk_response(sdk_message('broken JSON with private-diagnostic-sentinel'))
                answer = json.loads(MockProvider().generate(payload["language"], payload).text)
                answer["anomaly_findings"][0]["evidence_references"] = ["private-diagnostic-sentinel"]
                return sdk_response(sdk_message(json.dumps(answer)))

            with self.subTest(problem=problem), local_transport(handler):
                app = self.start()
                self.page(app, "anomalies")
                app.radio(key="ui_mode").set_value("live").run()
                self.live_form(app, "analysis")
                self.click(app, "Run AI analysis")
                self.assertNotIn("analysis", app.session_state)
                details = app.session_state["analysis_diagnostic"]
                self.assertEqual((details["error_code"], details["validation_path"]), (code, path))
                self.assertNotIn("private-diagnostic-sentinel", str(details))

    def test_chinese_charts_use_short_labels_and_keep_original_codes_in_tooltips(self):
        app = self.start()
        app.selectbox(key="ui_language").set_value("cn").run()
        self.assertFalse(list(app.exception))
        charts = app.get("vega_lite_chart")
        self.assertEqual(len(charts), 2)
        for chart in charts:
            encoding = json.loads(chart.proto.spec)["encoding"]
            self.assertEqual(encoding["y"]["axis"]["labelLimit"], 0)
            self.assertIn("code", [entry["field"] for entry in encoding["tooltip"]])
        labels = [chart_label("cn", code) for code in RECOMMENDED_ACTIONS]
        self.assertEqual(len(set(labels)), 9)
        self.assertTrue(all(code not in label for code, label in zip(RECOMMENDED_ACTIONS, labels)))


class StreamlitServiceTests(unittest.TestCase):
    def test_cli_and_streamlit_send_the_same_analysis_body_for_the_same_reports(self):
        snapshot = services.reconcile_files(services.sample_files())
        requests = []

        def handler(request):
            body = json.loads(request.content)
            requests.append(body)
            self.assertEqual(str(request.url), BASE + "/responses")
            self.assertEqual(request.headers["Authorization"], f"Bearer {KEY}")
            payload = json.loads(body["input"])
            return sdk_response(sdk_message(MockProvider().generate(payload["language"], payload).text))

        with workspace_temp() as folder, local_transport(handler), patch.dict(os.environ, ENV, clear=True):
            for filename, content in snapshot.files.items():
                (Path(folder) / filename).write_bytes(content)
            with redirect_stdout(io.StringIO()):
                self.assertEqual(analyze_cli(["--provider", "qwen", "--input-dir", folder, "--output-dir", folder]), 0)
            report = services.analysis_report(snapshot, "en", QwenSettings.from_env(ENV))
        self.assertEqual(report["core_validation"], "passed")
        self.assertEqual(len(requests), 2)
        self.assertEqual(requests[0], requests[1])

    def test_analysis_wire_contract_keeps_machine_fields_and_codes_across_languages(self):
        snapshot = services.reconcile_files(services.sample_files())
        requests = []

        def handler(request):
            body = json.loads(request.content)
            requests.append(body)
            payload = json.loads(body["input"])
            return sdk_response(sdk_message(MockProvider().generate(payload["language"], payload).text))

        with local_transport(handler):
            for language in ("en", "cn"):
                report = services.analysis_report(snapshot, language, QwenSettings.from_env(ENV))
                self.assertEqual(report["core_validation"], "passed")
        self.assertEqual(len(requests), 2)
        english, chinese = requests
        for body in requests:
            self.assertEqual(body["text"]["format"], {"type": "json_schema", "json_schema": {
                "name": "anomaly_analysis", "strict": True, "schema": ANALYSIS_SCHEMA,
            }})
        en_input, cn_input = (json.loads(body.pop("input")) for body in requests)
        self.assertEqual((en_input.pop("language"), cn_input.pop("language")), ("en", "cn"))
        self.assertEqual(en_input, cn_input)
        cn_prompt = chinese.pop("instructions")
        en_prompt = english.pop("instructions")
        self.assertIn("note in Simplified Chinese", cn_prompt)
        self.assertEqual(cn_prompt.replace("note in Simplified Chinese", "note in English"), en_prompt)
        self.assertEqual(english, chinese)

    def test_upload_limits_headers_and_formula_identifiers(self):
        for filename, data, error in (("../external.csv", b"data", "invalid_file_type"),
                                      ("external.pdf", b"data", "invalid_file_type"),
                                      ("empty.csv", b"", "invalid_file_size"),
                                      ("large.csv", b"x" * (services.MAX_FILE_BYTES + 1), "invalid_file_size")):
            with self.assertRaisesRegex(services.AppInputError, error):
                services.safe_upload(filename, data)
        files = services.sample_files()
        files["payments.csv"] = files["payments.csv"].replace(b"SIM-H001", b"=example", 1)
        with self.assertRaisesRegex(services.AppInputError, "invalid_identifier"):
            services.reconcile_files(files)
        with self.assertRaisesRegex(services.AppInputError, "incomplete_upload"):
            services.reconcile_files({})

    def test_provisional_artifacts_cannot_be_sent_to_ai(self):
        files = services.sample_files()
        lines = files["service_records.csv"].splitlines(keepends=True)
        fields = lines[1].decode().rstrip().split(",")
        fields[1] = ""
        lines[1] = (",".join(fields) + "\n").encode()
        files["service_records.csv"] = b"".join(lines)
        snapshot = services.reconcile_files(files)
        self.assertTrue(snapshot.provisional)
        with self.assertRaisesRegex(services.AppInputError, "provisional_ai_block"):
            services.analysis_report(snapshot, "en")
