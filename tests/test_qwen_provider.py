import io
import json
import os
import unittest
from contextlib import redirect_stderr, redirect_stdout
from getpass import GetPassWarning
from pathlib import Path
from unittest.mock import patch

import httpx

from analyze import main as analyze_cli
from scripts.verify_qwen_live import main as verify_cli
from src.context_builder import SOURCE_FILES, build_context
from src.llm_analyzer import analyze, render_markdown
from src.llm_client import LLMError, MockProvider, OpenAIProvider, create_provider
from src.output_validator import OutputValidationError
from src.prompts import ANALYSIS_SCHEMA
from src.qwen_provider import DEFAULT_MODEL, SMOKE_OUTPUT_LIMIT, QwenProvider, QwenSettings
from src.reconciliation import reconcile
from src.reporting import write_reports
from tests.fixtures import load_fixture, service, workspace_temp


BASE = "https://workspace-test.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
KEY = "placeholder-dashscope-credential"
OTHER_KEY = "placeholder-openai-credential"
ENV = {"QWEN_BASE_URL": BASE, "DASHSCOPE_API_KEY": KEY, "LLM_MAX_RETRIES": "0"}
USAGE = {"input_tokens": 16, "output_tokens": 3, "total_tokens": 19}
PAYLOAD = {"findings": [], "language": "en", "analysis_scope": "ANOMALY_ANALYSIS"}


def local_transport(handler):
    return patch.object(httpx.Client, "_init_transport", return_value=httpx.MockTransport(handler))


def reply(text="OK", status="completed", usage=USAGE, reasoning=False):
    output = [{"type": "message", "id": "msg_local", "role": "assistant", "status": status,
               "content": [{"type": "output_text", "text": text, "annotations": []}]}]
    if reasoning:
        output.insert(0, {"type": "reasoning", "id": "rs_local", "summary": []})
    return httpx.Response(200, json={
        "id": "resp_local", "model": "qwen3.8-flash", "object": "response", "created_at": 0,
        "status": status, "output": output, "usage": usage,
    })


