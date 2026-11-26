"""Deterministic exception, payment-reference, and balance rules."""

from dataclasses import dataclass

from .data_loader import GroupKey, SourceRow


RECOMMENDED_ACTIONS = {
    "MISSING_PAYMENT": "Check receipt and settlement records. Verify terms separately before assessing lateness.",
    "UNDERPAYMENT": "Verify receipt completeness and any documented adjustments with finance.",
    "OVERPAYMENT": "Verify the receipt amount and settlement period with finance.",
    "DUPLICATE_PAYMENT": "Compare the listed source rows with the original payment record.",
    "PRICE_MISMATCH": "Compare the reported charge, contract price and quantity with the source documents.",
    "MISSING_CONTRACT": "Obtain an approved contract covering the service date and pricing key.",
    "CONTRACT_OVERLAP": "Confirm the applicable contract version and correct the overlapping dates.",
    "UNMATCHED_PAYMENT": "Confirm the hospital and settlement period and locate the related services.",
    "INVALID_DATA": "Review the source fields and correct the record before finalizing affected amounts.",
}


@dataclass
class Anomaly:
    anomaly_type: str
    group: GroupKey | None
    related_record_ids: list[str]
    evidence: dict
    expected_cents: int | None = None
    actual_cents: int | None = None
    anomaly_id: str = ""

    @property
    def difference_cents(self) -> int | None:
        if self.expected_cents is None or self.actual_cents is None:
            return None
        return self.expected_cents - self.actual_cents

    @property
    def recommended_action(self) -> str:
        return RECOMMENDED_ACTIONS[self.anomaly_type]


def invalid_source(row: SourceRow, group: GroupKey | None) -> Anomaly:
    return Anomaly("INVALID_DATA", group, [row.record_id], {"source": row.evidence()})


def resolve_payment_reference(rows: list[SourceRow]) -> tuple[SourceRow | None, list[Anomaly]]:
    """Resolve one globally scoped reference and retain the evidence for every copy."""
    if len(rows) == 1:
        row = rows[0]
        return (None if row.errors else row), []

    first = rows[0]
    payload = ("hospital_id", "payment_date", "settlement_period", "payment_amount", "currency")
    identical = not any(row.errors for row in rows) and all(
        all(row.values[field] == first.values[field] for field in payload)
        for row in rows[1:]
    )
    selected = None
    if identical:
        selected = min(rows, key=lambda row: (row.record_id, row.line))
    evidence = {
        "payment_reference": first.raw["payment_reference"],
        "resolution": "EXACT_COPY_COUNTED_ONCE" if selected else "UNRESOLVED_REFERENCE",
        "selected_payment_id": selected.record_id if selected else None,
        "selected_source_line": selected.line if selected else None,
        "sources": [row.evidence() for row in rows],
    }
    groups = sorted({row.group for row in rows if row.group is not None})
    if any(row.group is None for row in rows):
        groups.append(None)
    ids = list(dict.fromkeys(row.record_id for row in rows))
    return selected, [
        Anomaly(
            "DUPLICATE_PAYMENT", group, ids, evidence,
            actual_cents=selected.values["payment_amount"] if selected else None,
        )
        for group in groups
    ]


def balance_status(
    expected_cents: int | None, paid_cents: int | None,
    has_services: bool, has_payments: bool,
) -> str:
    if paid_cents is None or (has_services and expected_cents is None):
        return "REVIEW_REQUIRED"
    if not has_services:
        return "UNMATCHED_PAYMENT"
    if not has_payments:
        return "MISSING_PAYMENT"
    if expected_cents > paid_cents:
        return "UNDERPAYMENT"
    if expected_cents < paid_cents:
        return "OVERPAYMENT"
    return "MATCHED"
