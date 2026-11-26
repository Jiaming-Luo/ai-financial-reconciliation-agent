"""Validate model output against the schema and the supplied evidence."""

import json
import re
import unicodedata

from .action_catalog import ACTION_CATALOG
from .hypothesis_catalog import CATALOG, INSUFFICIENT_EVIDENCE
from .prompts import (
    ACTION_SCHEMA, ANALYSIS_SCHEMA, CAUSE_SCHEMA, FINDING_SCHEMA, MAX_NARRATIVE_LENGTH,
    MAX_RESPONSE_LENGTH, MAX_SELECTIONS, MIN_SELECTIONS, OPTIONAL_ANALYSIS,
)


class OutputValidationError(ValueError):
    """The response must not be published as an analysis report."""

    def __init__(self, message: str, *, code: str = "schema_validation_failed", path: str | None = None,
                 constraint: str | None = None, expected_type: str | None = None, actual_type: str | None = None,
                 allowed_values: tuple = (), actual_string_length: int | None = None):
        super().__init__(message)
        self.code = code
        self.path = path
        self.constraint = constraint
        self.expected_type = expected_type
        self.actual_type = actual_type
        self.allowed_values = allowed_values
        self.actual_string_length = actual_string_length


def _json_type(value) -> str | None:
    return {dict: "object", list: "array", str: "string", int: "integer", float: "number",
            bool: "boolean", type(None): "null"}.get(type(value))


class OptionalTextRejected(ValueError):
    """A redacted reason for omitting supplementary model prose."""


_MARKUP = re.compile(r"[\[\]<>#`{}]|https?\s*:|www\.", re.IGNORECASE)
_NUMERIC_CLAIMS = re.compile(
    r"[\d$€£¥]|\b(?:cny|rmb|usd|eur|yuan|dollars?|cents?|zero|nil"
    r"|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen"
    r"|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty"
    r"|seventy|eighty|ninety|hundred|thousand|million|billion)\b"
    r"|(?:人民币|[零〇一二三四五六七八九十百千万亿壹贰叁肆伍陆柒捌玖拾佰仟]+(?:元|块|分)|为零|等于零)",
    re.IGNORECASE,
)
_FINAL_CLAIMS = re.compile(
    r"\b(?:overdue|past due|is late|settled in full|no (?:balance|variance|difference)|nothing (?:due|owed)"
    r"|no (?:payment|amount) (?:is )?(?:due|owed|outstanding)"
    r"|fully (?:paid|settled)|is balanced|definitely|certainly|proved|proven|confirmed (?:root )?cause"
    r"|(?:root cause|actual cause) (?:is|was)|is the (?:actual |root )?cause"
    r"|(?:cause|reason) (?:is|was|has been) confirmed|confirmed that|without (?:any )?doubt)\b"
    r"|(?:无差额|无余额|无需付款|已结清|已付清|逾期|根因[是为]|已证实|已证明|已确认(?:原因|根因|为|是)"
    r"|(?:原因|根因)已确认|已查明|确定是|必然|无疑)",
    re.IGNORECASE,
)
_OPERATIONS = re.compile(
    r"\b(?:(?:approve|execute|initiate|release|authorize|make|issue|process|submit)\s+(?:\w+\s+){0,3}(?:payment|refund)"
    r"|(?:send|wire|transfer)\s+(?:\w+\s+){0,3}(?:funds|money)"
    r"|pay\s+(?:\w+\s+){0,3}(?:invoice|bill|vendor|supplier)"
    r"|mark\s+(?:\w+\s+){0,3}(?:as paid|as settled)"
    r"|(?:change|overwrite|delete|update|modify)\s+(?:\w+\s+){0,3}(?:results|ledger|records|files)"
    r"|run (?:a |the )?(?:command|script)|ignore (?:the |all )?(?:rules|instructions))\b"
    r"|(?:执行付款|发起付款|拨款|审批付款|发起转账|立即付款|请转账|请付款|修改对账|覆盖结果"
    r"|删除记录|运行脚本|忽略指令)",
    re.IGNORECASE,
)
_TEXT_RULES = (
    ("plain_text", _MARKUP), ("financial_numbers", _NUMERIC_CLAIMS),
    ("unverified_conclusion", _FINAL_CLAIMS), ("unauthorized_operation", _OPERATIONS),
)



def _pairs(items: list) -> dict:
    result = {}
    for key, value in items:
        if key in result:
            raise OutputValidationError("Model JSON contains a duplicate key.", code="duplicate_json_key")
        result[key] = value
    return result


def _invalid_json_constant(_value: str) -> None:
    raise OutputValidationError("$: expected standard JSON without non-finite constants.", code="invalid_json", path="$")


