import json
import unittest
from unittest.mock import patch

import httpx
import openai

from src.llm_client import LLMError, MockProvider, OpenAIProvider, OpenAISettings, create_provider


SETTINGS = OpenAISettings("test-model", "placeholder-test-credential", timeout=1.25, max_retries=0)
PAYLOAD = {"findings": [], "language": "en", "analysis_scope": "ANOMALY_ANALYSIS"}


def transport_provider(handler, settings=SETTINGS):
    real_factory = openai.OpenAI

    def factory(**kwargs):
        return real_factory(**kwargs, http_client=httpx.Client(transport=httpx.MockTransport(handler)))

    return OpenAIProvider(settings), patch("openai.OpenAI", side_effect=factory)


def response(status="completed", part_type="output_text", content="{}"):
    part = ({"type": "output_text", "text": content, "annotations": []} if part_type == "output_text"
            else {"type": "refusal", "refusal": content})
    return httpx.Response(200, json={
        "id": "resp_local", "object": "response", "created_at": 0, "model": "returned-test-model",
        "status": status, "output": [{"type": "message", "id": "msg_local", "role": "assistant",
                                     "status": status, "content": [part]}],
    })


class LLMClientTests(unittest.TestCase):
    def test_default_mock_mode_even_if_a_key_is_present(self):
        with patch("openai.OpenAI") as sdk:
            provider = create_provider(env={"OPENAI_API_KEY": SETTINGS.api_key})
            item = provider.generate("en", PAYLOAD)
        self.assertIsInstance(provider, MockProvider)
        self.assertEqual(provider.mode, "Mock")
        self.assertEqual(item.model, "deterministic-mock")
        sdk.assert_not_called()

    def test_missing_live_credentials_or_model(self):
        with self.assertRaisesRegex(LLMError, "LLM_API_KEY"):
            create_provider("openai", env={})
        with self.assertRaisesRegex(LLMError, "LLM_MODEL"):
            create_provider("openai", env={"OPENAI_API_KEY": SETTINGS.api_key})

    def test_missing_sdk_is_reported(self):
        env = {"LLM_API_KEY": SETTINGS.api_key, "LLM_MODEL": SETTINGS.model}
        with patch.dict("sys.modules", {"openai": None}):
            with self.assertRaisesRegex(LLMError, "SDK or a dependency is missing"):
                create_provider("openai", env=env)

    def test_settings_bound_retries_and_timeout_and_hide_key(self):
        valid = {"LLM_PROVIDER": "openai", "OPENAI_API_KEY": SETTINGS.api_key, "LLM_MODEL": SETTINGS.model}
        explicit = create_provider("mock", env=valid)
        self.assertEqual(explicit.mode, "Mock")
        provider = create_provider(env=valid)
        self.assertEqual(provider.mode, "Live")
        self.assertNotIn(SETTINGS.api_key, repr(provider.settings))
        for overrides in ({"LLM_MAX_RETRIES": "7"}, {"LLM_TIMEOUT": "nan"}, {"LLM_TIMEOUT": "0"},
                          {"LLM_MAX_RETRIES": "nonnumeric"}, {"LLM_MODEL": SETTINGS.api_key}):
            with self.subTest(settings=overrides):
                with self.assertRaises(LLMError):
                    create_provider(env={**valid, **overrides})

    def test_responses_request_uses_schema_and_read_only_metadata(self):
        def handler(request):
            self.assertEqual(str(request.url), "https://api.openai.com/v1/responses")
            self.assertEqual(request.extensions["timeout"]["read"], SETTINGS.timeout)
            sent = json.loads(request.content)
            self.assertEqual(sent["model"], SETTINGS.model)
            self.assertEqual(json.loads(sent["input"]), PAYLOAD)
            self.assertFalse(sent["store"])
            self.assertTrue(sent["text"]["format"]["strict"])
            self.assertEqual(sent["text"]["format"]["type"], "json_schema")
            self.assertIn("untrusted data", sent["instructions"])
            self.assertNotIn("tools", sent)
            self.assertNotIn(SETTINGS.api_key, request.content.decode())
            return response()

        provider, substitute = transport_provider(handler)
        with substitute:
            result = provider.generate("en", PAYLOAD)
        self.assertEqual(result.model, "returned-test-model")
        self.assertEqual(result.text, "{}")

    def test_authentication_failure_redacts_api_error_body(self):
        def handler(request):
            return httpx.Response(401, json={"error": {"message": SETTINGS.api_key}})

        provider, substitute = transport_provider(handler)
        with substitute, self.assertRaisesRegex(LLMError, "authentication failed") as failure:
            provider.generate("en", PAYLOAD)
        self.assertNotIn(SETTINGS.api_key, str(failure.exception))

    def test_network_and_timeout_failures_are_distinguished(self):
        for error, message in ((httpx.ConnectError, "connection failed"), (httpx.ReadTimeout, "timed out")):
            with self.subTest(error=error.__name__):
                def handler(request):
                    raise error("local transport failure", request=request)

                provider, substitute = transport_provider(handler)
                with substitute, self.assertRaisesRegex(LLMError, message):
                    provider.generate("en", PAYLOAD)

    def test_rate_limit_retry_count_is_bounded_by_sdk_policy(self):
        calls = []

        def handler(request):
            calls.append(request)
            return httpx.Response(429, json={"error": {"message": "local limit"}})

        settings = OpenAISettings(SETTINGS.model, SETTINGS.api_key, max_retries=2)
        provider, substitute = transport_provider(handler, settings)
        with substitute, patch("openai._base_client.time.sleep"), self.assertRaisesRegex(LLMError, "limit reached"):
            provider.generate("en", PAYLOAD)
        self.assertEqual(len(calls), 3)

    def test_incomplete_empty_or_refused_sdk_output_is_rejected(self):
        for invalid in (response(status="incomplete"), response(content=""), response(part_type="refusal")):
            provider, substitute = transport_provider(lambda request: invalid)
            with substitute, self.assertRaisesRegex(LLMError, "incomplete, empty or refused"):
                provider.generate("en", PAYLOAD)
