"""Project reconciliation reports onto a small, read-only analysis context."""

import csv
import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from .action_catalog import eligible_actions
from .anomaly_detector import RECOMMENDED_ACTIONS
from .hypothesis_catalog import eligible_hypotheses


SOURCE_FILES = ("summary.json", "anomaly_details.csv", "reconciliation_results.csv")
COUNT_FIELDS = (
    "settlement_group_count", "anomalous_group_count", "held_group_count",
    "comparable_group_count", "unassigned_issue_count",
)
TOTAL_FIELDS = (
    "reliable_receivable_amount", "comparable_receivable_amount",
    "comparable_paid_amount", "net_difference", "held_eligible_payment_amount",
    "unmatched_payment_amount",
)
GROUP_AMOUNTS = ("expected_amount", "paid_amount", "difference_amount")
FINDING_AMOUNTS = ("expected_amount", "actual_amount", "difference_amount")
STATUSES = {
    "MATCHED", "MISSING_PAYMENT", "UNDERPAYMENT", "OVERPAYMENT",
    "UNMATCHED_PAYMENT", "REVIEW_REQUIRED",
}
SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}")


class ContextError(ValueError):
    """The financial reports cannot support the requested analysis."""


@dataclass
class AnalysisContext:
    summary: dict
    findings: dict

    @property
    def provisional(self) -> bool:
        return self.summary["run_status"] == "INCOMPLETE_INPUT"

    def model_input(self, language: str) -> dict:
        findings = []
        for item in self.findings.values():
            hospital = item["hospital_id"]
            findings.append({
                "anomaly_id": item["anomaly_id"],
                "anomaly_type": item["anomaly_type"],
                "hospital_id": hospital if hospital and SAFE_ID.fullmatch(hospital) else None,
                "settlement_period": item["settlement_period"],
                "evidence_references": list(item["reference_map"]),
                "cause_options": eligible_hypotheses(item["anomaly_type"], item["review_evidence"]),
                "action_options": eligible_actions(item["anomaly_type"], item["review_evidence"]),
                "settlement_status": item["settlement_status"],
                "payment_reference_resolution": item["payment_reference_resolution"],
                "available_finding_amounts": {
                    field: value is not None for field, value in item["amounts"].items()
                },
                "available_group_amounts": {
                    field: value is not None for field, value in item["group_amounts"].items()
                },
            })
        return {
            "language": language,
            "analysis_scope": "REVIEW_ONLY" if self.provisional else "ANOMALY_ANALYSIS",
            "run_status": self.summary["run_status"],
            "findings": findings,
        }


def _read_rows(path: Path, required: tuple) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as source:
        reader = csv.DictReader(source, strict=True)
        columns = reader.fieldnames or []
        if len(columns) != len(set(columns)) or not set(required) <= set(columns):
            raise ContextError(f"{path.name} is missing required columns or has duplicate columns.")
        rows = list(reader)
        if any(None in row or any(row[key] is None for key in required) for row in rows):
            raise ContextError(f"{path.name} contains a malformed row.")
        return rows


def _money(value) -> str | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str) or not re.fullmatch(r"-?[0-9]+\.[0-9]{2}", value):
        raise ContextError("A report contains an invalid authoritative amount.")
    return value


def _project_summary(data) -> dict:
    if not isinstance(data, dict) or data.get("run_status") not in ("COMPLETED", "INCOMPLETE_INPUT"):
        raise ContextError("The financial engine status is missing or unsuitable for analysis.")
    if data.get("currency") != "CNY" or data.get("difference_definition") != "expected_amount - paid_amount":
        raise ContextError("The financial report uses an unsupported currency or difference definition.")
    count_keys = (*COUNT_FIELDS, "contract_record_count", "service_record_count",
                  "raw_payment_count", "eligible_payment_count", "normal_group_count",
                  "review_required_group_count", "unmatched_payment_group_count")
    if any(type(data.get(key)) is not int or data[key] < 0 for key in count_keys):
        raise ContextError("The financial summary is missing a valid count.")
    anomaly_counts = data.get("anomaly_counts")
    if (not isinstance(anomaly_counts, dict) or set(anomaly_counts) != set(RECOMMENDED_ACTIONS)
            or any(type(value) is not int or value < 0 for value in anomaly_counts.values())):
        raise ContextError("The financial summary is missing valid anomaly counts.")
    amount_keys = (*TOTAL_FIELDS, "eligible_payment_amount", "missing_payment_amount",
                   "underpayment_amount", "overpayment_amount", "total_shortfall_amount")
    if not set(amount_keys) <= data.keys():
        raise ContextError("The financial summary is missing required amount fields.")
    return {
        "run_status": data["run_status"], "currency": "CNY",
        "difference_definition": data["difference_definition"],
        **{key: data[key] for key in count_keys},
        **{key: _money(data[key]) for key in amount_keys},
        "anomaly_counts": anomaly_counts,
    }


def _group(row: dict) -> tuple[str, str] | None:
    hospital, period = row["hospital_id"], row["settlement_period"]
    if not hospital and not period:
        return None
    if not hospital or not re.fullmatch(r"[0-9]{4}-(?:0[1-9]|1[0-2])", period):
        raise ContextError("A report contains an invalid settlement group.")
    return hospital, period


def _strings(value) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) and item for item in value)


