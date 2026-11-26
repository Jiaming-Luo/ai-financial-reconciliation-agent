"""Generate deterministic, synthetic Step 02 CSV fixtures."""

import csv
from pathlib import Path
from random import Random


SEED = 202602
OUTPUT_DIR = Path(__file__).resolve().parents[1] / "data" / "sample"
HOSPITALS = tuple(f"SIM-H{number:03d}" for number in range(1, 6))
PERIODS = tuple(f"2026-{month:02d}" for month in range(1, 7))
TERMS = (
    ("PCR", "SINGLE", "SAMPLE", 4250),
    ("PCR", "POOL_10", "POOL", 1580),
    ("PCR", "POOL_20", "POOL", 2190),
)
SERVICE_TYPES = ("MASS_SCREENING", "SELF_PAID")
PRICE_CHANGE_DATE = "2026-04-15"
PRICE_INCREASE = 300

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
EXPECTED_FIELDS = (
    "case_id", "hospital_id", "settlement_period", "service_id", "payment_id",
    "expected_type", "expected_result",
)


def money(cents):
    whole, fraction = divmod(cents, 100)
    return f"{whole}.{fraction:02d}"


def generate_data():
    random = Random(SEED)
    contracts, services, payments, expected = [], [], [], []
    receivables = {}
    source_rows = {}

    def add_contract(hospital, test, collection, service_type, unit, price, start, end):
        contracts.append((
            f"SIM-C{len(contracts) + 1:04d}", hospital, test, collection,
            service_type, unit, money(price), start, end, "CNY",
        ))
        return contracts[-1][0]

    def add_payment(hospital, period, date, amount, reference=None):
        number = len(payments) + 1
        payment_id = f"SIM-P{number:04d}"
        payments.append((
            payment_id, hospital, date, period, money(amount),
            reference or f"SIM-REF-{number:04d}", "CNY",
        ))
        return payment_id

    def add_case(hospital, period, kind, result, *, service_id="", payment_id=""):
        expected.append((
            f"CASE-{len(expected) + 1:03d}", hospital, period, service_id,
            payment_id, kind, result,
        ))

    for hospital_number, hospital in enumerate(HOSPITALS):
        for test, collection, unit, base_price in TERMS:
            for service_type in SERVICE_TYPES:
                price = base_price + hospital_number * 80
                if service_type == "SELF_PAID":
                    price += 500
                revisions = [("2026-01-01", "2026-06-30", price)]
                if (hospital, collection, service_type) == (
                    "SIM-H001", "SINGLE", "MASS_SCREENING"
                ):
                    revisions = [
                        ("2026-01-01", "2026-04-14", price),
                        (PRICE_CHANGE_DATE, "2026-06-30", price + PRICE_INCREASE),
                    ]
                for start, end, contract_price in revisions:
                    add_contract(
                        hospital, test, collection, service_type, unit,
                        contract_price, start, end,
                    )

                for period in PERIODS:
                    group = (hospital, period)
                    days = (7, 21)
                    if (group, collection, service_type) == (
                        ("SIM-H001", "2026-04"), "SINGLE", "MASS_SCREENING"
                    ):
                        days = (14, 15)
                    for day in days:
                        date = f"{period}-{day:02d}"
                        contract_price = next(
                            value for start, end, value in revisions if start <= date <= end
                        )
                        quantity = random.randint(5, 50)
                        amount = quantity * contract_price
                        service_id = f"SIM-S{len(services) + 1:04d}"
                        source_rows[(hospital, date, collection, service_type)] = (
                            len(services), service_id, amount,
                        )
                        services.append([
                            service_id, hospital, date, period, test, collection,
                            service_type, unit, quantity, money(amount),
                        ])
                        receivables[group] = receivables.get(group, 0) + amount

    for (hospital, period), amount in sorted(receivables.items()):
        group = (hospital, period)
        payment_date = f"{period}-26"
        if group == ("SIM-H001", "2026-01"):
            first = add_payment(hospital, period, payment_date, amount // 2)
            second = add_payment(hospital, period, "2026-02-03", amount - amount // 2)
            add_case(hospital, period, "MATCHED",
                     f"{first} and {second} total CNY {money(amount)} with zero variance.",
                     payment_id=first)
        elif group == ("SIM-H001", "2026-02"):
            add_case(hospital, period, "MISSING_PAYMENT",
                     f"No payment exists for CNY {money(amount)} due.")
        elif group == ("SIM-H002", "2026-02"):
            payment_id = add_payment(hospital, period, payment_date, amount - 1500)
            add_case(hospital, period, "UNDERPAYMENT",
                     "Eligible payments are CNY 15.00 below the receivable.",
                     payment_id=payment_id)
        elif group == ("SIM-H002", "2026-03"):
            payment_id = add_payment(hospital, period, payment_date, amount + 2200)
            add_case(hospital, period, "OVERPAYMENT",
                     "Eligible payments are CNY 22.00 above the receivable.",
                     payment_id=payment_id)
        elif group == ("SIM-H003", "2026-03"):
            original = add_payment(hospital, period, payment_date, amount)
            duplicate = add_payment(hospital, period, payment_date, amount, payments[-1][5])
            add_case(hospital, period, "DUPLICATE_PAYMENT",
                     f"{duplicate} repeats {original}; count CNY {money(amount)} once.",
                     payment_id=duplicate)
        else:
            add_payment(hospital, period, payment_date, amount)

    # Keep baseline payments for service-side cases so each case changes one input.
    hospital = "SIM-H003"
    index, service_id, amount = source_rows[hospital, "2026-04-07", "POOL_10", "SELF_PAID"]
    services[index][9] = money(amount + 400)
    add_case(hospital, "2026-04", "PRICE_MISMATCH",
             f"Reported amount is CNY {money(amount + 400)}; contract amount is CNY "
             f"{money(amount)}. The group remains balanced on contract amounts.",
             service_id=service_id)

    hospital = "SIM-H005"
    index, service_id, _ = source_rows[hospital, "2026-06-07", "SINGLE", "MASS_SCREENING"]
    services[index][4] = "ANTIGEN"
    add_case(hospital, "2026-06", "MISSING_CONTRACT",
             "No active ANTIGEN contract matches the line; hold the group for review.",
             service_id=service_id)

    hospital = "SIM-H004"
    _, service_id, _ = source_rows[hospital, "2026-05-07", "POOL_20", "MASS_SCREENING"]
    overlap = add_contract(
        hospital, "PCR", "POOL_20", "MASS_SCREENING", "POOL",
        2500, "2026-05-07", "2026-05-07",
    )
    add_case(hospital, "2026-05", "CONTRACT_OVERLAP",
             f"{overlap} and the base contract both cover the line; hold the group for review.",
             service_id=service_id)

    hospital = "SIM-H006"
    payment_id = add_payment(hospital, "2026-05", "2026-05-26", 87500)
    add_case(hospital, "2026-05", "UNMATCHED_PAYMENT",
             "A valid CNY 875.00 payment has no service rows in its group.",
             payment_id=payment_id)

    hospital = "SIM-H004"
    index, service_id, _ = source_rows[hospital, "2026-06-21", "POOL_10", "SELF_PAID"]
    services[index][8] = -1
    add_case(hospital, "2026-06", "INVALID_DATA",
             "Quantity -1 violates the positive integer rule; hold the group for review.",
             service_id=service_id)

    return (
        ("contracts.csv", CONTRACT_FIELDS, contracts),
        ("service_records.csv", SERVICE_FIELDS, services),
        ("payments.csv", PAYMENT_FIELDS, payments),
        ("expected_anomalies.csv", EXPECTED_FIELDS, expected),
    )


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for filename, fields, rows in generate_data():
        with (OUTPUT_DIR / filename).open("w", encoding="utf-8", newline="") as output:
            writer = csv.writer(output, lineterminator="\n")
            writer.writerow(fields)
            writer.writerows(rows)
        print(f"{filename}: {len(rows)} records")


if __name__ == "__main__":
    main()
