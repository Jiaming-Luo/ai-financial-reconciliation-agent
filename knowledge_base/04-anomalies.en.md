# Anomaly Classification and Handling

Document ID: KB-04
Version: 1.0
Language: en
Scope: Synthetic hospital testing reconciliation prototype
Status: SIMULATION

> Simulated business guidance for project demonstrations. This document represents no actual company policy, regulatory requirement or industry law.

## 1. Collection and balance exceptions

MISSING_PAYMENT means a calculable group has no receipt. UNDERPAYMENT means eligible receipts exist and the receivable exceeds paid. OVERPAYMENT means paid exceeds receivable. UNMATCHED_PAYMENT identifies an eligible payment group without service rows.

Review guidance: Inspect source receipts and settlement assignment. Record a proposed disposition for review.

## 2. Pricing exceptions

PRICE_MISMATCH means the reported amount differs from the unique valid contract charge. The contract charge stays usable while the finding remains open for review. MISSING_CONTRACT identifies no active contract. CONTRACT_OVERLAP identifies multiple active versions for the same service date. Unresolved pricing holds the affected group.

Review guidance: Compare source quantity, reported amount and contract candidates to identify review evidence.

## 3. Duplicate and invalid records

DUPLICATE_PAYMENT marks repeated payment references. Identical valid copies are counted once; conflicting or invalid copies stay unresolved. INVALID_DATA includes malformed dates, invalid values and a billing-unit conflict. Holds apply when these issues prevent reliable group calculation.

Review guidance: Preserve affected rows and the independent exception flags for review.