def _review_evidence(kind: str, evidence: dict, reference_map: dict, resolution: str | None) -> dict:
    """Project evidence roles onto the existing scoped reference aliases."""
    aliases = {source: alias for alias, source in reference_map.items()}

    def scoped(values) -> list[str]:
        if not isinstance(values, list):
            return []
        return list(dict.fromkeys(aliases[value] for value in values if isinstance(value, str) and value in aliases))

    payment_rows = evidence.get("sources" if kind == "DUPLICATE_PAYMENT" else "eligible_payments")
    payments = []
    if isinstance(payment_rows, list):
        for row in payment_rows:
            raw = row.get("raw") if isinstance(row, dict) else None
            if isinstance(raw, dict):
                payments.append(raw.get("payment_id"))

    services = [evidence.get("service_id")]
    service_count = evidence.get("service_record_count")
    if kind == "MISSING_PAYMENT" and type(service_count) is int and service_count > 0 and payment_rows == []:
        services = list(aliases)
    invalid_records = []
    if kind == "INVALID_DATA" and isinstance(evidence.get("source"), dict):
        invalid_records = scoped(services) or list(reference_map)
    return {
        "service_record": scoped(services),
        "payment_record": scoped(payments),
        "matched_contract": scoped([evidence.get("contract_id")]),
        "contract_candidate": scoped(evidence.get("candidate_contract_ids")),
        "exact_duplicate_payment": scoped(payments) if resolution == "EXACT_COPY_COUNTED_ONCE" else [],
        "invalid_source_record": invalid_records,
    }


def _findings(anomalies: list[dict], settlements: list[dict], summary: dict) -> dict:
    groups = {}
    for row in settlements:
        key = _group(row)
        labels = json.loads(row["anomaly_types"])
        if (key is None or key in groups or row["settlement_status"] not in STATUSES
                or not _strings(labels) or not set(labels) <= RECOMMENDED_ACTIONS.keys()):
            raise ContextError("The settlement report contains invalid or repeated group data.")
        groups[key] = (row["settlement_status"], set(labels), {field: _money(row[field]) for field in GROUP_AMOUNTS})

    result = {}
    by_group = {}
    for row in anomalies:
        anomaly_id, kind = row["anomaly_id"], row["anomaly_type"]
        key = _group(row)
        references = json.loads(row["related_record_ids"])
        if (not SAFE_ID.fullmatch(anomaly_id) or anomaly_id in result or kind not in RECOMMENDED_ACTIONS
                or not _strings(references) or (key is not None and key not in groups)):
            raise ContextError("The anomaly report contains invalid identifiers or settlement links.")
        status, labels, amounts = groups.get(key, (None, set(), dict.fromkeys(GROUP_AMOUNTS)))
        if key is not None:
            by_group.setdefault(key, set()).add(kind)
            if kind not in labels:
                raise ContextError("An anomaly type disagrees with its settlement group.")
        evidence = json.loads(row["evidence"])
        if not isinstance(evidence, dict):
            raise ContextError("An anomaly is missing structured evidence.")
        resolution = evidence.get("resolution")
        if kind != "DUPLICATE_PAYMENT" or resolution not in ("EXACT_COPY_COUNTED_ONCE", "UNRESOLVED_REFERENCE"):
            resolution = None
        reference_map = {
            value if SAFE_ID.fullmatch(value) else f"[REF-{index}]": value
            for index, value in enumerate(dict.fromkeys(references), 1)
        }
        result[anomaly_id] = {
            "anomaly_id": anomaly_id, "anomaly_type": kind,
            "hospital_id": key[0] if key else None, "settlement_period": key[1] if key else None,
            "settlement_status": status, "reference_map": reference_map,
            "review_evidence": _review_evidence(kind, evidence, reference_map, resolution),
            "payment_reference_resolution": resolution, "group_amounts": amounts,
            "amounts": {field: _money(row[field]) for field in FINDING_AMOUNTS},
        }

    unassigned = sum(row["settlement_period"] is None for row in result.values())
    by_type = Counter(row["anomaly_type"] for row in result.values())
    statuses = Counter(status for status, _, _ in groups.values())
    if (len(groups) != summary["settlement_group_count"]
            or len(by_group) != summary["anomalous_group_count"]
            or unassigned != summary["unassigned_issue_count"]
            or bool(unassigned) != (summary["run_status"] == "INCOMPLETE_INPUT")
            or any(by_type[kind] != count for kind, count in summary["anomaly_counts"].items())
            or any(by_group.get(key, set()) != labels for key, (_, labels, _) in groups.items())
            or statuses["REVIEW_REQUIRED"] != summary["held_group_count"]
            or statuses["UNMATCHED_PAYMENT"] != summary["unmatched_payment_group_count"]
            or len(groups) - statuses["REVIEW_REQUIRED"] - statuses["UNMATCHED_PAYMENT"] != summary["comparable_group_count"]):
        raise ContextError("The financial reports disagree. Regenerate the three reports together.")
    return result


def build_context(input_dir: Path) -> AnalysisContext:
    """Read only the three deterministic reports and separate model data from money."""
    summary_name, anomaly_name, settlement_name = SOURCE_FILES
    try:
        with (input_dir / summary_name).open(encoding="utf-8") as source:
            summary = _project_summary(json.load(source))
        anomalies = _read_rows(input_dir / anomaly_name, (
            "anomaly_id", "anomaly_type", "hospital_id", "settlement_period",
            "related_record_ids", "evidence", *FINDING_AMOUNTS,
        ))
        settlements = _read_rows(input_dir / settlement_name, (
            "hospital_id", "settlement_period", "settlement_status", "anomaly_types", *GROUP_AMOUNTS,
        ))
        return AnalysisContext(summary, _findings(anomalies, settlements, summary))
    except ContextError:
        raise
    except (OSError, ValueError, csv.Error, RecursionError) as error:
        raise ContextError("A financial report is missing, unreadable or malformed. Rerun main.py first.") from error