def _string_field(value, spec: dict, path: str, message: str) -> None:
    allowed = tuple(spec.get("enum", ()))
    actual_type = _json_type(value)
    if actual_type != spec["type"] or (allowed and value not in allowed):
        constraint = "type" if actual_type != spec["type"] else "enum"
        raise OutputValidationError(f"{path}: {message}", path=path, constraint=constraint,
                                    expected_type=spec["type"], actual_type=actual_type, allowed_values=allowed,
                                    actual_string_length=len(value) if isinstance(value, str) else None)


def _shape(value, schema: dict, path: str, *, allow_missing: str | None = None) -> None:
    if not isinstance(value, dict):
        raise OutputValidationError(f"{path}: expected a JSON object, got {type(value).__name__}.", path=path,
                                    constraint="type", expected_type="object", actual_type=_json_type(value))
    fields = schema["properties"].keys()
    missing = set(schema["required"]) - value.keys()
    missing.discard(allow_missing)
    extra_count = len(value.keys() - fields) if not schema["additionalProperties"] else 0
    if missing or extra_count:
        raise OutputValidationError(
            f"{path}: Model JSON has missing or unexpected fields "
            f"(missing: {', '.join(sorted(missing)) or 'none'}, unexpected field count: {extra_count}).",
            path=path, constraint="required" if missing else "additionalProperties",
            expected_type="object", actual_type="object",
        )


def _check_optional_text(text) -> None:
    if not isinstance(text, str) or not text.strip() or len(text) > MAX_NARRATIVE_LENGTH:
        raise OptionalTextRejected("narrative_size")
    normalized = unicodedata.normalize("NFKC", text)
    if any(unicodedata.category(char).startswith("C") or char in "\u2028\u2029" for char in normalized):
        raise OptionalTextRejected("plain_text")
    for rule, pattern in _TEXT_RULES:
        if pattern.search(normalized):
            raise OptionalTextRejected(rule)


def optional_analysis(value, path: str) -> tuple[str | None, dict | None]:
    """Return only safe supplementary text or a content-free warning."""
    if value is None:
        return None, None
    try:
        _check_optional_text(value)
    except OptionalTextRejected as error:
        return None, {"path": path, "rule": str(error)}
    return value, None


def _bounded_list(value, path: str) -> None:
    expected = f"a JSON array with {MIN_SELECTIONS} to {MAX_SELECTIONS} entries"
    if not isinstance(value, list):
        raise OutputValidationError(f"{path}: expected {expected}, got {type(value).__name__} (no item count).",
                                    path=path, constraint="type", expected_type="array", actual_type=_json_type(value))
    count = len(value)
    if not MIN_SELECTIONS <= count <= MAX_SELECTIONS:
        raise OutputValidationError(f"{path}: expected {expected}, got {count} entries.", path=path,
                                    constraint="minItems" if count < MIN_SELECTIONS else "maxItems",
                                    expected_type="array", actual_type="array")


def _reference_list(value, spec: dict, path: str, message: str) -> None:
    if not isinstance(value, list):
        raise OutputValidationError(f"{path}: {message}", path=path, constraint="type",
                                    expected_type=spec["type"], actual_type=_json_type(value))
    for index, reference in enumerate(value):
        _string_field(reference, spec["items"], f"{path}[{index}]", message)


def _selections(value, source: dict, finding_references: list[str], path: str, kind: str) -> None:
    _bounded_list(value, path)
    used_codes = set()
    catalog, schema = (CATALOG, CAUSE_SCHEMA) if kind == "cause" else (ACTION_CATALOG, ACTION_SCHEMA)
    code_field = f"{kind}_code"
    options = source.get(f"{kind}_options", {})
    for index, selection in enumerate(value):
        item = f"{path}[{index}]"
        _shape(selection, schema, item)
        code = selection[code_field]
        code_path = f"{item}.{code_field}"
        _string_field(code, schema["properties"][code_field], code_path,
                      f"expected a defined catalog code [unknown_{kind}].")
        code_metadata = {"path": code_path, "expected_type": "string", "actual_type": "string",
                         "actual_string_length": len(code)}
        entry = catalog[code]
        if source["anomaly_type"] not in entry.applicable_anomaly_types or entry.review_required is not True:
            raise OutputValidationError(
                f"{code_path}: code is inapplicable or does not require manual review [{kind}_type].",
                code="evidence_validation_failed", constraint="applicable_code", **code_metadata,
            )
        if code in used_codes:
            raise OutputValidationError(f"{code_path}: use distinct codes [{kind}_selection].",
                                        code="business_validation_failed", constraint="distinct_codes", **code_metadata)
        if code == INSUFFICIENT_EVIDENCE and len(value) != 1:
            raise OutputValidationError(
                f"{code_path}: use INSUFFICIENT_EVIDENCE alone [cause_selection].",
                code="business_validation_failed", constraint="exclusive_fallback", **code_metadata,
            )
        used_codes.add(code)
        refs = selection["evidence_references"]
        ref_path = f"{item}.evidence_references"
        ref_message = f"expected distinct references from this finding [{kind}_references]."
        _reference_list(refs, schema["properties"]["evidence_references"], ref_path, ref_message)
        if any(ref not in finding_references for ref in refs) or len(set(refs)) != len(refs):
            raise OutputValidationError(
                f"{ref_path}: {ref_message}", code="evidence_validation_failed", path=ref_path,
                constraint="scoped_distinct_references", expected_type="array", actual_type="array",
            )
        if not entry.required_evidence:
            continue
        option = options.get(code)
        if option is None:
            raise OutputValidationError(
                f"{code_path}: this finding lacks required evidence for the code [{kind}_unavailable].",
                code="evidence_validation_failed", constraint="eligible_code", **code_metadata,
            )
        cited = set(refs)
        for requirement in option["required_evidence"]:
            if len(cited.intersection(requirement["references"])) < requirement["minimum"]:
                raise OutputValidationError(
                    f"{ref_path}: required evidence was not cited [{kind}_evidence_missing].",
                    code="evidence_validation_failed", path=ref_path, constraint="required_evidence",
                )




