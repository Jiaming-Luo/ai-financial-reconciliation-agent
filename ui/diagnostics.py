"""Project analysis failures onto an allowlist of safe UI diagnostic fields."""

import re

from src.context_builder import ContextError
from src.llm_client import LLMError
from src.output_validator import OutputValidationError
from src.prompts import ACTION_SCHEMA, CAUSE_SCHEMA, FINDING_SCHEMA, MAX_RESPONSE_LENGTH
from ui import services
from ui.text import DIAGNOSTIC_MESSAGES


_PATH = re.compile(
    r"\$|anomaly_findings(?:\[[0-9]{1,4}\](?:\.(?:anomaly_id|anomaly_type|priority|"
    r"evidence_references(?:\[[0-9]{1,4}\])?|"
    r"(?:possible_causes|recommended_actions)(?:\[[0-9]{1,4}\](?:\.(?:cause_code|action_code|"
    r"evidence_references(?:\[[0-9]{1,4}\])?))?)?))?)?"
)
_TYPES = ("object", "array", "string", "integer", "number", "boolean", "null")
_STAGES = ("configuration", "request", "response", "validation", "context", "storage")
_CONSTRAINTS = (
    "type", "enum", "required", "additionalProperties", "minItems", "maxItems",
    "applicable_code", "eligible_code", "distinct_codes", "exclusive_fallback",
    "scoped_distinct_references", "required_evidence", "known_distinct_anomaly_id",
    "matches_engine_anomaly_type", "all_anomalies_present",
)
_ENUMS = {
    field: tuple(schema["properties"][field]["enum"])
    for field, schema in (("cause_code", CAUSE_SCHEMA), ("action_code", ACTION_SCHEMA), ("priority", FINDING_SCHEMA))
}


def analysis_diagnostic(error: Exception, *, live: bool) -> dict:
    """Never retain the exception, its message, or its chained transport objects."""
    if isinstance(error, services.AppInputError):
        code = error.args[0]
        if code in ("live_needs_confirmation", "invalid_config"):
            return {"error_code": code, "error_stage": "configuration", "model_request_count": 0}
        stage = "context" if code == "provisional_ai_block" else "storage"
        return {"error_code": code if code in DIAGNOSTIC_MESSAGES else "analysis_failed", "error_stage": stage,
                "model_request_count": 0}
    if isinstance(error, OutputValidationError):
        code = error.code if error.code in DIAGNOSTIC_MESSAGES else "schema_validation_failed"
        details = {"error_code": code, "error_stage": "validation", "model_request_count": int(live)}
        if isinstance(error.path, str) and _PATH.fullmatch(error.path):
            details["validation_path"] = error.path
            field = error.path.rsplit(".", 1)[-1]
            allowed = _ENUMS.get(field)
            if allowed and error.constraint in ("type", "enum") and error.allowed_values == allowed:
                details["allowed_values"] = list(allowed)
        if error.constraint in _CONSTRAINTS:
            details["validation_constraint"] = error.constraint
        for field in ("expected_type", "actual_type"):
            value = getattr(error, field)
            if value in _TYPES:
                details[field] = value
        length = error.actual_string_length
        if details.get("actual_type") == "string" and type(length) is int and 0 <= length <= MAX_RESPONSE_LENGTH:
            details["actual_string_length"] = length
        return details
    if isinstance(error, LLMError):
        code = error.code if error.code in DIAGNOSTIC_MESSAGES else "provider_failed"
        stage = error.stage if error.stage in _STAGES else "request"
        details = {"error_code": code, "error_stage": stage}
        if type(error.http_status) is int and 100 <= error.http_status <= 599:
            details["http_status"] = error.http_status
            details["model_request_count"] = 1
        elif stage in ("configuration", "response"):
            details["model_request_count"] = int(stage == "response" and live)
        return details
    if isinstance(error, ContextError):
        return {"error_code": "analysis_context_rejected", "error_stage": "context", "model_request_count": 0}
    if isinstance(error, OSError):
        return {"error_code": "analysis_storage_failed", "error_stage": "storage"}
    return {"error_code": "analysis_failed", "error_stage": "context"}
