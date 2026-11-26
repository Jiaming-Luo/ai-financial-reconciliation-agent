"""Read-only projections of the engine reports and an optional v3 analysis."""

import csv
import json
from pathlib import Path

from .action_catalog import ACTION_CATALOG, eligible_actions
from .context_builder import (
    GROUP_AMOUNTS, SAFE_ID, SOURCE_FILES, AnalysisContext, ContextError, _money, _read_rows, build_context,
)
from .prompts import LANGUAGES, PRIORITIES
from .tool_registry import DEFAULT_LIST_RESULTS, MAX_LIST_RESULTS, RecordNotFound, ToolError


SUMMARY_SOURCE, ANOMALY_SOURCE, GROUP_SOURCE = SOURCE_FILES
SUMMARY_AMOUNTS = (
    "reliable_receivable_amount", "comparable_receivable_amount", "eligible_payment_amount",
    "comparable_paid_amount", "net_difference", "held_eligible_payment_amount", "unmatched_payment_amount",
    "missing_payment_amount", "underpayment_amount", "overpayment_amount",
)
SUMMARY_COUNTS = (
    "settlement_group_count", "comparable_group_count", "anomalous_group_count", "held_group_count",
    "unassigned_issue_count", "normal_group_count",
)
HIGH_REVIEW_TYPES = {"INVALID_DATA", "CONTRACT_OVERLAP", "MISSING_CONTRACT", "DUPLICATE_PAYMENT"}
MAX_REFERENCES = 24


def _safe_id(value: str | None) -> str | None:
    return value if value and SAFE_ID.fullmatch(value) else None


def _groups(path: Path) -> dict:
    rows = _read_rows(path, ("hospital_id", "settlement_period", "settlement_status", "review_required",
                            "anomaly_types", "payment_bucket", "eligible_paid_amount", *GROUP_AMOUNTS))
    return {
        (row["hospital_id"], row["settlement_period"]): {
            "hospital_id": _safe_id(row["hospital_id"]),
            "settlement_period": row["settlement_period"],
            "settlement_status": row["settlement_status"],
            "review_required": bool(json.loads(row["anomaly_types"])) or row["settlement_status"] == "REVIEW_REQUIRED",
            "anomaly_types": json.loads(row["anomaly_types"]),
            "payment_bucket": row["payment_bucket"] if row["payment_bucket"] in ("HELD", "COMPARABLE", "UNMATCHED") else None,
            "eligible_paid_amount": _money(row["eligible_paid_amount"]),
            **{key: _money(row[key]) for key in GROUP_AMOUNTS},
        }
        for row in rows
    }


