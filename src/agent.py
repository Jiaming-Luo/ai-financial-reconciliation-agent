"""Bounded Responses function calling with engine-owned answer values."""

import json
import re
from dataclasses import dataclass, replace
from time import perf_counter
from typing import Protocol

from .agent_prompts import (
    ANSWER_STATUSES, FIELD_LABELS_CN, MAX_ANSWER_CITATIONS, TEXT, allowed_answer_statuses, answer_schema, instructions,
)
from .llm_client import LLMError, _valid_model
from .qwen_provider import QwenProvider, QwenSettings, structured_output_body
from .tool_registry import KNOWLEDGE_TOOL, JSONObjectError, RecordNotFound, ToolError, ToolRegistry, json_object


MAX_MODEL_REQUESTS = 5
MAX_TOOL_CALLS = 8
MAX_OUTPUT_TOKENS = 1024
MAX_RESULT_BYTES = 12_000
MAX_HISTORY_BYTES = 88_000
MAX_QUESTION_LENGTH = 3000
USAGE_KEYS = ("input_tokens", "output_tokens", "total_tokens")
_CALL_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}")
HOSPITAL_TOOL = "get_hospital_reconciliation"
MOCK_SCENARIOS = ("summary", "hospital", "multi", "knowledge", "combined")
HOSPITAL_AMOUNT_FIELDS = ("expected_amount", "paid_amount", "difference_amount", "eligible_paid_amount")
HOSPITAL_ANSWER_FIELDS = (
    "hospital_id", "settlement_period", "settlement_status", "review_required", "currency",
    "payment_bucket", *HOSPITAL_AMOUNT_FIELDS, "anomaly_types", "anomalies", "matched_count", "truncated",
)
_REQUIRED_EVIDENCE_FIELDS = {
    "get_reconciliation_summary": ("run_status", "currency", "difference_definition", "net_difference", "held_group_count"),
    "list_anomalies": ("anomalies", "matched_count", "truncated"),
    "get_anomaly_details": ("anomaly_id", "anomaly_type", "currency", "amounts", "group_amounts", "manual_review_actions"),
    HOSPITAL_TOOL: HOSPITAL_ANSWER_FIELDS,
    "get_review_priorities": ("priorities", "matched_count", "truncated", "business_priority_policy", "ai_priority_source"),
    KNOWLEDGE_TOOL: ("matches", "simulation", "review_required"),
}
_JSON_TYPES = {str: "string", list: "array", dict: "object", int: "integer", float: "number", bool: "boolean", type(None): "null"}


class AgentError(ValueError):
    """The agent cannot produce a verified answer."""


class AgentResponseError(AgentError):
    """A response failure with diagnostic fields that can be shown to users."""

    def __init__(self, code: str, message: str, *, stage: str = "final_answer", **metadata):
        super().__init__(message)
        self.details = {"code": code, "stage": stage, **metadata}


@dataclass(frozen=True)
class FunctionCall:
    call_id: str
    name: str
    arguments: str

    def input_item(self) -> dict:
        return {"type": "function_call", "name": self.name, "arguments": self.arguments, "call_id": self.call_id}


@dataclass(frozen=True)
class AgentTurn:
    model: str
    calls: tuple[FunctionCall, ...] = ()
    answer_plan: str | None = None
    usage: dict | None = None


class AgentProvider(Protocol):
    name: str
    mode: str

    def respond(self, language: str, history: list[dict], tools: list[dict],
                *, evidence_refs: tuple[str, ...]) -> AgentTurn: ...


