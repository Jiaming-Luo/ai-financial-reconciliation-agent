"""Offline Mock and explicitly enabled Responses providers."""

import json
import math
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Protocol

from .action_catalog import REQUEST_ADDITIONAL_EVIDENCE
from .hypothesis_catalog import INSUFFICIENT_EVIDENCE
from .prompts import ANALYSIS_SCHEMA, instructions


class LLMError(RuntimeError):
    """A configuration or provider failure with a safe user-facing message."""

    def __init__(self, message: str, *, code: str | None = None, stage: str | None = None,
                 http_status: int | None = None):
        super().__init__(message)
        self.code = code
        self.stage = stage
        self.http_status = http_status


@dataclass(frozen=True)
class LLMResponse:
    text: str
    model: str
    usage: dict[str, int] | None = None


class LLMProvider(Protocol):
    name: str
    mode: str

    def generate(self, language: str, payload: dict) -> LLMResponse: ...


@dataclass(frozen=True)
class OpenAISettings:
    model: str
    api_key: str = field(repr=False)
    timeout: float = 30.0
    max_retries: int = 2

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> "OpenAISettings":
        key = env.get("LLM_API_KEY", "").strip() or env.get("OPENAI_API_KEY", "").strip()
        if not key:
            raise LLMError("OpenAI requires LLM_API_KEY or OPENAI_API_KEY.")
        model = env.get("LLM_MODEL", "").strip()
        if not model:
            raise LLMError("OpenAI requires LLM_MODEL with a Responses Structured Outputs compatible model.")
        if not _valid_model(model, key):
            raise LLMError("LLM_MODEL must be a valid model identifier.")
        timeout, retries = _request_policy(env)
        return cls(model, key, timeout, retries)


def _request_policy(env: Mapping[str, str]) -> tuple[float, int]:
    try:
        timeout = float(env.get("LLM_TIMEOUT", "30"))
        retries = int(env.get("LLM_MAX_RETRIES", "2"))
    except ValueError:
        raise LLMError("LLM_TIMEOUT and LLM_MAX_RETRIES must be numeric.") from None
    if not math.isfinite(timeout) or not 0 < timeout <= 300 or not 0 <= retries <= 5:
        raise LLMError("LLM_TIMEOUT must be in (0, 300] seconds and LLM_MAX_RETRIES in [0, 5].")
    return timeout, retries


def _valid_model(model: str, key: str) -> bool:
    return (isinstance(model, str) and bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", model))
            and not model.lower().startswith("sk-") and key not in model)


def _mock_selection(options: dict, kind: str, fallback: str) -> dict:
    code = next((code for code in options if code != fallback), fallback)
    requirements = options.get(code, {}).get("required_evidence", [])
    references = list(dict.fromkeys(
        reference for rule in requirements for reference in rule["references"][:rule["minimum"]]
    ))
    return {f"{kind}_code": code, "evidence_references": references}


class MockProvider:
    name = "mock"
    mode = "Mock"

    def generate(self, language: str, payload: dict) -> LLMResponse:
        high_priority = {"DUPLICATE_PAYMENT", "MISSING_CONTRACT", "CONTRACT_OVERLAP", "INVALID_DATA"}
        findings = []
        for item in payload["findings"]:
            findings.append({
                "anomaly_id": item["anomaly_id"],
                "anomaly_type": item["anomaly_type"],
                "evidence_references": item["evidence_references"],
                "possible_causes": [_mock_selection(item.get("cause_options", {}), "cause", INSUFFICIENT_EVIDENCE)],
                "recommended_actions": [
                    _mock_selection(item.get("action_options", {}), "action", REQUEST_ADDITIONAL_EVIDENCE),
                ],
                "priority": "HIGH" if item["anomaly_type"] in high_priority else "MEDIUM",
                "optional_analysis": None,
            })
        return LLMResponse(json.dumps({"anomaly_findings": findings}, ensure_ascii=False), "deterministic-mock")


class OpenAIProvider:
    name = "openai"
    mode = "Live"

    def __init__(self, settings: OpenAISettings):
        self.settings = settings
        try:
            import openai
        except ImportError:
            raise LLMError("The OpenAI SDK or a dependency is missing. Install requirements.txt in the project venv.") from None
        self.sdk = openai

    def generate(self, language: str, payload: dict) -> LLMResponse:
        settings, sdk = self.settings, self.sdk
        try:
            with sdk.OpenAI(
                api_key=settings.api_key,
                base_url="https://api.openai.com/v1",
                timeout=settings.timeout,
                max_retries=settings.max_retries,
            ) as client:
                response = client.responses.create(
                    model=settings.model,
                    instructions=instructions(language),
                    input=json.dumps(payload, ensure_ascii=False),
                    text={"format": {"type": "json_schema", "name": "anomaly_analysis",
                                     "strict": True, "schema": ANALYSIS_SCHEMA}},
                    max_output_tokens=10000,
                    store=False,
                )
        except sdk.AuthenticationError:
            raise LLMError("OpenAI authentication failed. Verify the configured API key.") from None
        except sdk.PermissionDeniedError:
            raise LLMError("OpenAI denied access. Check project and model permissions.") from None
        except sdk.APITimeoutError:
            raise LLMError("OpenAI request timed out after the configured retry policy.") from None
        except sdk.RateLimitError:
            raise LLMError("OpenAI limit reached after the configured retry policy. Check quota and try again later.") from None
        except sdk.APIConnectionError:
            raise LLMError("OpenAI connection failed after the configured retry policy.") from None
        except sdk.NotFoundError:
            raise LLMError("OpenAI model was not found. Check LLM_MODEL and model access.") from None
        except sdk.OpenAIError:
            raise LLMError("OpenAI rejected or failed the analysis request. Check model compatibility and service status.") from None

        if response.status != "completed" or not response.output_text.strip() or any(
            part.type == "refusal"
            for item in response.output if item.type == "message" for part in item.content
        ):
            raise LLMError("OpenAI returned an incomplete, empty or refused analysis.")
        if not _valid_model(response.model, settings.api_key):
            raise LLMError("OpenAI returned invalid model metadata.")
        if settings.api_key in response.output_text:
            raise LLMError("OpenAI returned sensitive content. The response was rejected.")
        return LLMResponse(response.output_text, response.model)


def create_provider(name: str | None = None, env: Mapping[str, str] | None = None) -> LLMProvider:
    env = os.environ if env is None else env
    selected = name if name is not None else env.get("LLM_PROVIDER", "mock")
    if selected == "mock":
        return MockProvider()
    if selected == "openai":
        return OpenAIProvider(OpenAISettings.from_env(env))
    if selected == "qwen":
        from .qwen_provider import QwenProvider, QwenSettings

        return QwenProvider(QwenSettings.from_env(env))
    raise LLMError("LLM_PROVIDER must be mock, openai or qwen.")
