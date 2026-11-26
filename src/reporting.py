"""Serialize reconciliation results for review and downstream consumers."""

import csv
import json
from collections import Counter
from pathlib import Path

from .anomaly_detector import RECOMMENDED_ACTIONS, Anomaly
from .data_loader import format_money
from .reconciliation import ReconciliationRun, SettlementResult


SETTLEMENT_FIELDS = (
    "hospital_id", "settlement_period", "settlement_status", "review_required",
    "anomaly_types", "expected_amount", "paid_amount", "difference_amount",
    "eligible_paid_amount", "payment_bucket", "service_record_count",
    "raw_payment_count", "eligible_payment_count", "service_details",
    "raw_payments", "eligible_payments",
)
ANOMALY_FIELDS = (
    "anomaly_id", "anomaly_type", "hospital_id", "settlement_period",
    "related_record_ids", "expected_amount", "actual_amount", "difference_amount",
    "evidence", "review_required", "recommended_action",
)


def _payment_bucket(row: SettlementResult) -> str:
    if row.settlement_status == "REVIEW_REQUIRED":
        return "HELD"
    if row.settlement_status == "UNMATCHED_PAYMENT":
        return "UNMATCHED"
    return "COMPARABLE"


def summarize(run: ReconciliationRun) -> dict:
    settlements = run.settlements
    buckets = {
        "COMPARABLE": [], "HELD": [], "UNMATCHED": [],
    }
    for row in settlements:
        buckets[_payment_bucket(row)].append(row)
    comparable = buckets["COMPARABLE"]
    held = buckets["HELD"]
    unmatched = buckets["UNMATCHED"]
    reliable = [row for row in settlements if row.expected_cents is not None]
    issues = run.anomalies
    counts = Counter(issue.anomaly_type for issue in issues)
    missing = sum(row.difference_cents for row in comparable if row.settlement_status == "MISSING_PAYMENT")
    under = sum(row.difference_cents for row in comparable if row.settlement_status == "UNDERPAYMENT")
    over = -sum(row.difference_cents for row in comparable if row.settlement_status == "OVERPAYMENT")
    return {
        "run_status": "INCOMPLETE_INPUT" if run.unassigned_anomalies else "COMPLETED",
        "currency": "CNY",
        "difference_definition": "expected_amount - paid_amount",
        "contract_record_count": len(run.source.contracts),
        "service_record_count": len(run.source.services),
        "raw_payment_count": len(run.source.payments),
        "eligible_payment_count": sum(len(row.eligible_payments) for row in settlements),
        "settlement_group_count": len(settlements),
        "normal_group_count": sum(not row.review_required for row in settlements),
        "anomalous_group_count": sum(row.review_required for row in settlements),
        "review_required_group_count": sum(row.review_required for row in settlements),
        "held_group_count": len(held),
        "unmatched_payment_group_count": len(unmatched),
        "comparable_group_count": len(comparable),
        "unassigned_issue_count": len(run.unassigned_anomalies),
        "settlement_status_counts": dict(sorted(Counter(row.settlement_status for row in settlements).items())),
        "anomaly_counts": {kind: counts[kind] for kind in RECOMMENDED_ACTIONS},
        "reliable_receivable_amount": format_money(sum(row.expected_cents for row in reliable) if reliable else None),
        "comparable_receivable_amount": format_money(sum(row.expected_cents for row in comparable) if comparable else None),
        "eligible_payment_amount": format_money(sum(row.eligible_paid_cents for row in settlements)),
        "comparable_paid_amount": format_money(sum(row.eligible_paid_cents for row in comparable) if comparable else None),
        "held_eligible_payment_amount": format_money(sum(row.eligible_paid_cents for row in held)),
        "unmatched_payment_amount": format_money(sum(row.eligible_paid_cents for row in unmatched)),
        "net_difference": format_money(sum(row.difference_cents for row in comparable) if comparable else None),
        "missing_payment_amount": format_money(missing),
        "underpayment_amount": format_money(under),
        "overpayment_amount": format_money(over),
        "total_shortfall_amount": format_money(missing + under),
        "held_groups": [
            {
                "hospital_id": row.group[0],
                "settlement_period": row.group[1],
                "anomaly_types": row.anomaly_types,
                "expected_amount_known": row.expected_cents is not None,
                "paid_amount_known": row.paid_cents is not None,
                "eligible_paid_amount": format_money(row.eligible_paid_cents),
            }
            for row in held
        ],
        "amount_notes": {
            "unknown": "CSV blanks and JSON nulls denote unavailable amounts. Held and unmatched groups have no comparable difference.",
            "eligible": "Eligible amounts exclude invalid and unresolved payment rows and count exact copies once.",
            "scope": "When input is incomplete, group totals cover attributable rows only and are provisional.",
        },
    }


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _settlement_row(row: SettlementResult) -> dict:
    return dict(zip(SETTLEMENT_FIELDS, (
        *row.group, row.settlement_status, str(row.review_required).lower(),
        _json(row.anomaly_types), format_money(row.expected_cents), format_money(row.paid_cents),
        format_money(row.difference_cents), format_money(row.eligible_paid_cents),
        _payment_bucket(row), len(row.service_details), len(row.raw_payments),
        len(row.eligible_payments), _json(row.service_details),
        _json([item.evidence() for item in row.raw_payments]),
        _json([item.evidence() for item in row.eligible_payments]),
    )))


def _anomaly_row(anomaly: Anomaly) -> dict:
    return dict(zip(ANOMALY_FIELDS, (
        anomaly.anomaly_id, anomaly.anomaly_type, *(anomaly.group or ("", "")),
        _json(anomaly.related_record_ids), format_money(anomaly.expected_cents),
        format_money(anomaly.actual_cents), format_money(anomaly.difference_cents),
        _json(anomaly.evidence), "true", anomaly.recommended_action,
    )))


def _write_csv(path: Path, fields: tuple[str, ...], rows) -> None:
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_reports(run: ReconciliationRun, output_dir: Path) -> dict:
    """Write both evidence tables and the summary, returning the summary payload."""
    output_dir.mkdir(parents=True, exist_ok=True)
    summary = summarize(run)
    _write_csv(
        output_dir / "reconciliation_results.csv", SETTLEMENT_FIELDS,
        (_settlement_row(row) for row in run.settlements),
    )
    _write_csv(
        output_dir / "anomaly_details.csv", ANOMALY_FIELDS,
        (_anomaly_row(anomaly) for anomaly in run.anomalies),
    )
    with (output_dir / "summary.json").open("w", encoding="utf-8", newline="\n") as output:
        json.dump(summary, output, ensure_ascii=False, indent=2)
        output.write("\n")
    return summary
