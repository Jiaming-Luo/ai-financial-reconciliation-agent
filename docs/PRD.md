# Product Requirements Document

[简体中文](PRD_CN.md) · [Data dictionary](data_dictionary.md)

## 1. Background and pain points

Hospital testing fees depend on the hospital, test, collection method, service type and applicable contract version. Manual review can miss a price change, apply the wrong unit to pooled tests or misread split and late payments. Tracing these differences back to source records takes time.

## 2. Target users

- Finance reviewers who verify testing charges and reconcile hospital payments.
- Testing operations staff who verify service counts, collection methods and reported amounts.
- Contract and finance approvers who resolve pricing conflicts and confirm review decisions.

## 3. Product goals and scope

Build a personal process-improvement prototype using synthetic data. The MVP should show the applicable contract, explain the expected charge and payment variance, and give reviewers the source evidence. It covers single collection, pools of 10 or 20, mass screening and self-paid testing. Live hospital systems, real patient or corporate records, bank integration, payment execution, and multi-currency settlement are out of scope.

## 4. User scenarios

- A reviewer compares two services on consecutive dates across a contract price change.
- A reviewer reconciles a month with two valid payments, including one made the following month.
- An approver reviews an ambiguous contract, a missing contract or an invalid quantity before accepting the affected month's result.
- A reviewer traces a duplicated payment or an incorrect reported charge and records the disposition.

## 5. Core workflow

1. Import and validate contract, service and payment CSVs. Retain source identifiers and raw row values for traceability.
2. Resolve each valid service row to the contract key and inclusive service-date window. Check the billing unit and compute the expected charge where the match is unique and valid.
3. Detect duplicate payments and aggregate eligible payments and service receivables by hospital and settlement period. Hold any group with unresolved source validation or pricing for review.
4. Present exception evidence and group status. A reviewer records a decision or corrects the source, then reruns the calculation. Optional AI assistance explains existing results.

## 6. Functional requirements

| Priority | Requirement |
| --- | --- |
| P0 | Import three CSVs and validate keys, types, dates, currency, billing units, and numeric ranges. |
| P0 | Match versioned contracts by service date and compute exact line and group amounts. |
| P0 | Reconcile at hospital and month level, accept split and cross-month payments, and expose exception evidence with source IDs and amounts. |
| P0 | Hold unresolved groups and support a human decision record with reviewer, timestamp, reason and supporting evidence. |
| P1 | Provide a read-only AI explanation and Q&A grounded in calculated results and source evidence. |
| P1 | Retrieve simulated bilingual policy sections, cite them separately from financial evidence, and report insufficient knowledge when the topic is unsupported. |
| P1 | Provide a Streamlit review view with filters, drill-down and export of results. |
| P2 | Add English and Simplified Chinese UI and AI output selection. Centralize strings, default to English and leave room for Traditional Chinese. |

## 7. Financial and exception rules

- The pricing key is hospital, test type, collection type and service type. Use the service date and inclusive contract boundaries. A unique active contract supplies the price and billing unit. Compare the service billing unit with that contract. Use the entered quantity as the number of contractual units, including for pools.
- Use Decimal or integer cents. All monetary values are CNY with two decimal places. Compute line receivable as quantity × unit price. A different reported amount yields `PRICE_MISMATCH`. The contract amount remains usable for group settlement and the line still requires review.
- A key with no active contract yields `MISSING_CONTRACT`. Multiple active contracts yield `CONTRACT_OVERLAP`. A malformed or out-of-domain value, including a unit mismatch after a unique contract match, yields `INVALID_DATA`. Hold affected groups for review and leave their final receivable or variance unset where an input is unresolved.
- Match by `hospital_id` and `settlement_period`. Payment date does not determine settlement month. Sum eligible payments, including multiple distinct references in the same group.
- Check each payment reference across the input file. If valid rows sharing a reference have identical hospital, date, settlement period, amount and currency, flag `DUPLICATE_PAYMENT`, retain the lexicographically smallest payment ID for the sum, and keep the review flag even when the balance is zero. If the details differ or a copy is invalid, flag the reference as unresolved and hold all affected groups without a final variance.
- Use receivable minus paid as signed variance. For groups with reliable amounts, no payment gives `MISSING_PAYMENT`, a positive variance with one or more eligible payments gives `UNDERPAYMENT`, a negative variance gives `OVERPAYMENT`, and zero gives `MATCHED` for the balance. Missing payment records do not establish lateness. A valid payment group with no service rows gives `UNMATCHED_PAYMENT`. Preserve independent flags alongside the balance result. Use `REVIEW_REQUIRED` when a group amount cannot be resolved.

