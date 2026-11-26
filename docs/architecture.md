# Project Architecture

## Module responsibilities and data flow

| Module | Responsibility |
| --- | --- |
| `main.py` | Parse input and output directories, run the pipeline, and report completion or input failures. |
| `src/data_loader.py` | Read the three named source CSVs, validate schemas and rows, and keep raw values, source lines and errors. |
| `src/reconciliation.py` | Index contracts by pricing key, price service lines, assign receipts to settlement groups and assemble results and evidence. |
| `src/anomaly_detector.py` | Resolve duplicate payment references, classify balances, and provide deterministic review actions. |
| `src/reporting.py` | Serialize settlement results, anomaly evidence and aggregate metrics to CSV and JSON. |

`main.py` calls `load_data(input_dir)`, `reconcile(source)` and `write_reports(run, output_dir)`. Other Python callers can use the loader and reconcile function directly. The engine reads `contracts.csv`, `service_records.csv` and `payments.csv`. Tests compare completed results against the separate expected-case file. The engine and CLI have no dependency on it.

## Validation and pricing

- A CSV header must contain exactly the documented field names. Column order may vary. A missing, unreadable or structurally invalid file aborts the run and names the source. Recoverable row errors retain raw values and the starting source line.
- Invalid service rows and invalid payment rows hold their respective side of the affected group. Unassignable issues appear in the anomaly report with blank group fields. In this case the CLI writes provisional reports for attributable rows, uses `INCOMPLETE_INPUT` and exits with code 2. A fatal read or write error returns code 1. A completed run returns 0 even when it contains financial anomalies.
- The pricing key uses hospital, test, collection and service type. The service date must fall within the contract interval including both endpoints. An invalid contract that could cover the service blocks pricing even if a valid candidate also exists. If the date range itself is unusable, the engine uses any reliable boundary or treats all dates for that key as potentially affected. Valid overlapping candidates generate `CONTRACT_OVERLAP` on affected services.
- The uniquely effective contract supplies the unit and price. A mismatch with the service billing unit blocks the line. The line charge is the entered quantity multiplied by that price. Pool quantities are already expressed in contractual units. The line evidence includes the source ID, contract ID, unit, price, quantity and computed amount when available.
- Source money requires exactly two decimal places. The engine parses prices and amounts into integer cents, multiplies by integers and sums exactly. There is no rounding during calculation. Overprecision is reported as invalid input. A valid but different reported amount creates `PRICE_MISMATCH` while the contract-priced amount remains usable.

## Payment and balance rules

- Settle by hospital and source settlement month. The payment date is evidence and may fall in a later month. Each distinct valid payment reference represents a separate receipt.
- Step 03 replaces the Step 02 hospital-scoped reference rule with file-wide matching so a reference with conflicting hospital, period, date, amount or currency cannot be applied automatically. Identical valid copies count once using the smallest payment ID and then earliest source line for an identical ID. Conflicting or invalid copies sharing the same reference hold affected groups and all copies of that reference are excluded from eligible amounts. Other identifiable receipts in those groups remain visible.
- Step 03 reverses the earlier variance direction to `expected_amount - paid_amount` as specified in the implementation requirements. A positive balance signals shortfall and a negative balance signals excess. No payment record with a reliable receivable is classified as missing payment. Payment deadlines and overdue assessment are outside the data model.
- Settlement status describes the balance. Anomaly types describe review findings. A zero balance can coexist with `DUPLICATE_PAYMENT` and `PRICE_MISMATCH`. A group with an unresolved side has status `REVIEW_REQUIRED`. A payment-only group with valid receipts is `UNMATCHED_PAYMENT` with an unknown receivable and difference.

## Output semantics

| Report | Data |
| --- | --- |
| `reconciliation_results.csv` | One row per group. Includes settlement status, review flag, distinct anomaly labels, monetary fields and source evidence. JSON cells contain service details and both raw and eligible payment rows. |
| `anomaly_details.csv` | One row per finding. Includes report-local anomaly ID, type, group, related record IDs, evidence, applicable monetary values and a rule-based review action. Arrays and objects are JSON cells. |
| `summary.json` | Counts groups once, counts findings by type, and partitions eligible payments into comparable, held and unmatched buckets. Includes the held groups and which side of their balance is known. |

Money is serialized as two-decimal CNY strings. Unknown amounts are blank in CSV and `null` in JSON. A true zero balance or an absence of effective receipts in a confirmed no-payment group is represented by `0.00`. Unresolved payment rows do not contribute to eligible totals. The net difference sums comparable groups only. Missing payments and partial underpayments are reported separately and together as total shortfall. Overpayment amount is shown as a positive magnitude in the summary.

## Scope

The prototype uses synthetic data and an in-memory batch run. It detects contract overlaps encountered during service pricing. A standalone audit of unused contract windows, persisted reviewer decisions, allocation across settlement groups, refunds, due dates and live payments are outside the financial engine. Report files are overwritten on each successful run to the same output directory.

## Step 04 advisory analysis

`analyze.py` calls `context_builder.build_context()` on the three completed engine reports. `llm_analyzer.analyze()` passes a minimized input to the selected provider in `llm_client.py`, which uses the shared contract in `prompts.py`. `output_validator.py` validates the response against supplied anomaly types and evidence. The analyzer renders validated prose alongside amounts copied directly from the engine reports.

The analysis CLI consumes completed artifacts independently of the engine. It only writes files named `ai_analysis_*`. Mock runs locally, while OpenAI analysis has offline validation. Incomplete input produces a review-only report with aggregate figures withheld. Fatal or inconsistent inputs are rejected before the provider is constructed. See the [LLM integration guide](llm_integration.md).