class QwenAgentProvider:
    name, mode = "qwen", "Live"

    def __init__(self, settings: QwenSettings):
        self._transport = QwenProvider(replace(settings, timeout=min(settings.timeout, 60), max_retries=0))

    def respond(self, language: str, history: list[dict], tools: list[dict],
                *, evidence_refs: tuple[str, ...]) -> AgentTurn:
        try:
            reply = self._transport.create_response(
                input=history, instructions=instructions(language, evidence_refs), tools=tools, tool_choice="auto",
                extra_body=structured_output_body("agent_answer", answer_schema(evidence_refs)),
                max_output_tokens=MAX_OUTPUT_TOKENS, max_retries=0,
            )
        except LLMError as error:
            raise AgentResponseError("request_failed", str(error), stage="request") from None
        settings = self._transport.settings
        model = getattr(reply, "model", None)
        output = getattr(reply, "output", None)
        status = getattr(reply, "status", None)
        if status in ("incomplete", "queued", "in_progress"):
            reason = getattr(getattr(reply, "incomplete_details", None), "reason", None)
            details = {"response_status": status}
            if reason in ("max_output_tokens", "content_filter"):
                details["reason"] = reason
            raise AgentResponseError("incomplete_response", "Qwen did not complete the response.", stage="response", **details)
        if status != "completed" or getattr(reply, "error", None):
            raise AgentResponseError("failed_response", "Qwen returned a failed or invalid response status.", stage="response")
        if not isinstance(output, list) or not _valid_model(model, settings.api_key):
            raise AgentResponseError("invalid_response_output", "Qwen returned invalid output or model metadata.", stage="response")
        calls, text = [], []
        refusal = False
        for item in output:
            kind = getattr(item, "type", None)
            if kind == "reasoning":
                continue
            status = getattr(item, "status", None)
            if status not in (None, "completed"):
                stage = "final_answer" if kind == "message" else "response"
                raise AgentResponseError("incomplete_response", "Qwen returned an incomplete function or message.", stage=stage)
            if kind == "function_call":
                calls.append(FunctionCall(getattr(item, "call_id", None), getattr(item, "name", None),
                                          getattr(item, "arguments", None)))
                continue
            parts = getattr(item, "content", None)
            if kind != "message" or getattr(item, "role", None) != "assistant" or not isinstance(parts, list):
                raise AgentResponseError("invalid_response_output", "Qwen returned an unsupported output item.", stage="response")
            for part in parts:
                part_type = getattr(part, "type", None)
                if part_type == "refusal":
                    refusal = True
                elif part_type == "output_text" and isinstance(getattr(part, "text", None), str):
                    text.append(part.text)
                else:
                    raise AgentResponseError("invalid_response_output", "Qwen returned an unsupported message part.")
        if refusal and calls:
            raise AgentResponseError("invalid_response_output", "Qwen combined a refusal with function calls.", stage="response")
        plan = '{"status":"refused","citations":[]}' if refusal else "".join(text)
        values = [model, plan, *(value for call in calls for value in (call.call_id, call.name, call.arguments))]
        host = settings.base_url.split("/")[2]
        if any(isinstance(value, str) and (settings.api_key in value or host in value.lower()) for value in values):
            raise AgentResponseError("sensitive_response", "Qwen returned sensitive content. The response was rejected.", stage="response")
        usage = {field: getattr(getattr(reply, "usage", None), field, None) for field in USAGE_KEYS}
        return AgentTurn(model, tuple(calls), None if calls else plan, usage)


