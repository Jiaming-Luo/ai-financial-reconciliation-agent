import unittest

from src.reconciliation import reconcile
from src.reporting import summarize
from tests.fixtures import contract, load_fixture, payment, service


class ReconciliationTests(unittest.TestCase):
    def test_inclusive_boundaries_and_revision_day(self):
        run = reconcile(load_fixture(
            contracts=[
                contract(expiry_date="2026-01-14"),
                contract(contract_id="C2", effective_date="2026-01-15", unit_price="0.20"),
            ],
            services=[
                service(service_id=f"S{day}", service_date=f"2026-01-{day}", reported_amount=amount)
                for day, amount in (("01", "0.30"), ("14", "0.30"), ("15", "0.60"), ("31", "0.60"))
            ],
            payments=[payment(payment_amount="1.80")],
        ))
        result, = run.settlements
        self.assertEqual(
            [(line["contract_id"], line["unit_price"], line["expected_amount"])
             for line in result.service_details],
            [("C1", "0.10", "0.30")] * 2 + [("C2", "0.20", "0.60")] * 2,
        )
        self.assertEqual(result.settlement_status, "MATCHED")
        self.assertEqual(result.expected_cents, 180)

    def test_outside_window_or_wrong_key_is_missing_contract(self):
        for row in (service(service_date="2026-02-01"), service(service_type="MASS_SCREENING")):
            with self.subTest(row=row):
                run = reconcile(load_fixture(contracts=[contract()], services=[row], payments=[payment()]))
                result, = run.settlements
                self.assertEqual(result.settlement_status, "REVIEW_REQUIRED")
                self.assertEqual(result.anomaly_types, ["MISSING_CONTRACT"])
                self.assertIsNone(result.expected_cents)
                self.assertIsNone(result.difference_cents)
                self.assertEqual(summarize(run)["held_eligible_payment_amount"], "0.30")

    def test_inclusive_shared_boundary_is_contract_overlap(self):
        run = reconcile(load_fixture(
            contracts=[contract(), contract(contract_id="C2", effective_date="2026-01-31")],
            services=[service(service_date="2026-01-31")],
        ))
        result, = run.settlements
        self.assertEqual(result.settlement_status, "REVIEW_REQUIRED")
        issue, = result.anomalies
        self.assertEqual(issue.anomaly_type, "CONTRACT_OVERLAP")
        self.assertEqual(issue.related_record_ids, ["S1", "C1", "C2"])
        self.assertIsNone(result.expected_cents)
        self.assertIsNone(issue.difference_cents)

    def test_invalid_candidate_is_not_silently_excluded_from_pricing(self):
        run = reconcile(load_fixture(
            contracts=[contract(), contract(contract_id="C2", unit_price="oops")],
            services=[service(), service(service_id="S2")],
            payments=[payment()],
        ))
        result, = run.settlements
        issue, = result.anomalies
        self.assertEqual(issue.anomaly_type, "INVALID_DATA")
        self.assertEqual(issue.related_record_ids, ["C2"])
        self.assertIsNone(result.expected_cents)
        self.assertIsNone(summarize(run)["reliable_receivable_amount"])

    def test_billing_unit_is_checked_after_contract_match(self):
        run = reconcile(load_fixture(contracts=[contract()], services=[service(billing_unit="POOL")]))
        issue, = run.anomalies
        self.assertEqual(issue.anomaly_type, "INVALID_DATA")
        self.assertEqual(issue.evidence["contract_id"], "C1")
        self.assertIsNone(run.settlements[0].expected_cents)

    def test_pool_quantities_are_used_directly_and_split_cents_are_exact(self):
        for method in ("POOL_10", "POOL_20"):
            with self.subTest(method=method):
                run = reconcile(load_fixture(
                    contracts=[contract(collection_type=method, billing_unit="POOL")],
                    services=[service(collection_type=method, billing_unit="POOL")],
                    payments=[
                        payment(payment_amount="0.10"),
                        payment(payment_id="P2", payment_reference="REF-2", payment_amount="0.20",
                                payment_date="2026-02-01"),
                    ],
                ))
                result, = run.settlements
                self.assertEqual(result.settlement_status, "MATCHED")
                self.assertEqual((result.expected_cents, result.paid_cents, result.difference_cents),
                                 (30, 30, 0))
                self.assertEqual(len(result.eligible_payments), 2)

    def test_invalid_service_does_not_hide_unrelated_valid_group(self):
        run = reconcile(load_fixture(
            contracts=[contract()],
            services=[service(quantity="-1"), service(service_id="S2", settlement_period="2026-02")],
            payments=[payment(), payment(payment_id="P2", payment_reference="REF-2",
                                         settlement_period="2026-02")],
        ))
        held, matched = run.settlements
        self.assertIsNone(held.expected_cents)
        self.assertIsNone(held.difference_cents)
        self.assertEqual(held.paid_cents, 30)
        self.assertEqual(matched.settlement_status, "MATCHED")
        self.assertEqual(summarize(run)["reliable_receivable_amount"], "0.30")

    def test_unmatched_payment_never_creates_zero_receivable(self):
        run = reconcile(load_fixture(payments=[payment()]))
        result, = run.settlements
        self.assertEqual(result.settlement_status, "UNMATCHED_PAYMENT")
        self.assertIsNone(result.expected_cents)
        self.assertIsNone(result.difference_cents)
        summary = summarize(run)
        self.assertIsNone(summary["net_difference"])
        self.assertEqual(summary["unmatched_payment_amount"], "0.30")
