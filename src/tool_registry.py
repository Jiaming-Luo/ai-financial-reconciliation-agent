"""Closed registry and local validation for Responses function calls."""

import json
import re
from dataclasses import dataclass

from .anomaly_detector import RECOMMENDED_ACTIONS
from .knowledge_base import DEFAULT_TOP_K, LANGUAGES, MAX_QUERY_LENGTH, MAX_TOP_K


MAX_LIST_RESULTS = 10
DEFAULT_LIST_RESULTS = 5
KNOWLEDGE_TOOL = "search_business_knowledge"
IDENTIFIER_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}$"
PERIOD_PATTERN = r"^(?!0000)[0-9]{4}-(?:0[1-9]|1[0-2])$"
_ID = {"type": "string", "pattern": IDENTIFIER_PATTERN}
_PERIOD = {"type": "string", "pattern": PERIOD_PATTERN}
_LIMIT = {"type": "integer", "minimum": 1, "maximum": MAX_LIST_RESULTS, "default": DEFAULT_LIST_RESULTS}
_FILTERS = {"hospital_id": _ID, "settlement_period": _PERIOD,
            "anomaly_type": {"type": "string", "enum": list(RECOMMENDED_ACTIONS)}, "limit": _LIMIT}


class ToolError(ValueError):
    """A rejected tool call with a static, safe explanation."""


class RecordNotFound(ToolError):
    """A well-formed lookup that produced no matching business record."""


class JSONObjectError(ToolError):
    """A strict JSON decoder failure with safe diagnostic metadata."""

    def __init__(self, code: str, message: str, **location: int):
        super().__init__(message)
        self.code = code
        self.location = location


def _unique_object(pairs: list) -> dict:
    value = {}
    for key, item in pairs:
        if key in value:
            raise JSONObjectError("duplicate_json_key", "JSON contains a duplicate key.")
        value[key] = item
    return value


def _invalid_constant(_value: str) -> None:
    raise JSONObjectError("invalid_json", "JSON contains a nonstandard number.")


def json_object(text: str | None, max_chars: int) -> dict:
    if not isinstance(text, str) or not text:
        raise JSONObjectError("missing_response_text", "JSON text is missing or empty.")
    if len(text) > max_chars:
        raise JSONObjectError("json_length_limit", "JSON exceeds its length limit.")
    if not text.strip():
        raise JSONObjectError("missing_response_text", "JSON text is missing or empty.")
    try:
        value = json.loads(text, object_pairs_hook=_unique_object, parse_constant=_invalid_constant)
    except JSONObjectError:
        raise
    except json.JSONDecodeError as error:
        raise JSONObjectError("invalid_json", "Expected valid JSON.", line=error.lineno, column=error.colno) from None
    except (ValueError, RecursionError):
        raise JSONObjectError("invalid_json", "Expected valid JSON within decoder limits.") from None
    if not isinstance(value, dict):
        raise JSONObjectError("invalid_json_type", "Expected a JSON object.")
    return value


@dataclass(frozen=True)
class ToolDefinition:
    description: str
    properties: dict
    required: tuple[str, ...] = ()

    def schema(self) -> dict:
        return {"type": "object", "properties": self.properties, "required": list(self.required),
                "additionalProperties": False}

    def arguments(self, text: str) -> dict:
        arguments = json_object(text, 2000)
        if not set(self.required) <= arguments.keys() or not arguments.keys() <= self.properties.keys():
            raise ToolError("Tool arguments contain missing or unexpected fields.")
        validated = {}
        for key, spec in self.properties.items():
            if key not in arguments:
                if "default" in spec:
                    validated[key] = spec["default"]
                continue
            value = arguments[key]
            if spec["type"] == "integer":
                valid = type(value) is int and spec["minimum"] <= value <= spec["maximum"]
            elif "maxLength" in spec:
                valid = (isinstance(value, str) and bool(value.strip()) and len(value) <= spec["maxLength"]
                         and all(char.isprintable() for char in value))
            else:
                valid = isinstance(value, str) and (
                    value in spec["enum"] if "enum" in spec else bool(re.fullmatch(spec["pattern"], value))
                )
            if not valid:
                raise ToolError(f"Invalid tool argument: {key}.")
            validated[key] = value
        return validated


TOOLS = {
    "get_reconciliation_summary": ToolDefinition(
        "Read portfolio totals, comparable differences, anomaly counts and held groups. Use no arguments.", {},
    ),
    "list_anomalies": ToolDefinition(
        "List engine anomalies. Optional filters use exact hospital ID, YYYY-MM or anomaly type. Returns IDs for detail lookups.",
        _FILTERS,
    ),
    "get_anomaly_details": ToolDefinition(
        "Read one anomaly by its exact ID. Returns engine amounts, evidence and manual review actions.",
        {"anomaly_id": _ID}, ("anomaly_id",),
    ),
    "get_hospital_reconciliation": ToolDefinition(
        "Read one hospital and settlement month, including balances, holds and linked anomalies.",
        {"hospital_id": _ID, "settlement_period": _PERIOD}, ("hospital_id", "settlement_period"),
    ),
    "get_review_priorities": ToolDefinition(
        "List review priorities ordered by the business rule. Optional AI suggestion priorities remain separate.",
        _FILTERS,
    ),
}
_KNOWLEDGE_DEFINITION = ToolDefinition(
    "Retrieve simulated business rules and review guidance. Use a specific topic or anomaly, without private data. "
    "Use language en or cn for the source language. A lookup can yield no evidence.",
    {"query": {"type": "string", "minLength": 1, "maxLength": MAX_QUERY_LENGTH},
     "top_k": {"type": "integer", "minimum": 1, "maximum": MAX_TOP_K, "default": DEFAULT_TOP_K},
     "language": {"type": "string", "enum": list(LANGUAGES)}}, ("query",),
)


class ToolRegistry:
    def __init__(self, tools, *, knowledge_search=None):
        self._definitions = dict(TOOLS)
        self._handlers = {name: getattr(tools, name) for name in TOOLS}
        if knowledge_search is not None:
            self._definitions[KNOWLEDGE_TOOL] = _KNOWLEDGE_DEFINITION
            self._handlers[KNOWLEDGE_TOOL] = knowledge_search
        self.provisional = tools.provisional

    def definitions(self) -> list[dict]:
        return [{"type": "function", "name": name, "description": tool.description, "parameters": tool.schema()}
                for name, tool in self._definitions.items()]

    def prepare(self, name: str, raw_arguments: str) -> dict:
        if not isinstance(name, str) or name not in self._handlers:
            raise ToolError("Tool is unavailable or unauthorized.")
        return self._definitions[name].arguments(raw_arguments)

    def execute(self, name: str, arguments: dict) -> dict:
        validated = self.prepare(name, json.dumps(arguments))
        return self._handlers[name](**validated)