def _ai_priorities(path: Path, context: AnalysisContext) -> tuple[dict, str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if (not isinstance(data, dict) or data.get("report_schema_version") != "3.0"
            or data.get("core_validation") != "passed"
            or data.get("analysis_status") not in ("completed", "completed_with_omissions")
            or data.get("run_mode") not in ("Mock", "Live")
            or data.get("requires_human_review") is not True
            or context.provisional or data.get("financial_summary") != context.summary
            or not isinstance(data.get("anomaly_findings"), list)):
        raise ContextError("The optional AI report is not a validated v3 report for these financial results.")
    priorities = {}
    for finding in data["anomaly_findings"]:
        if not isinstance(finding, dict) or not isinstance(finding.get("anomaly_id"), str):
            raise ContextError("The optional AI report contains an invalid finding.")
        anomaly_id = finding["anomaly_id"]
        source = context.findings.get(anomaly_id)
        if (source is None or anomaly_id in priorities or finding.get("priority") not in PRIORITIES
                or finding.get("requires_human_review") is not True
                or any(finding.get(key) != source[key] for key in ("anomaly_type", "hospital_id", "settlement_period", "settlement_status"))
                or finding.get("engine_amounts") != source["amounts"]
                or finding.get("engine_group_amounts") != source["group_amounts"]):
            raise ContextError("The optional AI report findings do not agree with the financial evidence.")
        refs = finding.get("evidence_references")
        allowed = source["reference_map"].values()
        if (not isinstance(refs, list) or bool(refs) != bool(allowed)
                or any(not isinstance(ref, str) or ref not in allowed for ref in refs)
                or len(set(refs)) != len(refs)):
            raise ContextError("The optional AI report contains unsupported evidence references.")
        priorities[anomaly_id] = finding["priority"]
    if priorities.keys() != context.findings.keys():
        raise ContextError("The optional AI report does not cover the current findings.")
    return priorities, data["run_mode"]


class AgentTools:
    """Load validated financial artifacts once for a single read-only question."""

    def __init__(self, input_dir: Path, language: str, analysis_dir: Path | None = None):
        if language not in LANGUAGES:
            raise ToolError("Unsupported output language.")
        self.language = language
        self.context = build_context(input_dir)
        self.provisional = self.context.provisional
        self.ai_priorities, self.ai_mode = {}, None
        try:
            self.groups = _groups(input_dir / GROUP_SOURCE)
            if analysis_dir is not None:
                self.ai_priorities, self.ai_mode = _ai_priorities(analysis_dir / f"ai_analysis_{language}.json", self.context)
        except ContextError:
            raise
        except (OSError, ValueError, csv.Error, RecursionError):
            raise ContextError("Unable to read the required financial or optional analysis report.") from None

    def get_reconciliation_summary(self) -> dict:
        summary = self.context.summary
        held = [group for group in self.groups.values() if group["settlement_status"] == "REVIEW_REQUIRED"]
        return {
            "source_files": [SUMMARY_SOURCE, GROUP_SOURCE],
            "data": {
                "run_status": summary["run_status"],
                "currency": summary["currency"],
                "difference_definition": summary["difference_definition"],
                **{key: summary[key] for key in SUMMARY_COUNTS},
                **{key: None if self.provisional else summary[key] for key in SUMMARY_AMOUNTS},
                "anomaly_counts": summary["anomaly_counts"],
                "held_groups": held[:MAX_LIST_RESULTS],
                "held_groups_truncated": len(held) > MAX_LIST_RESULTS,
            },
        }

    def _matching(self, hospital_id: str | None, settlement_period: str | None, anomaly_type: str | None) -> list[dict]:
        return [finding for finding in self.context.findings.values()
                if (hospital_id is None or hospital_id == finding["hospital_id"])
                and (settlement_period is None or settlement_period == finding["settlement_period"])
                and (anomaly_type is None or anomaly_type == finding["anomaly_type"])]

    @staticmethod
    def _finding_row(finding: dict) -> dict:
        return {
            "anomaly_id": finding["anomaly_id"], "anomaly_type": finding["anomaly_type"],
            "hospital_id": _safe_id(finding["hospital_id"]), "settlement_period": finding["settlement_period"],
            "settlement_status": finding["settlement_status"], "review_required": True,
        }

    def list_anomalies(self, hospital_id=None, settlement_period=None, anomaly_type=None, limit=DEFAULT_LIST_RESULTS) -> dict:
        matches = self._matching(hospital_id, settlement_period, anomaly_type)
        return {"source_files": [ANOMALY_SOURCE], "data": {
            "matched_count": len(matches), "truncated": len(matches) > limit,
            "anomalies": [self._finding_row(item) for item in matches[:limit]],
        }}

    def get_anomaly_details(self, anomaly_id: str) -> dict:
        finding = self.context.findings.get(anomaly_id)
        if finding is None:
            raise RecordNotFound("The anomaly ID was not found.")
        refs = list(finding["reference_map"])
        options = eligible_actions(finding["anomaly_type"], finding["review_evidence"])
        actions = [
            {"action_code": code, "description": ACTION_CATALOG[code].describe(self.language), "review_required": True}
            for code in options
        ]
        return {"source_files": [ANOMALY_SOURCE, GROUP_SOURCE], "data": {
            **self._finding_row(finding), "currency": self.context.summary["currency"],
            "amounts": finding["amounts"], "group_amounts": finding["group_amounts"],
            "related_record_ids": refs[:MAX_REFERENCES], "related_record_count": len(refs),
            "references_truncated": len(refs) > MAX_REFERENCES,
            "evidence_by_role": {role: [ref for ref in values if ref in refs[:MAX_REFERENCES]]
                                 for role, values in finding["review_evidence"].items() if values},
            "payment_reference_resolution": finding["payment_reference_resolution"],
            "manual_review_actions": actions,
        }}

    def get_hospital_reconciliation(self, hospital_id: str, settlement_period: str) -> dict:
        group = self.groups.get((hospital_id, settlement_period))
        if group is None:
            raise RecordNotFound("No settlement group matched that hospital and period.")
        matches = self._matching(hospital_id, settlement_period, None)
        return {"source_files": [GROUP_SOURCE, ANOMALY_SOURCE], "data": {
            **group, "currency": self.context.summary["currency"],
            "matched_count": len(matches), "truncated": len(matches) > MAX_LIST_RESULTS,
            "anomalies": [self._finding_row(finding) for finding in matches[:MAX_LIST_RESULTS]],
        }}

    def get_review_priorities(self, hospital_id=None, settlement_period=None, anomaly_type=None, limit=DEFAULT_LIST_RESULTS) -> dict:
        matches = self._matching(hospital_id, settlement_period, anomaly_type)
        rows = []
        for finding in matches:
            high = finding["settlement_status"] == "REVIEW_REQUIRED" or finding["anomaly_type"] in HIGH_REVIEW_TYPES
            rows.append({
                **self._finding_row(finding), "business_priority": "HIGH" if high else "MEDIUM",
                "ai_suggested_priority": self.ai_priorities.get(finding["anomaly_id"]),
            })
        rows.sort(key=lambda row: (PRIORITIES.index(row["business_priority"]), row["anomaly_id"]))
        return {"source_files": [ANOMALY_SOURCE, GROUP_SOURCE], "data": {
            "matched_count": len(rows), "truncated": len(rows) > limit,
            "business_priority_policy": "HELD_OR_CONTROL_EXCEPTION_FIRST",
            "ai_priority_source": f"v3 analysis ({self.ai_mode})" if self.ai_mode else None,
            "priorities": rows[:limit],
        }}
