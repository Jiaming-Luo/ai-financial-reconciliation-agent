"""Price service rows and reconcile validated source records by settlement group."""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date

from .anomaly_detector import Anomaly, balance_status, invalid_source, resolve_payment_reference
from .data_loader import GroupKey, SourceData, SourceRow, format_money


@dataclass
class SettlementResult:
    group: GroupKey
    settlement_status: str
    expected_cents: int | None
    paid_cents: int | None
    eligible_paid_cents: int
    service_details: list[dict]
    raw_payments: list[SourceRow]
    eligible_payments: list[SourceRow]
    anomalies: list[Anomaly]

    @property
    def difference_cents(self) -> int | None:
        if self.expected_cents is None or self.paid_cents is None:
            return None
        return self.expected_cents - self.paid_cents

    @property
    def anomaly_types(self) -> list[str]:
        return sorted({anomaly.anomaly_type for anomaly in self.anomalies})

    @property
    def review_required(self) -> bool:
        return bool(self.anomalies)


@dataclass
class ReconciliationRun:
    source: SourceData
    settlements: list[SettlementResult]
    unassigned_anomalies: list[Anomaly]

    @property
    def anomalies(self) -> list[Anomaly]:
        return [
            anomaly for settlement in self.settlements for anomaly in settlement.anomalies
        ] + self.unassigned_anomalies


@dataclass
class _GroupInput:
    services: list[SourceRow] = field(default_factory=list)
    raw_payments: list[SourceRow] = field(default_factory=list)
    eligible_payments: list[SourceRow] = field(default_factory=list)
    payment_anomalies: list[Anomaly] = field(default_factory=list)
    payment_blocked: bool = False


def _could_cover(contract: SourceRow, service_date: date) -> bool:
    start = contract.values.get("effective_date")
    end = contract.values.get("expiry_date")
    if start is not None and end is not None and start > end:
        return True
    return (start is None or start <= service_date) and (end is None or service_date <= end)


def _price_service(
    row: SourceRow, contracts: list[SourceRow], invalid_contracts: dict[int, SourceRow],
) -> tuple[int | None, dict, list[Anomaly]]:
    details = {
        "service_id": row.record_id,
        "source": row.evidence(),
        "quantity": row.values.get("quantity"),
        "reported_amount": format_money(row.values.get("reported_amount")),
        "contract_id": None,
        "unit_price": None,
        "expected_amount": None,
    }
    if row.errors:
        return None, details, [invalid_source(row, row.group)]

    candidates = [c for c in contracts if _could_cover(c, row.values["service_date"])]
    valid = [c for c in candidates if not c.errors]
    suspect = [c for c in candidates if c.errors]
    invalid_contracts.update((c.line, c) for c in suspect)
    details["candidate_contract_ids"] = [c.record_id for c in candidates]
    ids = [row.record_id, *details["candidate_contract_ids"]]
    if len(valid) > 1:
        return None, details, [Anomaly(
            "CONTRACT_OVERLAP", row.group, ids,
            {**details, "candidate_contracts": [c.evidence() for c in candidates]},
        )]
    if suspect:
        details["pricing_issue"] = "INVALID_CONTRACT_CANDIDATE"
        return None, details, []
    if not valid:
        return None, details, [Anomaly("MISSING_CONTRACT", row.group, ids, details)]

    contract = valid[0]
    unit_price = contract.values["unit_price"]
    details.update(
        contract_id=contract.record_id,
        contract_billing_unit=contract.values["billing_unit"],
        unit_price=format_money(unit_price),
    )
    if row.values["billing_unit"] != contract.values["billing_unit"]:
        return None, details, [Anomaly(
            "INVALID_DATA", row.group, ids,
            {**details, "errors": ["billing_unit differs from the active contract"]},
        )]
    charge = row.values["quantity"] * unit_price
    reported = row.values["reported_amount"]
    details["expected_amount"] = format_money(charge)
    anomalies = []
    if charge != reported:
        anomalies.append(Anomaly("PRICE_MISMATCH", row.group, ids, details, charge, reported))
    return charge, details, anomalies


def _collect_groups(source: SourceData) -> tuple[dict[GroupKey, _GroupInput], list[Anomaly]]:
    groups = defaultdict(_GroupInput)
    unassigned = []
    for row in source.services:
        if row.group is None:
            unassigned.append(invalid_source(row, None))
        else:
            groups[row.group].services.append(row)

    by_reference = defaultdict(list)
    for row in source.payments:
        if row.group is None:
            unassigned.append(invalid_source(row, None))
        else:
            group = groups[row.group]
            group.raw_payments.append(row)
            if row.errors:
                group.payment_blocked = True
                group.payment_anomalies.append(invalid_source(row, row.group))
        reference = row.values.get("payment_reference")
        if reference is not None:
            by_reference[reference].append(row)

    for rows in by_reference.values():
        selected, anomalies = resolve_payment_reference(rows)
        if selected is not None:
            groups[selected.group].eligible_payments.append(selected)
        for anomaly in anomalies:
            if anomaly.group is None:
                unassigned.append(anomaly)
            else:
                group = groups[anomaly.group]
                group.payment_anomalies.append(anomaly)
                if selected is None:
                    group.payment_blocked = True
    return groups, unassigned


def _reconcile_group(
    key: GroupKey, group: _GroupInput, contract_index: dict,
) -> tuple[SettlementResult, set[int]]:
    details = []
    anomalies = list(group.payment_anomalies)
    charges = []
    invalid_contracts = {}
    for service in group.services:
        charge, detail, issues = _price_service(
            service, contract_index.get(service.pricing_key, []), invalid_contracts,
        )
        charges.append(charge)
        details.append(detail)
        anomalies.extend(issues)
    anomalies.extend(invalid_source(row, key) for row in invalid_contracts.values())

    expected = None
    if charges and all(charge is not None for charge in charges):
        expected = sum(charges)
    eligible_paid = sum(row.values["payment_amount"] for row in group.eligible_payments)
    paid = None if group.payment_blocked else eligible_paid
    status = balance_status(expected, paid, bool(group.services), bool(group.raw_payments))
    if status in {"MISSING_PAYMENT", "UNDERPAYMENT", "OVERPAYMENT", "UNMATCHED_PAYMENT"}:
        ids = [row.record_id for row in group.services + group.eligible_payments]
        evidence = {
            "service_record_count": len(group.services),
            "eligible_payments": [row.evidence() for row in group.eligible_payments],
        }
        anomalies.append(Anomaly(status, key, ids, evidence, expected, paid))
    return SettlementResult(
        key, status, expected, paid, eligible_paid, details,
        group.raw_payments, group.eligible_payments, anomalies,
    ), set(invalid_contracts)


def reconcile(source: SourceData) -> ReconciliationRun:
    """Return settlement results, independent anomaly labels, and source evidence."""
    contract_index = defaultdict(list)
    for contract in source.contracts:
        if contract.pricing_key is not None:
            contract_index[contract.pricing_key].append(contract)

    groups, unassigned = _collect_groups(source)
    settlements = []
    assigned_contract_lines = set()
    for key in sorted(groups):
        settlement, lines = _reconcile_group(key, groups[key], contract_index)
        settlements.append(settlement)
        assigned_contract_lines.update(lines)
    for contract in source.contracts:
        if contract.errors and contract.line not in assigned_contract_lines:
            unassigned.append(invalid_source(contract, None))

    run = ReconciliationRun(source, settlements, unassigned)
    for number, anomaly in enumerate(run.anomalies, 1):
        anomaly.anomaly_id = f"ANOM-{number:06d}"
    return run
