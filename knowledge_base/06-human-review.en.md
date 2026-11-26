# Human Review and Escalation

Document ID: KB-06
Version: 1.0
Language: en
Scope: Synthetic hospital testing reconciliation prototype
Status: SIMULATION

> Simulated business guidance for project demonstrations. This document represents no actual company policy, regulatory requirement or industry law.

## 1. Escalate contract overlap for human review

For contract overlap or a version conflict, send the candidate contract IDs, service date and overlap window to the contract owner and finance reviewer. Keep the group on hold until the owner provides version evidence and the reviewer approves the correction.

Review guidance: Record the supporting approvals, reviewer, decision time and rationale outside the source data, then rerun reconciliation.

## 2. Prioritize unresolved control exceptions

Prioritize held groups, contract conflicts, missing contracts, invalid records and duplicate-payment controls for review. Keep deterministic business priority separate from optional AI suggestions. A reviewer checks evidence before confirming a disposition.

Review guidance: Route unresolved source issues to the responsible owner and retain the related records for review.

## 3. Record evidence and authority limits

Record the reviewer, date and time, rationale and supporting evidence separately from source data. AI provides read-only evidence and advisory guidance. A human reviewer owns settlement acceptance and any correction. This prototype does not execute payments or store review decisions.

Review guidance: Independently verify evidence and document any human decision outside the prototype.
