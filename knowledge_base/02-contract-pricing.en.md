# Contract Pricing and Version Control

Document ID: KB-02
Version: 1.0
Language: en
Scope: Synthetic hospital testing reconciliation prototype
Status: SIMULATION

> Simulated business guidance for project demonstrations. This document represents no actual company policy, regulatory requirement or industry law.

## 1. Pricing key and effective dates

Match hospital ID, test type, collection type and service type. Consider contracts effective on the actual service date, including both boundary dates. With inclusive dates, a new revision can start the day after its predecessor expires.

Review guidance: Check the service date against signed version evidence and verify both date boundaries.

## 2. Contract overlap and version conflicts

If more than one contract is active for the same pricing key on the service date, classify the affected record as CONTRACT_OVERLAP. Hold the settlement for human review. Preserve all candidate versions and dates. The reviewer must resolve which version applies before the calculation is rerun.

Review guidance: Compare candidate windows, approvals and version IDs with the contract owner. Leave unresolved amounts unknown.

## 3. Missing contract and billing unit

No active pricing match is MISSING_CONTRACT. A unique valid match supplies the unit price and contractual billing unit. A conflicting unit is INVALID_DATA. Multiply the recorded quantity by the contractual price. A pool count already expresses the contractual quantity.

Review guidance: Verify the contract key and billing unit before using the quantity. Preserve the original record for review.
