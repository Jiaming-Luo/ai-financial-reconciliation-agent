"""Alibaba Cloud Model Studio adapter for the compatible Responses API."""

import json
import logging
import re
from collections.abc import Mapping
from contextvars import ContextVar
from dataclasses import dataclass, field

from .llm_client import LLMError, LLMResponse, _request_policy, _valid_model
from .prompts import ANALYSIS_SCHEMA, instructions


DEFAULT_MODEL = "qwen3.8-flash"
SMOKE_OUTPUT_LIMIT = 32
_SHARED_HOSTS = {
    "dashscope.aliyuncs.com", "dashscope-intl.aliyuncs.com", "dashscope-us.aliyuncs.com",
    "cn-hongkong.dashscope.aliyuncs.com",
}
_WORKSPACE_REGIONS = {
    "cn-beijing", "ap-southeast-1", "ap-northeast-1", "eu-central-1", "us-east-1", "cn-hongkong",
}
_TRIAL_REGIONS = {"cn-beijing", "ap-southeast-1", "cn-hongkong"}
_BASE_URL = re.compile(r"https://([a-zA-Z0-9.-]+)/compatible-mode/v1/?", re.ASCII)
_WORKSPACE_HOST = re.compile(r"([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)\.([a-z0-9-]+)\.maas\.aliyuncs\.com")
_QUIET_QWEN_REQUEST = ContextVar("quiet_qwen_request", default=False)


def _trusted_base_url(value: str) -> str:
    match = _BASE_URL.fullmatch(value)
    if match:
        host = match[1].lower()
        workspace = _WORKSPACE_HOST.fullmatch(host)
        if host in _SHARED_HOSTS or (
            workspace and workspace[2] in _WORKSPACE_REGIONS and workspace[1] != "token-plan"
            and (workspace[1] != "trial" or workspace[2] in _TRIAL_REGIONS)
        ):
            return f"https://{host}/compatible-mode/v1"
    raise LLMError("QWEN_BASE_URL must be an official Alibaba Cloud Model Studio HTTPS base URL ending in /compatible-mode/v1.")


@dataclass(frozen=True)
class QwenSettings:
    model: str
    api_key: str = field(repr=False)
    base_url: str = field(repr=False)
    timeout: float = 30.0
    max_retries: int = 2

    def __post_init__(self):
        if not self.api_key:
            raise LLMError("Qwen requires DASHSCOPE_API_KEY.")
        if not re.fullmatch(r"[!-~]+", self.api_key) or self.api_key.startswith(("sk-proj-", "sk-svcacct-", "sk-admin-")):
            raise LLMError("DASHSCOPE_API_KEY must contain an Alibaba Cloud Model Studio credential.")
        if not self.base_url:
            raise LLMError("Qwen requires QWEN_BASE_URL for the region or workspace associated with the key.")
        object.__setattr__(self, "base_url", _trusted_base_url(self.base_url))
        if not _valid_model(self.model, self.api_key):
            raise LLMError("QWEN_MODEL must be a valid model identifier.")

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> "QwenSettings":
        timeout, retries = _request_policy(env)
        return cls(
            model=env.get("QWEN_MODEL", DEFAULT_MODEL).strip(),
            api_key=env.get("DASHSCOPE_API_KEY", "").strip(),
            base_url=env.get("QWEN_BASE_URL", "").strip(),
            timeout=timeout,
            max_retries=retries,
        )


def _allow_library_log(record: logging.LogRecord) -> bool:
    # SDK and HTTP debug records can expose the workspace hostname.
    return not _QUIET_QWEN_REQUEST.get()


def structured_output_body(name: str, schema: dict) -> dict:
    """Build the Alibaba-specific nested Responses format for SDK extra_body."""
    return {"text": {"format": {
        "type": "json_schema", "json_schema": {"name": name, "strict": True, "schema": schema},
    }}}


