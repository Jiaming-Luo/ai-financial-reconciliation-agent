# Payment Reconciliation SOP

Document ID: KB-03
Version: 1.0
Language: en
Scope: Synthetic hospital testing reconciliation prototype
Status: SIMULATION

> Simulated business guidance for project demonstrations. This document represents no actual company policy, regulatory requirement or industry law.

## 1. Group and validate receipts

Use the hospital ID and assigned settlement period to group receipts. A payment date may be in another calendar month. Multiple distinct valid references can be legitimate partial receipts in the same group.

Review guidance: Confirm the settlement assignment and trace each receipt to its reference.

## 2. Duplicate payment and conflicting references

Check payment references across the full input. If valid copies share the same hospital, payment date, settlement period, amount and currency, flag DUPLICATE_PAYMENT and count the lexicographically smallest payment ID once. Keep the review flag. Conflicting copies or an invalid copy leave the reference unresolved and block affected groups.

Review guidance: Compare the original receipts, retain all evidence, and ask a reviewer to confirm any reference conflict.

## 3. Missing and unmatched receipts

A calculable service group without receipts is MISSING_PAYMENT. A valid payment group without service rows is UNMATCHED_PAYMENT. The absence of a receipt alone does not determine lateness. Track the provisional receipt or service evidence without allocating it to another period.

Review guidance: Verify the assigned month and source import coverage with the finance reviewer.
