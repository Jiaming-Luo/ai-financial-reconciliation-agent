# Data Dictionary

The three source CSVs are UTF-8 with headers and comma-delimited fields. All source columns are required. The tables below describe valid source values, with intentional fixture exceptions listed at the end.

## contracts.csv

| Field | Type | Meaning and constraints | Example |
| --- | --- | --- | --- |
| contract_id | String | Unique, nonempty contract version ID | SIM-C0001 |
| hospital_id | String | Nonempty synthetic hospital identifier | SIM-H001 |
| test_type | Enum | Testing discipline. Initial values are `PCR` and `ANTIGEN` | PCR |
| collection_type | Enum | Collection method. `SINGLE`, `POOL_10` or `POOL_20` | SINGLE |
| service_type | Enum | Business type. `MASS_SCREENING` or `SELF_PAID` | MASS_SCREENING |
| billing_unit | Enum | Contractual unit. Initial values are `SAMPLE` and `POOL` | SAMPLE |
| unit_price | Decimal (2 places) | Positive CNY amount per contractual unit | 42.50 |
| effective_date | Date (YYYY-MM-DD) | First valid day, inclusive | 2026-01-01 |
| expiry_date | Date (YYYY-MM-DD) | Last valid day, inclusive. On or after effective date | 2026-04-14 |
| currency | Enum | `CNY` only | CNY |

## service_records.csv

| Field | Type | Meaning and constraints | Example |
| --- | --- | --- | --- |
| service_id | String | Unique, nonempty identifier of a service row | SIM-S0001 |
| hospital_id | String | Nonempty synthetic hospital identifier | SIM-H001 |
| service_date | Date (YYYY-MM-DD) | Actual service day used for contract pricing | 2026-01-07 |
| settlement_period | Month (YYYY-MM) | Explicit settlement month with valid year and month | 2026-01 |
| test_type | Enum | Testing discipline from the contract vocabulary | PCR |
| collection_type | Enum | Collection method from the contract vocabulary | SINGLE |
| service_type | Enum | Business type from the contract vocabulary | MASS_SCREENING |
| billing_unit | Enum | Reported unit. Must equal the uniquely matched contract's unit | SAMPLE |
| quantity | Integer | Positive count in contractual units. Use the recorded count directly for pooled services | 10 |
| reported_amount | Decimal (2 places) | Nonnegative CNY amount supplied by the service source | 425.00 |

## payments.csv

| Field | Type | Meaning and constraints | Example |
| --- | --- | --- | --- |
| payment_id | String | Unique, nonempty source row ID, including duplicate copies | SIM-P0001 |
| hospital_id | String | Nonempty synthetic hospital identifier | SIM-H001 |
| payment_date | Date (YYYY-MM-DD) | Actual payment day. May fall outside the settlement month | 2026-02-03 |
| settlement_period | Month (YYYY-MM) | Explicit settlement month this payment applies to | 2026-01 |
| payment_amount | Decimal (2 places) | Positive amount received | 1200.00 |
| payment_reference | String | Nonempty transaction reference. Expected to identify one transaction across the entire payment file | SIM-REF-0001 |
| currency | Enum | `CNY` only | CNY |

## Relationships and data quality

- Match a service to a contract on `hospital_id`, `test_type`, `collection_type` and `service_type`, with `effective_date <= service_date <= expiry_date`. Expect exactly one candidate. A contract version can price many services. Match by date and key before validating the billing unit so a unit mismatch is visible as invalid data.
- Contract windows for the same key must be disjoint. With inclusive endpoints, a revision can start the calendar day after the previous expiry. Step 03 detects overlaps where an affected service falls in the overlapping window and blocks that group's finalization.
- Check ID uniqueness, exact headers, required values, valid calendar dates/months, enums, positive quantities and prices/payments, nonnegative reported amounts, and two decimal places with a dot and no thousands separators. Treat monetary values as Decimal or integer cents. Service amounts inherit CNY. There is no currency conversion.
- Compute service receivable from the uniquely matched contract's unit price times the quantity. Reported amounts are retained for comparison. Missing and ambiguous matches or invalid service inputs block the affected settlement group from finalization.
- Services and payments are independently aggregated by `(hospital_id, settlement_period)`. The relationship is many-to-many at the group level and has no line-level foreign key. A service group with no payment and a payment group with no service are valid input shapes that require review. Distinct payment references are legitimate separate receipts. Apply the file-wide duplicate/reference-conflict rules and the expected-minus-paid difference in the [PRD](PRD.md#7-financial-and-exception-rules).

## expected_anomalies.csv

Test oracle only. The rule engine processes the three source tables. Tests compare its outputs against this file after calculation.

| Field | Type | Meaning and constraints | Example |
| --- | --- | --- | --- |
| case_id | String | Unique control or exception case ID | CASE-001 |
| hospital_id | String | Hospital associated with the case group | SIM-H001 |
| settlement_period | Month (YYYY-MM) | Settlement month associated with the case | 2026-01 |
| service_id | String or empty | Service evidence ID for line-level cases | SIM-S0187 |
| payment_id | String or empty | Payment evidence ID where a specific payment is relevant | SIM-P0001 |
| expected_type | Enum | Outcome code from the PRD rules | MATCHED |
| expected_result | String | Human-readable expected outcome and review rationale | Two payments total CNY 9284.00 with zero variance. |

Each populated evidence ID must resolve to the case's hospital and settlement month. The fixture contains one explicit matched control plus ordinary balanced groups. The intentional exceptions are one missing payment, one short payment, one excess payment, one exact duplicate, one reported amount discrepancy, one valid test type without a contract, one single-day overlap, one payment-only group and one negative quantity. Each case targets a distinct settlement group. The blocked groups retain their simulated baseline payments for review and have no final calculated variance until the source problem is resolved.