class QwenProvider:
    name = "qwen"
    mode = "Live"

    def __init__(self, settings: QwenSettings):
        self.settings = settings
        try:
            import httpx
            import openai
        except ImportError:
            raise LLMError("The OpenAI SDK or a dependency is missing. Install requirements.txt in the project venv.",
                           code="sdk_unavailable", stage="configuration") from None
        self.sdk = openai
        self.httpx = httpx
        for logger in ("openai._base_client", "httpx", "httpcore.connection", "httpcore.http11", "httpcore.http2"):
            logging.getLogger(logger).addFilter(_allow_library_log)

    def generate(self, language: str, payload: dict) -> LLMResponse:
        return self._request(
            input=json.dumps(payload, ensure_ascii=False),
            instructions=instructions(language),
            max_output_tokens=10000,
            extra_body=structured_output_body("anomaly_analysis", ANALYSIS_SCHEMA),
        )

    def probe(self) -> LLMResponse:
        """Send a bounded synthetic connectivity check without retrying."""
        return self._request(input="Connection check. Reply only with OK.",
                             max_output_tokens=SMOKE_OUTPUT_LIMIT, max_retries=0)

    def _request(self, *, max_retries: int | None = None, **fields) -> LLMResponse:
        return self._read_reply(self.create_response(max_retries=max_retries, **fields))

    def create_response(self, *, max_retries: int | None = None, **fields):
        """Use the same restricted transport for analysis and Responses tool turns."""
        settings, sdk, httpx = self.settings, self.sdk, self.httpx
        endpoint = settings.base_url + "/responses"

        def secure_request(request):
            if request.method != "POST" or str(request.url) != endpoint:
                raise LLMError("Qwen SDK attempted an unexpected request destination.",
                               code="unexpected_destination", stage="configuration")
            # Replace inherited SDK headers, including any OPENAI_CUSTOM_HEADERS.
            request.headers = httpx.Headers({
                "Host": request.url.host,
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Content-Length": str(len(request.content)),
                "Authorization": f"Bearer {settings.api_key}",
            })

        quiet = _QUIET_QWEN_REQUEST.set(True)
        try:
            with httpx.Client(
                follow_redirects=False, trust_env=False, event_hooks={"request": [secure_request]},
            ) as transport, sdk.OpenAI(
                api_key=settings.api_key, base_url=settings.base_url, http_client=transport,
                timeout=settings.timeout,
                max_retries=settings.max_retries if max_retries is None else max_retries,
            ) as client:
                reply = client.responses.create(
                    model=settings.model, reasoning={"effort": "none"}, store=False, **fields,
                )
        except sdk.AuthenticationError as error:
            raise LLMError("Qwen authentication failed. Verify the key and its region or workspace.",
                           code="authentication_failed", stage="request", http_status=error.status_code) from None
        except sdk.PermissionDeniedError as error:
            raise LLMError("Qwen denied access. Check workspace and model permissions.",
                           code="permission_denied", stage="request", http_status=error.status_code) from None
        except sdk.APITimeoutError:
            raise LLMError("Qwen request timed out.", code="request_timeout", stage="request") from None
        except sdk.RateLimitError as error:
            raise LLMError("Qwen rate or quota limit reached.", code="rate_limited", stage="request",
                           http_status=error.status_code) from None
        except sdk.APIConnectionError:
            raise LLMError("Qwen connection failed.", code="connection_failed", stage="request") from None
        except sdk.NotFoundError as error:
            raise LLMError("Qwen model or endpoint was not found. Check QWEN_MODEL and QWEN_BASE_URL.",
                           code="endpoint_not_found", stage="request", http_status=error.status_code) from None
        except sdk.APIStatusError as error:
            if 300 <= error.status_code < 400:
                raise LLMError("Qwen endpoint redirected the request. Redirects are disabled.",
                               code="redirect_rejected", stage="request", http_status=error.status_code) from None
            raise LLMError("Qwen rejected or failed the request. Check model compatibility and service status.",
                           code="http_request_failed", stage="request", http_status=error.status_code) from None
        except (sdk.OpenAIError, ValueError, TypeError):
            raise LLMError("Qwen returned an invalid response or the SDK could not process the request.",
                           code="sdk_response_error", stage="request") from None
        finally:
            _QUIET_QWEN_REQUEST.reset(quiet)
        return reply

    def _read_reply(self, reply) -> LLMResponse:
        if getattr(reply, "status", None) != "completed" or getattr(reply, "error", None):
            raise LLMError("Qwen returned an incomplete or failed response.", code="incomplete_response", stage="response")
        output = getattr(reply, "output", None)
        if not isinstance(output, list):
            raise LLMError("Qwen returned invalid output.", code="invalid_response_output", stage="response")
        parts = []
        for item in output:
            kind = getattr(item, "type", None)
            if kind == "reasoning":
                continue
            content = getattr(item, "content", None)
            if kind != "message" or not isinstance(content, list) or getattr(item, "status", "completed") != "completed":
                raise LLMError("Qwen returned an unexpected response item.", code="invalid_response_output", stage="response")
            for part in content:
                text = getattr(part, "text", None)
                if getattr(part, "type", None) != "output_text" or not isinstance(text, str):
                    raise LLMError("Qwen returned refused or invalid output.", code="invalid_response_output", stage="response")
                parts.append(text)
        text = "".join(parts)
        model = getattr(reply, "model", None)
        if not text.strip() or not _valid_model(model, self.settings.api_key):
            raise LLMError("Qwen returned empty output or invalid model metadata.", code="invalid_response_output", stage="response")
        host = self.settings.base_url.split("/")[2]
        if self.settings.api_key in text or host in text.lower() or host in model.lower():
            raise LLMError("Qwen returned sensitive content. The response was rejected.", code="sensitive_response", stage="response")

        usage = {}
        reported = getattr(reply, "usage", None)
        for field in ("input_tokens", "output_tokens", "total_tokens"):
            value = getattr(reported, field, None)
            if type(value) is int and value >= 0:
                usage[field] = value
        return LLMResponse(text, model, usage or None)