class MockAgentProvider:
    """Explicit scripted scenarios for exercising the same protocol offline."""

    name, mode = "mock", "Mock"
    model = "scripted-tool-demo"

    def __init__(self, scenario: str = "summary"):
        if scenario not in MOCK_SCENARIOS:
            raise AgentError("Unknown Mock scenario.")
        self.scenario = scenario

    def respond(self, language: str, history: list[dict], tools: list[dict],
                *, evidence_refs: tuple[str, ...]) -> AgentTurn:
        outputs = [json.loads(item["output"]) for item in history if item["type"] == "function_call_output"]
        if not outputs:
            hospital_lookup = (HOSPITAL_TOOL, {"hospital_id": "SIM-H004", "settlement_period": "2026-05"})
            name, arguments = {
                "summary": ("get_reconciliation_summary", {}),
                "hospital": hospital_lookup,
                "multi": ("list_anomalies", {"anomaly_type": "PRICE_MISMATCH", "limit": 1}),
                "knowledge": (KNOWLEDGE_TOOL, {"query": history[0]["content"]}),
                "combined": hospital_lookup,
            }[self.scenario]
            return AgentTurn(self.model, (FunctionCall("mock_call_1", name, json.dumps(arguments)),))
        first = outputs[0]
        if self.scenario == "multi" and len(outputs) == 1 and first.get("data", {}).get("anomalies"):
            anomaly_id = first["data"]["anomalies"][0]["anomaly_id"]
            return AgentTurn(self.model, (FunctionCall("mock_call_2", "get_anomaly_details", json.dumps({"anomaly_id": anomaly_id})),))
        if self.scenario == "combined" and len(outputs) == 1 and first.get("data", {}).get("anomaly_types"):
            query = " ".join(first["data"]["anomaly_types"])
            return AgentTurn(self.model, (FunctionCall("mock_call_2", KNOWLEDGE_TOOL, json.dumps({"query": query})),))
        if any(item["status"] != "ok" for item in outputs):
            plan = {"status": "insufficient_evidence", "citations": []}
        else:
            plan = {"status": "answered", "citations": evidence_refs}
        return AgentTurn(self.model, answer_plan=json.dumps(plan))


def _answer_status(plan: dict, *, has_evidence: bool) -> str:
    status = plan.get("status")
    missing = "status" not in plan
    details = {
        "path": "$.status",
        "field_missing": missing,
        "expected_type": "string",
        "actual_type": "missing" if missing else _JSON_TYPES[type(status)],
        "allowed_values": list(allowed_answer_statuses(has_evidence=has_evidence)),
    }
    if missing:
        raise AgentResponseError("schema_validation_failed", "The answer status is missing.", category="missing_status", **details)
    if not isinstance(status, str):
        category = "null_status" if status is None else "invalid_status_type"
        raise AgentResponseError("invalid_field_type", "The answer status must be a string.", category=category, **details)
    if status not in ANSWER_STATUSES:
        category = "empty_status" if not status.strip() else "invalid_status_value"
        raise AgentResponseError("schema_validation_failed", "The answer status is not allowed.",
                                 category=category, value_length=len(status), **details)
    # Evidence validation below also rejects an answered status when there are no valid citations.
    return status