class QwenProviderTests(unittest.TestCase):
    def provider(self, **overrides):
        return create_provider("qwen", env={**ENV, **overrides})

    def test_configuration_accepts_official_workspace_shared_and_trial_urls(self):
        for url in (BASE + "/", "https://dashscope.aliyuncs.com/compatible-mode/v1",
                    "https://trial.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1"):
            with self.subTest(url=url):
                provider = self.provider(QWEN_BASE_URL=url, QWEN_MODEL="example-model", LLM_TIMEOUT="1.5")
                self.assertIsInstance(provider, QwenProvider)
                self.assertEqual(provider.mode, "Live")
                self.assertEqual(provider.settings.base_url, url.rstrip("/"))
                self.assertEqual(provider.settings.model, "example-model")
                self.assertEqual(provider.settings.timeout, 1.5)
                self.assertNotIn(url.rstrip("/"), repr(provider.settings))
                self.assertNotIn(KEY, repr(provider.settings))
        self.assertEqual(self.provider().settings.model, DEFAULT_MODEL)

    def test_rejects_untrusted_or_non_base_urls_without_echoing_input(self):
        for url in (
            BASE.replace("https:", "http:"), BASE.replace(".com/", ".com.example/"),
            BASE.replace("workspace-test.", "child.workspace-test."), BASE + "/responses",
            BASE + "?token=private-placeholder", BASE + "#fragment", BASE.replace(".com/", ".com:8443/"),
            BASE.replace("https://", "https://user@"), BASE.replace("/compatible", "/%63ompatible"),
            BASE.replace("cn-beijing", "invented-region"), BASE.replace("workspace-test", "token-plan"),
            BASE.replace("workspace-test.cn-beijing", "trial.eu-central-1"),
            "https://api.openai.com/compatible-mode/v1", "https://127.0.0.1/compatible-mode/v1",
        ):
            with self.subTest(url=url), self.assertRaisesRegex(LLMError, "official Alibaba") as error:
                self.provider(QWEN_BASE_URL=url)
            self.assertNotIn(url, str(error.exception))

    def test_config_requires_dashscope_key_and_base_url(self):
        for key in ("", "sk-proj-placeholder"):
            with self.subTest(key=key), self.assertRaisesRegex(LLMError, "DASHSCOPE_API_KEY"):
                self.provider(DASHSCOPE_API_KEY=key, OPENAI_API_KEY=OTHER_KEY, LLM_API_KEY=OTHER_KEY)
        with self.assertRaisesRegex(LLMError, "requires QWEN_BASE_URL"):
            self.provider(QWEN_BASE_URL="")

    def test_default_mock_and_openai_configuration_remain_independent(self):
        settings = {**ENV, "LLM_API_KEY": OTHER_KEY, "LLM_MODEL": "openai-test-model"}
        mock = create_provider(env=settings)
        self.assertEqual((mock.name, mock.mode), ("mock", "Mock"))
        openai = create_provider("openai", env=settings)
        self.assertIsInstance(openai, OpenAIProvider)
        self.assertEqual(openai.settings.api_key, OTHER_KEY)
        self.assertEqual(create_provider(env={**settings, "LLM_PROVIDER": "qwen"}).settings.api_key, KEY)

    def test_wire_request_uses_alibaba_schema_and_removes_openai_headers(self):
        requests = []

        def handler(request):
            requests.append(request)
            data = json.loads(request.content)
            self.assertEqual(str(request.url), BASE + "/responses")
            self.assertEqual(request.headers["Authorization"], f"Bearer {KEY}")
            self.assertNotIn("OpenAI-Organization", request.headers)
            self.assertNotIn("OpenAI-Project", request.headers)
            self.assertNotIn("x-secret-test", request.headers)
            self.assertNotIn(OTHER_KEY, request.content.decode())
            self.assertEqual(data["model"], DEFAULT_MODEL)
            self.assertEqual(json.loads(data["input"]), PAYLOAD)
            self.assertEqual(data["reasoning"], {"effort": "none"})
            self.assertFalse(data["store"])
            self.assertEqual(data["text"]["format"], {
                "type": "json_schema",
                "json_schema": {"name": "anomaly_analysis", "strict": True, "schema": ANALYSIS_SCHEMA},
            })
            for name in ("tools", "background", "enable_thinking", "response_format"):
                self.assertNotIn(name, data)
            self.assertEqual(request.extensions["timeout"]["read"], 1.25)
            return reply("{}", reasoning=True)

        ambient = {"OPENAI_BASE_URL": "https://example.invalid", "OPENAI_API_KEY": OTHER_KEY,
                   "HTTPS_PROXY": "http://example.invalid:8080", "NO_PROXY": "",
                   "OPENAI_ORG_ID": "fake-org", "OPENAI_PROJECT_ID": "fake-project",
                   "OPENAI_CUSTOM_HEADERS": f"X-Secret-Test: {OTHER_KEY}\nAuthorization: Bearer {OTHER_KEY}"}
        with patch.dict(os.environ, ambient, clear=True), local_transport(handler), \
                patch.object(httpx.Client, "_init_proxy_transport", side_effect=AssertionError("Unexpected proxy")):
            result = self.provider(LLM_TIMEOUT="1.25").generate("en", PAYLOAD)
        self.assertEqual((result.text, result.model, result.usage), ("{}", DEFAULT_MODEL, USAGE))
        self.assertEqual(len(requests), 1)

    def test_redirect_is_never_followed(self):
        seen = []

        def handler(request):
            seen.append(str(request.url))
            return httpx.Response(307, headers={"Location": "https://example.invalid/collect"})

        with local_transport(handler), self.assertRaisesRegex(LLMError, "Redirects are disabled"):
            self.provider().probe()
        self.assertEqual(seen, [BASE + "/responses"])

    def test_authentication_and_rate_limit_errors_are_sanitized(self):
        for code, message in ((401, "authentication failed"), (429, "quota limit reached")):
            def handler(request):
                return httpx.Response(code, json={"error": {"message": KEY + BASE}})

            with self.subTest(code=code), local_transport(handler), self.assertRaisesRegex(LLMError, message) as error:
                self.provider().generate("en", PAYLOAD)
            self.assertNotIn(KEY, str(error.exception))
            self.assertNotIn(BASE, str(error.exception))

    def test_timeout_and_network_errors_are_reported(self):
        for error, expectation in ((httpx.ReadTimeout, "timed out"), (httpx.ConnectError, "connection failed")):
            def handler(request):
                raise error("simulated transport failure", request=request)

            with self.subTest(error=error), local_transport(handler), self.assertRaisesRegex(LLMError, expectation):
                self.provider().probe()

    def test_probe_disables_retries_and_caps_output(self):
        bodies = []

        def handler(request):
            bodies.append(json.loads(request.content))
            return httpx.Response(429, json={"error": {"message": "local rate limit"}})

        with local_transport(handler), self.assertRaisesRegex(LLMError, "quota"):
            self.provider(LLM_MAX_RETRIES="4").probe()
        body, = bodies
        self.assertEqual(body["input"], "Connection check. Reply only with OK.")
        self.assertEqual(body["max_output_tokens"], SMOKE_OUTPUT_LIMIT)
        self.assertFalse(body["store"])
        self.assertNotIn("text", body)

    def test_regular_analysis_applies_shared_retry_limit(self):
        calls = []

        def handler(request):
            calls.append(request)
            return httpx.Response(429, json={"error": {"message": "local rate limit"}})

        with local_transport(handler), patch("openai._base_client.time.sleep"), \
                self.assertRaisesRegex(LLMError, "quota"):
            self.provider(LLM_MAX_RETRIES="2").generate("en", PAYLOAD)
        self.assertEqual(len(calls), 3)

    def test_response_failure_or_sensitive_content_is_rejected_without_sdk_logs(self):
        for content, status, error in (("", "incomplete", "incomplete"), (KEY, "completed", "sensitive"),
                                       (BASE, "completed", "sensitive")):
            with self.subTest(status=status), local_transport(lambda request: reply(content, status)):
                with self.assertNoLogs(level="DEBUG"), self.assertRaisesRegex(LLMError, error):
                    self.provider().probe()

    def test_usage_can_be_absent(self):
        with local_transport(lambda request: reply(usage=None)):
            self.assertIsNone(self.provider().probe().usage)


class QwenAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.directory = Path(self.enterContext(workspace_temp()))
        self.financial = self.directory / "financial"
        self.report = self.directory / "analysis"
        write_reports(reconcile(load_fixture(services=[service()])), self.financial)
        self.context = build_context(self.financial)
        self.output = json.loads(MockProvider().generate("en", self.context.model_input("en")).text)

    def test_qwen_analysis_is_live_and_includes_usage(self):
        with local_transport(lambda request: reply(json.dumps(self.output))):
            report = analyze(self.context, create_provider("qwen", env=ENV), "en")
        self.assertEqual((report["provider"], report["run_mode"]), ("qwen", "Live"))
        self.assertIsNone(report["mode_notice"])
        self.assertEqual(report["usage"], USAGE)
        self.assertIn("Token usage", render_markdown(report))

    def test_shared_model_validation_rejects_invalid_json_and_fake_reference(self):
        self.output["anomaly_findings"][0]["evidence_references"] = ["invented-record"]
        for text, message in (("bad JSON", "not valid JSON"), (json.dumps(self.output), "evidence references")):
            with self.subTest(message=message), local_transport(lambda request: reply(text)):
                with self.assertRaisesRegex(OutputValidationError, message):
                    analyze(self.context, create_provider("qwen", env=ENV), "en")

    def test_cli_failure_preserves_engine_files_and_publishes_no_analysis(self):
        before = {name: (self.financial / name).read_bytes() for name in SOURCE_FILES}
        with patch.dict(os.environ, ENV, clear=True), local_transport(
            lambda request: httpx.Response(401, json={"error": {"message": KEY}}),
        ), redirect_stderr(io.StringIO()) as stderr:
            result = analyze_cli(["--provider", "qwen", "--input-dir", str(self.financial),
                                  "--output-dir", str(self.report)])
        self.assertEqual(result, 1)
        self.assertIn("authentication failed", stderr.getvalue())
        self.assertNotIn(KEY, stderr.getvalue())
        self.assertFalse(self.report.exists())
        self.assertEqual(before, {name: (self.financial / name).read_bytes() for name in SOURCE_FILES})

    def test_verifier_requires_explicit_live_flag(self):
        with patch("scripts.verify_qwen_live.QwenProvider") as provider, redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as exit_result:
                verify_cli([])
        self.assertEqual(exit_result.exception.code, 2)
        provider.assert_not_called()

    def test_verifier_hidden_prompt_prints_only_safe_metadata(self):
        with patch.dict(os.environ, ENV, clear=True), local_transport(lambda request: reply()), \
                patch("scripts.verify_qwen_live.sys.stdin.isatty", return_value=True), \
                patch("scripts.verify_qwen_live.sys.stderr.isatty", return_value=True), \
                patch("scripts.verify_qwen_live.getpass", return_value="prompted-placeholder") as prompt, \
                redirect_stdout(io.StringIO()) as output:
            self.assertEqual(verify_cli(["--live", "--prompt-key"]), 0)
        prompt.assert_called_once()
        metadata = json.loads(output.getvalue())
        self.assertEqual(set(metadata), {"model", "status", "usage", "elapsed_seconds"})
        self.assertEqual(metadata["usage"], USAGE)
        self.assertNotIn(BASE, output.getvalue())
        self.assertNotIn("prompted-placeholder", output.getvalue())

    def test_verifier_never_uses_an_echoing_fallback(self):
        with patch.dict(os.environ, {"QWEN_BASE_URL": BASE}, clear=True), \
                patch("scripts.verify_qwen_live.sys.stdin.isatty", return_value=True), \
                patch("scripts.verify_qwen_live.sys.stderr.isatty", return_value=True), \
                patch("scripts.verify_qwen_live.getpass", side_effect=GetPassWarning), \
                patch("scripts.verify_qwen_live.QwenProvider") as provider, redirect_stderr(io.StringIO()):
            self.assertEqual(verify_cli(["--live", "--prompt-key"]), 1)
        provider.assert_not_called()

    def test_structured_verifier_is_separate_and_does_not_write_reports(self):
        calls = []

        def handler(request):
            calls.append(json.loads(request.content))
            return reply(json.dumps(self.output))

        with patch.dict(os.environ, ENV, clear=True), local_transport(handler), redirect_stdout(io.StringIO()) as output:
            code = verify_cli(["--live", "--structured", "--input-dir", str(self.financial)])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.getvalue())["status"], "completed")
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["max_output_tokens"], 10000)
        schema = calls[0]["text"]["format"]["json_schema"]["schema"]["properties"]
        finding = schema["anomaly_findings"]["items"]["properties"]
        for field in (finding["possible_causes"], finding["recommended_actions"]):
            self.assertEqual((field["minItems"], field["maxItems"]), (1, 8))
        self.assertEqual(finding["optional_analysis"]["type"], ["string", "null"])
        self.assertIn("1 to 8 possible_causes and recommended_actions objects per finding", calls[0]["instructions"])
        self.assertEqual({path.name for path in self.financial.iterdir()}, set(SOURCE_FILES))

    def test_structured_verifier_reports_the_invalid_list_without_raw_content(self):
        self.output["anomaly_findings"][0]["recommended_actions"] = []
        self.output["anomaly_findings"][0]["optional_analysis"] = "Confidential example narrative."
        raw = json.dumps(self.output)
        with (
            patch.dict(os.environ, ENV, clear=True),
            local_transport(lambda request: reply(raw)),
            redirect_stderr(io.StringIO()) as stderr,
            redirect_stdout(io.StringIO()) as stdout,
        ):
            code = verify_cli(["--live", "--structured", "--input-dir", str(self.financial)])
        self.assertEqual(code, 1)
        self.assertEqual(stdout.getvalue(), "")
        message = stderr.getvalue()
        self.assertIn("anomaly_findings[0].recommended_actions", message)
        self.assertIn("1 to 8 entries, got 0 entries", message)
        for secret in ("Confidential example narrative.", KEY, BASE):
            self.assertNotIn(secret, message)