def validate_output(raw: str, payload: dict) -> dict:
    """Validate the mandatory contract before inspecting supplementary model text."""
    if not isinstance(raw, str) or len(raw) > MAX_RESPONSE_LENGTH:
        raise OutputValidationError(f"$: Model output is missing or exceeds {MAX_RESPONSE_LENGTH} characters.",
                                    code="invalid_response_output", path="$")
    try:
        result = json.loads(raw, object_pairs_hook=_pairs, parse_constant=_invalid_json_constant)
    except json.JSONDecodeError as error:
        raise OutputValidationError(f"$: Model output is not valid JSON at line {error.lineno}, column {error.colno}.",
                                    code="invalid_json", path="$") from None
    except OutputValidationError:
        raise
    except (ValueError, RecursionError):
        raise OutputValidationError("Model output is not valid JSON.", code="invalid_json") from None
    _shape(result, ANALYSIS_SCHEMA, "$")
    if not isinstance(result["anomaly_findings"], list):
        raise OutputValidationError("anomaly_findings must be a list.", path="anomaly_findings",
                                    constraint="type", expected_type="array", actual_type=_json_type(result["anomaly_findings"]))

    fields = FINDING_SCHEMA["properties"]
    expected = {item["anomaly_id"]: item for item in payload["findings"]}
    seen = set()
    for index, finding in enumerate(result["anomaly_findings"]):
        path = f"anomaly_findings[{index}]"
        _shape(finding, FINDING_SCHEMA, path, allow_missing=OPTIONAL_ANALYSIS)
        anomaly_id = finding["anomaly_id"]
        _string_field(anomaly_id, fields["anomaly_id"], f"{path}.anomaly_id", "expected a string anomaly ID.")
        if anomaly_id not in expected or anomaly_id in seen:
            raise OutputValidationError(f"{path}.anomaly_id: Model cited an unknown or repeated anomaly ID.",
                                        code="evidence_validation_failed", path=f"{path}.anomaly_id",
                                        constraint="known_distinct_anomaly_id", expected_type="string",
                                        actual_type="string", actual_string_length=len(anomaly_id))
        source = expected[anomaly_id]
        seen.add(anomaly_id)
        anomaly_type = finding["anomaly_type"]
        _string_field(anomaly_type, fields["anomaly_type"], f"{path}.anomaly_type", "expected a string anomaly type.")
        if anomaly_type != source["anomaly_type"]:
            raise OutputValidationError(f"{path}.anomaly_type: Model anomaly type does not match the engine evidence.",
                                        code="evidence_validation_failed", path=f"{path}.anomaly_type",
                                        constraint="matches_engine_anomaly_type", expected_type="string",
                                        actual_type="string", actual_string_length=len(anomaly_type))

        references = finding["evidence_references"]
        allowed = source["evidence_references"]
        ref_path = f"{path}.evidence_references"
        ref_message = "Model evidence references are unsupported, repeated or missing."
        _reference_list(references, fields["evidence_references"], ref_path, ref_message)
        if (any(ref not in allowed for ref in references)
                or len(set(references)) != len(references) or bool(allowed) != bool(references)):
            raise OutputValidationError(f"{ref_path}: {ref_message}", code="evidence_validation_failed", path=ref_path,
                                        constraint="scoped_distinct_references", expected_type="array", actual_type="array")
        _string_field(finding["priority"], fields["priority"], f"{path}.priority", "expected a priority from the schema enum.")
        _selections(finding["possible_causes"], source, references, f"{path}.possible_causes", "cause")
        _selections(finding["recommended_actions"], source, references, f"{path}.recommended_actions", "action")
    if seen != expected.keys():
        raise OutputValidationError(f"anomaly_findings: Model omitted {len(expected.keys() - seen)} engine finding(s).",
                                    code="evidence_validation_failed", path="anomaly_findings",
                                    constraint="all_anomalies_present")
    return result