def _answer(plan: str | None, evidence: dict) -> tuple[str, list[dict]]:
    try:
        value = json_object(plan, 8000)
    except JSONObjectError as error:
        raise AgentResponseError(error.code, str(error), **error.location) from None
    status = _answer_status(value, has_evidence=bool(evidence))
    expected_fields = {"status", "citations"}
    missing_fields = expected_fields - value.keys()
    if missing_fields:
        raise AgentResponseError("schema_validation_failed", "The answer plan is missing required properties.",
                                 path="$", missing_fields=sorted(missing_fields))
    if value.keys() - expected_fields:
        raise AgentResponseError("unknown_evidence_field", "The answer plan contains unsupported properties.",
                                 path="$", actual_type="object", allowed_fields=sorted(expected_fields),
                                 unexpected_count=len(value.keys() - expected_fields))
    citations = value["citations"]
    if not isinstance(citations, list):
        raise AgentResponseError("invalid_field_type", "The answer property has an invalid type.",
                                 path="$.citations", expected_type="array", actual_type=_JSON_TYPES[type(citations)])
    maximum = min(len(evidence), MAX_ANSWER_CITATIONS) if status == "answered" else 0
    if status == "answered" and not citations:
        raise AgentResponseError("missing_required_evidence", "A financial answer requires at least one verified tool citation.",
                                 path="$.citations", min_items=1, actual_count=0, available_count=len(evidence))
    if len(citations) > MAX_ANSWER_CITATIONS or (status != "answered" and citations):
        raise AgentResponseError("invalid_citation_length", "The citation list exceeds its allowed length.",
                                 path="$.citations", max_items=maximum, actual_count=len(citations))

    sections = []
    used = set()
    for index, ref in enumerate(citations):
        location = {"path": f"$.citations[{index}]", "citation_index": index}
        if not isinstance(ref, str):
            raise AgentResponseError("invalid_reference_type", "Each citation must be a string evidence reference.",
                                     **location, expected_type="string", actual_type=_JSON_TYPES[type(ref)])
        if ref not in evidence:
            raise AgentResponseError("unknown_evidence_reference", "The citation refers to unavailable tool evidence.",
                                     **location, available_count=len(evidence), available_refs=list(evidence))
        if ref in used:
            raise AgentResponseError("duplicate_evidence_reference", "The answer plan repeats an evidence reference.", **location)
        row = evidence[ref]
        data = row["data"]
        missing = [key for key in _REQUIRED_EVIDENCE_FIELDS[row["tool"]] if key not in data]
        if row["tool"] == KNOWLEDGE_TOOL and "matches" in data and not data["matches"]:
            missing.append("matches")
        if missing:
            raise AgentResponseError("missing_required_evidence", "The cited tool evidence is missing required fields.",
                                     **location, missing_fields=missing)
        used.add(ref)
        sections.append({**row, "data": data.copy()})
    return status, sections


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def run_agent(question: str, language: str, provider: AgentProvider, registry: ToolRegistry) -> dict:
    """Execute one bounded question. A failed run never returns answer sections."""
    started = perf_counter()
    history = [{"type": "message", "role": "user", "content": question}]
    trace, evidence, sections = [], {}, []
    usage_total = dict.fromkeys(USAGE_KEYS, 0)
    usage_complete = True
    call_ids, signatures = set(), set()
    request_count, reported_requests, failed_turns = 0, 0, 0
    model, error, error_details = None, None, None
    try:
        if language not in TEXT or not isinstance(question, str) or not question.strip() or len(question) > MAX_QUESTION_LENGTH:
            raise AgentError("Provide a non-empty question of at most 3,000 characters and a supported language.")
        definitions = registry.definitions()
        for _ in range(MAX_MODEL_REQUESTS):
            if len(_json(history).encode("utf-8")) > MAX_HISTORY_BYTES:
                raise AgentError("The model input reached its byte limit.")
            request_count += 1
            turn = provider.respond(language, history, definitions, evidence_refs=tuple(evidence))
            reported_requests += 1
            model = turn.model
            usage_complete &= turn.usage is not None and all(
                type(turn.usage.get(key)) is int and turn.usage[key] >= 0 for key in USAGE_KEYS
            )
            if usage_complete:
                for key in USAGE_KEYS:
                    usage_total[key] += turn.usage[key]
            if not turn.calls:
                status, sections = _answer(turn.answer_plan, evidence)
                break
            if request_count == MAX_MODEL_REQUESTS:
                raise AgentError("The model request limit was reached before a final answer.")
            if len(trace) + len(turn.calls) > MAX_TOOL_CALLS:
                raise AgentError("The proposed batch exceeds the tool execution limit.")

            prepared = []
            for call in turn.calls:
                if not isinstance(call.call_id, str) or not _CALL_ID.fullmatch(call.call_id) or call.call_id in call_ids:
                    raise AgentError("The model returned an invalid or repeated call ID.")
                try:
                    args = registry.prepare(call.name, call.arguments)
                except JSONObjectError as issue:
                    raise AgentResponseError(issue.code, str(issue), stage="tool_arguments", **issue.location) from None
                signature = call.name, _json(args)
                if signature in signatures:
                    raise AgentError("A repeated tool call was stopped to prevent a loop.")
                signatures.add(signature)
                call_ids.add(call.call_id)
                prepared.append((call, args))

            successful = False
            for call, args in prepared:
                event = {"name": call.name, "arguments": args, "call_id": call.call_id, "model_request": request_count}
                trace.append(event)
                try:
                    tool_result = registry.execute(call.name, args)
                    knowledge = call.name == KNOWLEDGE_TOOL
                    prefix = "K" if knowledge else "E"
                    ref = f"{prefix}{1 + sum(key.startswith(prefix) for key in evidence)}"
                    result = {"status": "ok", "ref": ref, "evidence_type": "knowledge" if knowledge else "financial", **tool_result}
                except RecordNotFound as issue:
                    result = {"status": "not_found", "reason": str(issue)}
                serialized = _json(result)
                if len(serialized.encode("utf-8")) > MAX_RESULT_BYTES:
                    raise AgentError("A tool result exceeded its byte limit. Narrow the query.")
                event["result"] = result
                if result["status"] == "ok":
                    evidence[ref] = {**result, "tool": call.name, "arguments": args}
                    successful = True
                history.extend([call.input_item(), {
                    "type": "function_call_output", "call_id": call.call_id, "output": serialized,
                }])
            failed_turns = 0 if successful else failed_turns + 1
            if failed_turns >= 2:
                raise AgentError("Two consecutive tool turns produced no evidence.")
    except AgentResponseError as issue:
        status, error = "failed", str(issue)
        error_details = {**issue.details, "model_request": request_count}
    except (AgentError, LLMError, ToolError) as issue:
        status, error = "failed", str(issue)

    return {
        "status": status, "error": error, "error_details": error_details,
        "provider": provider.name, "run_mode": provider.mode, "model": model,
        "provisional": registry.provisional, "requires_human_review": True,
        "model_requests": request_count, "tool_calls": len(trace), "tool_trace": trace, "answer_sections": sections,
        "usage": usage_total if usage_complete and reported_requests == request_count and request_count else None,
        "elapsed_seconds": round(perf_counter() - started, 3),
    }