## Step 04B provider routing

`create_provider()` selects Mock, OpenAI or Qwen. Mock remains the default. `qwen_provider.py` uses the installed OpenAI SDK for Alibaba Cloud's Responses endpoint and shares the prompt, schema and local output validator. The wire format nests the schema inside `text.format.json_schema`. The OpenAI adapter retains its existing endpoint and request format.

The Qwen adapter reads its own credential and validates the configured HTTPS base URL before creating the client. Its HTTP client disables redirects and environment proxies. A request hook verifies the exact destination and replaces inherited SDK headers with the headers required for the DashScope request. The adapter checks the response envelope and gives the analysis layer model text, model name and available token counts. `scripts/verify_qwen_live.py` provides separate, explicitly enabled connectivity and structured verification with a zero-retry policy. See the [LLM integration guide](llm_integration.md).

## Step 04C.2 structured hypotheses

The user confirmed Qwen basic connectivity. The later single-finding response reached a local rule that tried to recognize tentative phrasing. The raw response was unavailable. The provider contract now represents each cause as a catalog code and a list of evidence references.

`context_builder.py` derives evidence roles from the existing financial artifacts. `hypothesis_catalog.py` defines type applicability, minimum references by role, bilingual descriptions and the human review requirement. The input offers only choices whose evidence requirements can be met. The validator checks code membership, type, citation scope and required roles for each selected cause before the renderer maps references back to source IDs. No request data contains expected cases or business amounts. The renderer generates the executive summary, fixed disclaimers and cause wording. Other model prose remains advisory and is screened for common financial and operational claims.

The catalog trades breadth for a controllable MVP. `INSUFFICIENT_EVIDENCE` is a model-selected outcome with no minimum citations. A missing or invalid model selection fails validation. The reconciliation engine remains the source of all financial amounts and availability. The user later verified one Live finding with the cause-code contract.

## Step 04C.2 final structured output

The next Live full run reached the numeric-content check for the sixth finding's model-generated explanation. The v3 contract moves factual explanations and fixed disclosures to the renderer. The provider selects hypotheses, manual action codes, citations and priority. The builder offers evidence-eligible codes for each finding. The same strict validator checks both catalogs and requires every finding before publication.

After core validation, a separate screen checks the nullable supplementary note. Rejection yields a redacted warning and `completed_with_omissions`. The renderer preserves the core and emits the rejection state without the offending text. Invalid core output fails before the analyzer constructs a report. JSON report schema 3.0 includes core status, note status, warnings and rendered action objects. The user subsequently verified v3 Single, Full and both report languages through the real Qwen API.

## Step 05 read-only financial Agent

`agent_cli.py` loads engine reports through `agent_tools.py` and dispatches model requests through `agent.py`. The Qwen Agent provider shares the restricted SDK transport with the analysis adapter. The tool registry validates each function name and arguments before local execution. The loop replays each validated call and its result with the same call ID. The final model response selects evidence references. Python renders original engine values using that validated plan.

The financial engine and v3 analysis contract remain frozen. Tools accept a fixed business schema, operate on loaded evidence, and expose no mutation, filesystem traversal, shell or network target parameters. The Agent has no cross-question memory. The Step 05 Agent core is frozen. The final strict plan contains only answer status and reference IDs from successful calls in the current run. Python renders the required fields from each cited result and preserves null amounts. The user verified Summary, Hospital and Multi through Live Qwen, and all 187 offline tests passed. See the [Agent design](agent_design.md).

## Step 06 local RAG

The CLI adds an optional registry extension through `KnowledgeTool.search`. The tool lazily loads the simulated Markdown corpus through `KnowledgeIndex` and retrieves relevant sections with BM25. Missing or weak results produce a scoped lookup failure with no evidence reference. Financial references keep the `E` prefix and knowledge uses `K`. Both enter the existing enum of successful references and use the same `call_id`, limit and error handling. Python renders source excerpts and review guidance for knowledge citations and continues to render authoritative amounts from financial evidence. The Agent displays the same reference list in the instructions and schema. Step 06C also lists the exact English status codes in both, irrespective of display language. After Step 06C, the user verified all three Live Qwen RAG scenarios. All 207 offline tests passed, and the Step 06 architecture is frozen at Checkpoint 02. Retrieval and model behavior are validated for the synthetic MVP scenarios. BM25 can miss paraphrases, and an invalid model status or citation is rejected. OpenAI analysis remains offline-verified only. [RAG design](rag_design.md)

## Step 07 Streamlit application

The browser UI delegates to the same reconciliation, analysis, Agent and knowledge contracts. `ui/services.py` adapts session-owned bytes to a temporary operation directory. `app.py` and the views manage presentation, language, data invalidation and explicit request forms. The default sample run is local. A Qwen Live submission supplies masked, transient credentials and requires the user's authorization. Local evidence, financial amounts and review requirements retain their existing behavior. [Streamlit design](streamlit_design.md) · [Local guide](streamlit_guide.md)

The Anomaly Review view reads business priority and AI suggested priority from separate sources. In the user-run Live acceptance, four business-high findings received lower advisory priorities. Business priority, settlement state, financial amounts and review requirements retained their deterministic values. The final acceptance covers both browser Live workflows on synthetic inputs and freezes the Step 01–07 feature scope at Checkpoint 03. [Final acceptance and failure history](test_report.md#step-07-final-acceptance-and-checkpoint-03)
