import unittest
from datetime import date
from pathlib import Path

from src.data_loader import DataLoadError, load_data
from tests.fixtures import contract, load_fixture, payment, service, workspace_temp, write_sources


class DataLoaderTests(unittest.TestCase):
    def test_parses_dates_and_exact_integer_cents(self):
        rows = load_fixture(contracts=[contract()], services=[service()], payments=[payment()])
        self.assertEqual(rows.contracts[0].values["unit_price"], 10)
        self.assertEqual(rows.services[0].values["service_date"], date(2026, 1, 15))
        self.assertEqual(rows.payments[0].values["payment_amount"], 30)
        self.assertTrue(all(not row.errors for row in rows.contracts + rows.services + rows.payments))

    def test_invalid_service_rows_retain_original_values_and_locations(self):
        for field, value in (
            ("quantity", "-1"), ("quantity", "1.5"), ("quantity", "0"),
            ("service_date", "2026-02-30"), ("service_date", "20260115"),
            ("settlement_period", "2026-13"), ("service_id", ""),
            ("collection_type", "POOL_15"), ("test_type", "UNKNOWN"),
            ("service_type", "OTHER"), ("billing_unit", "PERSON"),
        ):
            with self.subTest(field=field, value=value):
                row, = load_fixture(services=[service(**{field: value})]).services
                self.assertTrue(any(error.startswith(field + ":") for error in row.errors))
                self.assertEqual(row.evidence()["raw"][field], value)
                self.assertEqual(row.evidence()["line"], 2)

    def test_rejects_non_cent_and_negative_money(self):
        for value in ("0.001", "1", "NaN", "Infinity", "1e2", "-0.10", "", "1,000.00"):
            with self.subTest(value=value):
                rows = load_fixture(
                    contracts=[contract(unit_price=value)],
                    services=[service(reported_amount=value)],
                    payments=[payment(payment_amount=value)],
                )
                self.assertTrue(all(row.errors for row in rows.contracts + rows.services + rows.payments))

    def test_requires_positive_prices_and_payments_and_cny(self):
        rows = load_fixture(
            contracts=[contract(unit_price="0.00")],
            services=[service(reported_amount="0.00")],
            payments=[payment(payment_amount="0.00", currency="USD")],
        )
        self.assertEqual(len(rows.contracts[0].errors), 1)
        self.assertFalse(rows.services[0].errors)
        self.assertEqual(len(rows.payments[0].errors), 2)

    def test_rejects_reversed_contract_window(self):
        row, = load_fixture(contracts=[contract(expiry_date="2025-12-31")]).contracts
        self.assertIn("expiry_date precedes effective_date", row.errors)

    def test_duplicate_primary_keys_are_reported_on_all_conflicting_rows(self):
        rows = load_fixture(
            contracts=[contract(), contract()],
            services=[service(), service()],
            payments=[payment(), payment(payment_reference="REF-2")],
        )
        for row in rows.contracts + rows.services + rows.payments:
            self.assertTrue(any("duplicate" in error and "lines 2, 3" in error for error in row.errors))

    def test_invalid_or_missing_source_file_reports_path(self):
        with workspace_temp() as temporary:
            path = Path(temporary)
            with self.assertRaisesRegex(DataLoadError, "contracts.csv"):
                load_data(path)
            write_sources(path)
            (path / "contracts.csv").write_text("contract_id,hospital_id\n", encoding="utf-8")
            with self.assertRaisesRegex(DataLoadError, "expected exactly these columns"):
                load_data(path)

    def test_short_row_and_extra_fields_are_retained(self):
        with workspace_temp() as temporary:
            path = Path(temporary)
            write_sources(path)
            with (path / "payments.csv").open("a", encoding="utf-8") as output:
                output.write("P1,TEST-H1,2026-01-26,2026-01\n")
                output.write("P2,TEST-H1,2026-01-26,2026-01,0.30,REF-2,CNY,extra\n")
            short, long = load_data(path).payments
        self.assertIsNone(short.raw["payment_amount"])
        self.assertEqual(long.evidence()["extra_fields"], ["extra"])
        self.assertTrue(short.errors and long.errors)
