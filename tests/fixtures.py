"""Small synthetic CSV fixtures independent of the Step 02 dataset."""

import csv
from pathlib import Path
from tempfile import TemporaryDirectory

from src.data_loader import CONTRACT_FIELDS, PAYMENT_FIELDS, SERVICE_FIELDS, load_data


ROOT = Path(__file__).resolve().parents[1]
SOURCE_FILES = ("contracts.csv", "service_records.csv", "payments.csv")
GROUP = ("TEST-H1", "2026-01")


def contract(**changes):
    return {
        "contract_id": "C1", "hospital_id": GROUP[0], "test_type": "PCR",
        "collection_type": "SINGLE", "service_type": "SELF_PAID", "billing_unit": "SAMPLE",
        "unit_price": "0.10", "effective_date": "2026-01-01",
        "expiry_date": "2026-01-31", "currency": "CNY", **changes,
    }


def service(**changes):
    return {
        "service_id": "S1", "hospital_id": GROUP[0], "service_date": "2026-01-15",
        "settlement_period": GROUP[1], "test_type": "PCR", "collection_type": "SINGLE",
        "service_type": "SELF_PAID", "billing_unit": "SAMPLE", "quantity": "3",
        "reported_amount": "0.30", **changes,
    }


def payment(**changes):
    return {
        "payment_id": "P1", "hospital_id": GROUP[0], "payment_date": "2026-01-26",
        "settlement_period": GROUP[1], "payment_amount": "0.30",
        "payment_reference": "REF-1", "currency": "CNY", **changes,
    }


def workspace_temp():
    output = (ROOT / "outputs").resolve()
    if not output.is_relative_to(ROOT):
        raise ValueError("Test output directory must be inside the project")
    output.mkdir(exist_ok=True)
    return TemporaryDirectory(prefix="step03-test-", dir=output)


def write_sources(path, contracts=(), services=(), payments=()):
    path.mkdir(parents=True, exist_ok=True)
    for filename, fields, rows in zip(
        SOURCE_FILES, (CONTRACT_FIELDS, SERVICE_FIELDS, PAYMENT_FIELDS),
        (contracts, services, payments),
    ):
        with (path / filename).open("w", encoding="utf-8", newline="") as output:
            writer = csv.DictWriter(output, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)


def load_fixture(**tables):
    with workspace_temp() as temporary:
        path = Path(temporary)
        write_sources(path, **tables)
        return load_data(path)