def render_answer(result: dict, language: str) -> str:
    labels = TEXT[language]
    chinese = FIELD_LABELS_CN if language == "cn" else {}

    def shown(value):
        if value is None:
            return labels["unknown"]
        if isinstance(value, dict):
            return {chinese.get(key, key): shown(item) for key, item in value.items()}
        if isinstance(value, list):
            return [shown(item) for item in value]
        return value

    lines = []
    if result["run_mode"] == "Mock":
        lines.append(labels["mock"])
    if result["provisional"]:
        lines.append(labels["scope"])
    lines.append(labels[result["status"]])
    if result["error"]:
        lines.append(result["error"])
    for section in result["answer_sections"]:
        if section.get("evidence_type") == "knowledge":
            lines.append(f"[{section['ref']}] {labels['knowledge_evidence']}")
            for match in section["data"]["matches"]:
                lines.extend((
                    f"- {match['document_title']} [{match['document_id']} §{match['section_id']} · v{match['version']} · {match['language']}]",
                    f"  {match['section_title']} · {match['source_file']}",
                    f"  {labels['knowledge_scope']} · {match['scope']}",
                    f"  {labels['knowledge_excerpt']} · {match['excerpt']}",
                    f"  {labels['knowledge_review']} · {match['review_guidance']}",
                ))
            lines.append(labels["knowledge_limit"])
            continue
        lines.append(f"[{section['ref']}] {section['tool']} {_json(section['arguments'])} · {', '.join(section['source_files'])}")
        for field, raw in section["data"].items():
            label = chinese.get(field, field.replace("_", " ").capitalize())
            unknown_amount = section["tool"] == HOSPITAL_TOOL and field in HOSPITAL_AMOUNT_FIELDS and raw is None
            value = labels["undetermined_amount"] if unknown_amount else shown(raw)
            lines.append(f"- {label} · {_json(value) if isinstance(value, (list, dict)) else value}")
    if any(section.get("evidence_type") != "knowledge" for section in result["answer_sections"]):
        lines.append(labels["amount_policy"])
    if (result["status"] == "answered"
            and not any(section.get("evidence_type") == "knowledge" for section in result["answer_sections"])
            and any(event["name"] == KNOWLEDGE_TOOL and event.get("result", {}).get("status") == "not_found"
                    for event in result["tool_trace"])):
        lines.append(labels["knowledge_unavailable"])
    lines.append(labels["review"])
    return "\n".join(lines)
