"""Load and validate the three source CSVs without discarding source rows."""

import csv
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path


CONTRACT_FIELDS = (
    "contract_id", "hospital_id", "test_type", "collection_type", "service_type",
    "billing_unit", "unit_price", "effective_date", "expiry_date", "currency",
)
SERVICE_FIELDS = (
    "service_id", "hospital_id", "service_date", "settlement_period", "test_type",
    "collection_type", "service_type", "billing_unit", "quantity", "reported_amount",
)
PAYMENT_FIELDS = (
    "payment_id", "hospital_id", "payment_date", "settlement_period",
    "payment_amount", "payment_reference", "currency",
)
PRICING_FIELDS = ("hospital_id", "test_type", "collection_type", "service_type")
ENUMS = {
    "test_type": {"PCR", "ANTIGEN"},
    "collection_type": {"SINGLE", "POOL_10", "POOL_20"},
    "service_type": {"MASS_SCREENING", "SELF_PAID"},
    "billing_unit": {"SAMPLE", "POOL"},
    "currency": {"CNY"},
}
DATE_FIELDS = {"effective_date", "expiry_date", "service_date", "payment_date"}
MONEY_FIELDS = {"unit_price", "reported_amount", "payment_amount"}
GroupKey = tuple[str, str]


class DataLoadError(ValueError):
    """A source file cannot be safely interpreted."""


def format_money(cents: int | None) -> str | None:
    if cents is None:
        return None
    whole, fraction = divmod(abs(cents), 100)
    sign = "-" if cents < 0 else ""
    return f"{sign}{whole}.{fraction:02d}"


@dataclass
class SourceRow:
    filename: str
    line: int
    id_field: str
    raw: dict[str, str | None]
    extra_fields: list[str]
    values: dict[str, str | int | date] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    @property
    def record_id(self) -> str:
        return self.values.get(self.id_field) or f"{self.filename}:{self.line}"

    @property
    def group(self) -> GroupKey | None:
        if "hospital_id" in self.values and "settlement_period" in self.values:
            return self.values["hospital_id"], self.values["settlement_period"]
        return None

    @property
    def pricing_key(self) -> tuple[str, ...] | None:
        if all(name in self.values for name in PRICING_FIELDS):
            return tuple(self.values[name] for name in PRICING_FIELDS)
        return None

    def evidence(self) -> dict:
        details = {"file": self.filename, "line": self.line, "raw": self.raw}
        if self.extra_fields:
            details["extra_fields"] = self.extra_fields
        if self.errors:
            details["errors"] = self.errors
        return details


@dataclass
class SourceData:
    contracts: list[SourceRow]
    services: list[SourceRow]
    payments: list[SourceRow]


def _parse_value(name: str, value: str | None) -> str | int | date:
    if value is None or not value.strip():
        raise ValueError("required value is missing")
    if name in ENUMS and value not in ENUMS[name]:
        raise ValueError(f"expected one of {', '.join(sorted(ENUMS[name]))}")
    if name in DATE_FIELDS or name == "settlement_period":
        pattern = r"[0-9]{4}-[0-9]{2}" if name == "settlement_period" else r"[0-9]{4}-[0-9]{2}-[0-9]{2}"
        if not re.fullmatch(pattern, value):
            raise ValueError("expected YYYY-MM for a month or YYYY-MM-DD for a date")
        if name == "settlement_period":
            date.fromisoformat(f"{value}-01")
            return value
        return date.fromisoformat(value)
    if name in MONEY_FIELDS:
        if not re.fullmatch(r"[0-9]+\.[0-9]{2}", value):
            raise ValueError("expected nonnegative CNY with exactly two decimal places")
        cents = int(value.replace(".", ""))
        if name != "reported_amount" and cents == 0:
            raise ValueError("amount must be positive")
        return cents
    if name == "quantity":
        if not re.fullmatch(r"[0-9]+", value) or int(value) == 0:
            raise ValueError("quantity must be a positive integer")
        return int(value)
    if value != value.strip():
        raise ValueError("leading and trailing whitespace is invalid")
    return value


def _read_rows(path: Path, fields: tuple[str, ...]) -> list[SourceRow]:
    rows = []
    try:
        with path.open(encoding="utf-8-sig", newline="") as source:
            reader = csv.reader(source, strict=True)
            header = next(reader, [])
            if len(header) != len(fields) or set(header) != set(fields):
                raise DataLoadError(f"{path}: expected exactly these columns: {', '.join(fields)}")
            while True:
                line = reader.line_num + 1
                columns = next(reader, None)
                if columns is None:
                    break
                if not columns:
                    continue
                raw = dict.fromkeys(header)
                raw.update(zip(header, columns))
                row = SourceRow(path.name, line, fields[0], raw, columns[len(header):])
                if row.extra_fields:
                    row.errors.append("row has extra columns")
                for name in fields:
                    try:
                        row.values[name] = _parse_value(name, raw[name])
                    except ValueError as error:
                        row.errors.append(f"{name}: {error}")
                start = row.values.get("effective_date")
                end = row.values.get("expiry_date")
                if start is not None and end is not None and start > end:
                    row.errors.append("expiry_date precedes effective_date")
                rows.append(row)
    except (OSError, UnicodeError, csv.Error) as error:
        raise DataLoadError(f"{path}: {error}") from error

    by_id = defaultdict(list)
    for row in rows:
        if row.id_field in row.values:
            by_id[row.record_id].append(row)
    for record_id, copies in by_id.items():
        if len(copies) < 2:
            continue
        # An exact repeated payment row is handled by the payment reference rule.
        if fields == PAYMENT_FIELDS and all(
            not row.errors and row.raw == copies[0].raw for row in copies
        ):
            continue
        lines = ", ".join(str(row.line) for row in copies)
        for row in copies:
            row.errors.append(f"duplicate {row.id_field} {record_id} at lines {lines}")
    return rows


def load_data(input_dir: Path) -> SourceData:
    """Read the source tables. Recoverable row errors remain attached to their rows."""
    return SourceData(
        contracts=_read_rows(input_dir / "contracts.csv", CONTRACT_FIELDS),
        services=_read_rows(input_dir / "service_records.csv", SERVICE_FIELDS),
        payments=_read_rows(input_dir / "payments.csv", PAYMENT_FIELDS),
    )
