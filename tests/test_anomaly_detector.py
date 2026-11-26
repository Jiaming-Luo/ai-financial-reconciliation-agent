import unittest

from src.reconciliation import reconcile
from src.reporting import summarize
from tests.fixtures import contract, load_fixture, payment, service


class AnomalyDetectorTests(unittest.TestCase):
    def test_exact_reference_copies_are_counted_once_with_evidence(self):
        run = reconcile(load_fixture(
            contracts=[contract()], services=[service()],
            payments=[payment(payment_id="P9"), payment()],
        ))
        result, = run.settlements
        self.assertEqual(result.settlement_status, "MATCHED")
        self.assertTrue(result.review_required)
        self.assertEqual(result.paid_cents, 30)
        self.assertEqual(len(result.raw_payments), 2)
        issue, = result.anomalies
        self.assertEqual(issue.anomaly_type, "DUPLICATE_PAYMENT")
        self.assertEqual(issue.evidence["selected_payment_id"], "P1")
        self.assertEqual(len(issue.evidence["sources"]), 2)

    def test_same_id_exact_copies_still_produce_duplicate_evidence(self):
        run = reconcile(load_fixture(payments=[payment(), payment()]))
        result, = run.settlements
        self.assertEqual(len(result.eligible_payments), 1)
        issue = next(issue for issue in result.anomalies if issue.anomaly_type == "DUPLICATE_PAYMENT")
        self.assertEqual([row["line"] for row in issue.evidence["sources"]], [2, 3])

    def test_reference_conflicts_hold_every_group(self):
        for changes in (
            {"payment_amount": "0.31"}, {"settlement_period": "2026-02"},
            {"hospital_id": "TEST-H2"}, {"payment_date": "2026-01-27"},
            {"currency": "USD"},
        ):
            with self.subTest(changes=changes):
                run = reconcile(load_fixture(
                    contracts=[contract()], services=[service()],
                    payments=[payment(), payment(payment_id="P2", **changes)],
                ))
                self.assertTrue(all(g.settlement_status == "REVIEW_REQUIRED" for g in run.settlements))
                self.assertTrue(all(g.paid_cents is None and g.difference_cents is None for g in run.settlements))
                self.assertTrue(all("DUPLICATE_PAYMENT" in g.anomaly_types for g in run.settlements))
                self.assertEqual(summarize(run)["eligible_payment_count"], 0)
                self.assertEqual(run.settlements[0].expected_cents, 30)

    def test_unattributed_conflicting_payment_blocks_known_copy(self):
        run = reconcile(load_fixture(
            contracts=[contract()], services=[service()],
            payments=[payment(), payment(payment_id="P2", settlement_period="")],
        ))
        result, = run.settlements
        self.assertEqual(result.settlement_status, "REVIEW_REQUIRED")
        self.assertEqual(result.anomaly_types, ["DUPLICATE_PAYMENT"])
        self.assertEqual({a.anomaly_type for a in run.unassigned_anomalies},
                         {"INVALID_DATA", "DUPLICATE_PAYMENT"})
        self.assertEqual(summarize(run)["run_status"], "INCOMPLETE_INPUT")

    def test_balance_and_price_and_duplicate_labels_are_independent(self):
        run = reconcile(load_fixture(
            contracts=[contract()], services=[service(reported_amount="0.31")],
            payments=[payment(), payment(payment_id="P2")],
        ))
        result, = run.settlements
        self.assertEqual(result.settlement_status, "MATCHED")
        self.assertEqual(result.anomaly_types, ["DUPLICATE_PAYMENT", "PRICE_MISMATCH"])
        price = next(issue for issue in result.anomalies if issue.anomaly_type == "PRICE_MISMATCH")
        self.assertEqual((price.expected_cents, price.actual_cents, price.difference_cents), (30, 31, -1))
        summary = summarize(run)
        self.assertEqual(summary["anomalous_group_count"], 1)
        self.assertEqual(summary["comparable_receivable_amount"], "0.30")
        self.assertEqual(summary["comparable_paid_amount"], "0.30")
        self.assertEqual(summary["net_difference"], "0.00")

    def test_difference_sign_and_missing_payment(self):
        for source_rows, status, difference in (
            ([], "MISSING_PAYMENT", 30),
            ([payment(payment_amount="0.29")], "UNDERPAYMENT", 1),
            ([payment(payment_amount="0.31")], "OVERPAYMENT", -1),
        ):
            with self.subTest(status=status):
                run = reconcile(load_fixture(contracts=[contract()], services=[service()], payments=source_rows))
                result, = run.settlements
                issue, = result.anomalies
                self.assertEqual(result.settlement_status, status)
                self.assertEqual(issue.anomaly_type, status)
                self.assertEqual(result.difference_cents, difference)
                self.assertEqual(issue.difference_cents, difference)
                self.assertTrue(issue.recommended_action)

    def test_invalid_payment_amount_blocks_total_but_keeps_other_eligible_receipts(self):
        run = reconcile(load_fixture(
            contracts=[contract()], services=[service()],
            payments=[payment(), payment(payment_id="P2", payment_reference="REF-2", payment_amount="NaN")],
        ))
        result, = run.settlements
        self.assertEqual(result.settlement_status, "REVIEW_REQUIRED")
        self.assertEqual(result.anomaly_types, ["INVALID_DATA"])
        self.assertIsNone(result.paid_cents)
        self.assertIsNone(result.difference_cents)
        self.assertEqual(summarize(run)["held_eligible_payment_amount"], "0.30")
