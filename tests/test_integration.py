import csv
import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

from src.data_loader import load_data
from src.reconciliation import reconcile
from src.reporting import summarize
from tests.fixtures import ROOT, SOURCE_FILES, contract, payment, service, workspace_temp, write_sources


SAMPLE = ROOT / "data" / "sample"
REPORT_FILES = ("reconciliation_results.csv", "anomaly_details.csv", "summary.json")


def run_cli(input_dir, output_dir):
    return subprocess.run(
        [sys.executable, "-B", str(ROOT / "main.py"), "--input-dir", str(input_dir),
         "--output-dir", str(output_dir)],
        cwd=ROOT, capture_output=True, text=True,
    )


class IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.run_result = reconcile(load_data(SAMPLE))
        cls.settlements = {row.group: row for row in cls.run_result.settlements}

    def test_all_ten_oracle_cases(self):
        with (SAMPLE / "expected_anomalies.csv").open(encoding="utf-8", newline="") as source:
            cases = list(csv.DictReader(source))
        self.assertEqual(len(cases), 10)
        self.assertEqual(len({case["expected_type"] for case in cases}), 10)
        self.assertEqual(len(self.run_result.anomalies), 9)
        for case in cases:
            with self.subTest(case=case["case_id"], kind=case["expected_type"]):
                key = case["hospital_id"], case["settlement_period"]
                result = self.settlements[key]
                kind = case["expected_type"]
                if kind == "MATCHED":
                    self.assertEqual(result.settlement_status, "MATCHED")
                    self.assertFalse(result.review_required)
                    self.assertEqual(result.difference_cents, 0)
                    self.assertIn(case["payment_id"], [row.record_id for row in result.eligible_payments])
                    continue
                issue, = [item for item in result.anomalies if item.anomaly_type == kind]
                self.assertTrue(result.review_required)
                for id_field in ("service_id", "payment_id"):
                    if case[id_field]:
                        self.assertIn(case[id_field], issue.related_record_ids)
                if kind in {"MISSING_CONTRACT", "CONTRACT_OVERLAP", "INVALID_DATA"}:
                    self.assertEqual(result.settlement_status, "REVIEW_REQUIRED")
                    self.assertIsNone(result.expected_cents)
                    self.assertIsNone(result.difference_cents)
                elif kind in {"DUPLICATE_PAYMENT", "PRICE_MISMATCH"}:
                    self.assertEqual(result.settlement_status, "MATCHED")
                    self.assertEqual(result.difference_cents, 0)
                else:
                    self.assertEqual(result.settlement_status, kind)

    def test_sample_revision_and_summary_totals(self):
        april = self.settlements["SIM-H001", "2026-04"]
        lines = {item["service_id"]: item for item in april.service_details}
        for service_id, contract_id, price, quantity, amount in (
            ("SIM-S0007", "SIM-C0001", "42.50", 47, "1997.50"),
            ("SIM-S0008", "SIM-C0002", "45.50", 26, "1183.00"),
        ):
            with self.subTest(service=service_id):
                self.assertEqual(
                    tuple(lines[service_id][field] for field in
                          ("contract_id", "unit_price", "quantity", "expected_amount")),
                    (contract_id, price, quantity, amount),
                )
        summary = summarize(self.run_result)
        self.assertEqual(summary["settlement_group_count"], 31)
        self.assertEqual(summary["reliable_receivable_amount"], "287468.40")
        self.assertEqual(summary["comparable_paid_amount"], "277900.10")
        self.assertEqual(summary["net_difference"], "9568.30")
        self.assertEqual(summary["held_eligible_payment_amount"], "30010.00")
        self.assertEqual(summary["unmatched_payment_amount"], "875.00")

    def test_cli_reports_are_identical_with_and_without_oracle(self):
        with workspace_temp() as temporary:
            root = Path(temporary)
            input_dir, output_dir = root / "input", root / "reports"
            input_dir.mkdir()
            for name in (*SOURCE_FILES, "expected_anomalies.csv"):
                shutil.copyfile(SAMPLE / name, input_dir / name)
            first = run_cli(input_dir, output_dir)
            self.assertEqual(first.returncode, 0, first.stderr)
            before = {name: (output_dir / name).read_bytes() for name in REPORT_FILES}

            (input_dir / "expected_anomalies.csv").unlink()
            second = run_cli(input_dir, output_dir)
            self.assertEqual(second.returncode, 0, second.stderr)
            for name, original in before.items():
                self.assertEqual((output_dir / name).read_bytes(), original, name)

            summary = json.loads(before["summary.json"])
            self.assertEqual(summary["run_status"], "COMPLETED")
            with (output_dir / "reconciliation_results.csv").open(encoding="utf-8", newline="") as source:
                held = [row for row in csv.DictReader(source) if row["payment_bucket"] == "HELD"]
            self.assertEqual(len(held), 3)
            self.assertTrue(all(not row["expected_amount"] and not row["difference_amount"] for row in held))
            self.assertTrue(all(json.loads(row["raw_payments"]) for row in held))

    def test_cli_reports_unassignable_rows_and_returns_nonzero(self):
        with workspace_temp() as temporary:
            root = Path(temporary)
            input_dir, output_dir = root / "input", root / "reports"
            write_sources(
                input_dir, contracts=[contract()],
                services=[service(), service(service_id="S2", settlement_period="2026-14")],
                payments=[payment(payment_id="P1", hospital_id="")],
            )
            result = run_cli(input_dir, output_dir)
            self.assertEqual(result.returncode, 2)
            self.assertIn("2 issues could not be assigned", result.stderr)
            summary = json.loads((output_dir / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["run_status"], "INCOMPLETE_INPUT")
            with (output_dir / "anomaly_details.csv").open(encoding="utf-8", newline="") as source:
                unassigned = [row for row in csv.DictReader(source) if not row["settlement_period"]]
            self.assertEqual({json.loads(row["related_record_ids"])[0] for row in unassigned}, {"S2", "P1"})
            self.assertTrue(all(json.loads(row["evidence"])["source"]["errors"] for row in unassigned))

    def test_cli_aborts_missing_file_and_names_source(self):
        with workspace_temp() as temporary:
            root = Path(temporary)
            result = run_cli(root, root / "reports")
            self.assertEqual(result.returncode, 1)
            self.assertIn("contracts.csv", result.stderr)
            self.assertFalse((root / "reports" / "summary.json").exists())
