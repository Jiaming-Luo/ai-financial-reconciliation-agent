# Data Quality and Validation

Document ID: KB-05
Version: 1.0
Language: en
Scope: Synthetic hospital testing reconciliation prototype
Status: SIMULATION

> Simulated business guidance for project demonstrations. This document represents no actual company policy, regulatory requirement or industry law.

## 1. File and identifier checks

Validate the three source CSV schemas, required values and source row identifiers. Contract IDs, service IDs and payment IDs identify rows. Repeated transaction references use the dedicated payment rule. Retain invalid raw rows and report issues to reviewers.

Review guidance: Compare errors against the data dictionary and preserve row identifiers.

## 2. Date, quantity and money checks

Validate calendar dates and settlement months. Contract prices, receipt amounts and integer quantities must be positive. Reported amounts can be zero. Monetary values use CNY with two decimal places. A matched contract determines the permitted billing unit.

Review guidance: Check the source format and contract unit before requesting a correction.

## 3. Provisional run and fixture isolation

An issue without a reliable group may make the run provisional. Report the issue and withhold portfolio monetary totals in the Agent. Expected anomaly cases are test fixtures and are excluded from financial calculation and knowledge answers.

Review guidance: Resolve unassigned issues before using portfolio totals. Use only synthetic inputs in this prototype.