## 8. Non-functional requirements

- Ensure repeatable results for identical inputs and trace each amount or exception to source rows and applicable contract IDs.
- Validate at least the delivered sample size in a local run without network access for P0. Preserve exact cent arithmetic regardless of display language.
- Read the agreed CSV schemas with explicit validation and surface row-level errors. Keep original source records intact.

## 9. Data safety and human review

Use synthetic inputs only and keep credentials out of sample data and Git. Show the reviewer source rows, candidate contracts, calculated amounts and the reason for each flag. Record reviewer decisions separately from raw inputs, including who decided, when and why. AI may summarize or explain evidence and has no authority over financial calculations, review decisions or payment execution. Test expectations are isolated from rule execution.

## 10. MVP acceptance criteria

- Import and validate the three source CSVs with the documented schema and identify deliberate invalid records without stopping unrelated groups.
- Select the correct price on both sides of a revision boundary and reproduce expected group balances using exact cents.
- Correctly handle split and cross-month payments. Reproduce all ten named control and exception outcomes by calculating from source CSVs. Compare to the expectation CSV only after producing actual results.
- Show actionable evidence for each exception, hold unresolved groups and record a human disposition with an audit trail.

## 11. Current development status

Steps 01–03 delivered the workspace, deterministic sample data and reconciliation engine. Step 03 established the current variance direction and payment-reference rule. Step 04 delivered v3 bilingual advisory analysis, verified by the user on Live Qwen. OpenAI analysis has offline validation. Step 05 completed bilingual, read-only Q&A for one question with up to five model requests and eight tool executions. The final contract accepts answer status and verified evidence IDs, with required financial fields rendered by Python. The user verified Summary, Hospital and Multi through Live Qwen. All 187 offline tests passed, and the Step 05 Agent core is frozen. Step 06 implements local BM25 retrieval and policy citations for knowledge-only and mixed questions. Step 06 passed all 207 offline tests, and the user verified English RAG, Chinese RAG and combined Q&A on Live `qwen3.8-flash` after Step 06C. The MVP uses synthetic data and simulated policy. BM25 can miss paraphrases, and model output remains subject to strict validation. Step 06 is frozen at Checkpoint 02.

Step 07 passed final acceptance for the five bilingual local Streamlit views. The app defaults to Mock. The user verified Live Agent + RAG and completed the Live Anomaly Review retest after Step 07G. All 227 offline tests passed, including simulated HTTP tests for accepted output and failure isolation. AI suggested priorities remain advisory, and the deterministic business priorities and human-review requirements remain authoritative. Checkpoint 03 freezes the Step 01–07 scope. Production validation remains pending. Persistent review decisions and multi-question memory remain planned. [Architecture](architecture.md) · [LLM integration](llm_integration.md) · [Final acceptance](test_report.md#step-07-final-acceptance-and-checkpoint-03)

## 12. Initial assumptions and known limitations

Each service row belongs to one settlement month, supplied by the source and independent of service-date pricing. Each payment applies to one hospital and month. Hospital IDs come from the source exports and have no separate master table in this model. Contract end dates are mandatory. Quantities are positive integers, refunds and credits are excluded, and the variance tolerance is zero cents. The imported payment feed is assumed to use globally unique transaction references. The prototype does not allocate payments across months or to individual service lines, handle tax or discounts separately, or prove that a transfer occurred.
