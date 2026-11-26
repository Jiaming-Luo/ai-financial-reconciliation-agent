# Financial Reconciliation Policy

Document ID: KB-01
Version: 1.0
Language: en
Scope: Synthetic hospital testing reconciliation prototype
Status: SIMULATION

> Simulated business guidance for project demonstrations. This document represents no actual company policy, regulatory requirement or industry law.

## 1. Settlement scope and signed difference

Group service charges and eligible receipts by hospital ID and explicit settlement month. Use CNY in exact cents. The signed difference is calculated receivable minus paid, with a zero-cent tolerance. A positive difference indicates underpayment if an eligible receipt exists. A negative difference indicates overpayment.

Review guidance: Confirm the hospital, settlement period and comparison status before interpreting the difference.

## 2. Held settlements and unknown amounts

A missing or ambiguous active contract, invalid input or unresolved payment reference can hold a settlement. The group remains REVIEW_REQUIRED. Unresolved receivable and difference stay unknown where applicable, even when a known eligible payment is shown. Held amounts are excluded from comparable totals.

Review guidance: Verify the blocking source issue and retain the payment evidence for manual review.

## 3. Balance versus exceptions

A zero difference indicates a matched balance when amounts are reliable. Independent exceptions, such as an exact duplicate receipt or a reported price mismatch, still require review. A missing receipt does not establish that a payment is overdue.

Review guidance: Review both the settlement status and each recorded anomaly before drawing a conclusion.
