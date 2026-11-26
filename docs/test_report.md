# Project Test Report

## Step 03 reconciliation

## Environment and executed commands

The verification used the project virtual environment with Python 3.13.7 and the standard-library unittest runner.

```powershell
.\.venv\Scripts\python.exe -B main.py
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -B -m pip check
```

The default CLI exited with code 0 and produced all three report files. The test suite passed **28 of 28 tests** with no failures, errors or skips. The dependency check reported no broken requirements.

| Suite | Passed | Coverage |
| --- | ---: | --- |
| Data loader | 8 | Type, enum and currency validation, exact cents, positive amounts, invalid dates, missing and malformed rows, and primary-key collisions. |
| Reconciliation | 8 | Contract boundary days, revised prices, pricing-key mismatches, pooled quantities, split and cross-month payments, held groups and unknown amount handling. |
| Anomaly detection | 7 | Exact duplicates, identical IDs, conflicts across hospitals and periods, amount/date/currency conflicts, mixed labels, variance direction and excluded invalid receipts. |
| Integration | 5 | Ten sample cases, real sample revision and totals, CLI independence from the expected file, provisional output on unassigned errors and fatal missing input. |

Twenty-five test methods use independent small input datasets or a missing-input directory. Three methods exercise shipped sample data. The ten expected outcomes are verified through subtests of one integration test. The CLI test compares all three report files byte for byte before and after deleting the expected-case file from a temporary copy of the sample directory. The shipped fixtures were preserved.

## Sample case results

| Case | Outcome | Observed evidence | Result |
| --- | --- | --- | --- |
| CASE-001 | MATCHED | SIM-H001 January totals are CNY 9,284.00 on both sides. SIM-P0002 is paid in February. | Pass |
| CASE-002 | MISSING_PAYMENT | SIM-H001 February has CNY 9,575.30 due and no receipt. | Pass |
| CASE-003 | UNDERPAYMENT | SIM-H002 February difference is CNY 15.00. | Pass |
| CASE-004 | OVERPAYMENT | SIM-H002 March difference is CNY -22.00. | Pass |
| CASE-005 | DUPLICATE_PAYMENT | SIM-P0016 repeats SIM-P0015. The CNY 11,895.80 receipt counts once. | Pass |
| CASE-006 | PRICE_MISMATCH | SIM-S0187 reports CNY 922.40 against CNY 918.40 calculated. The settlement balance is zero. | Pass |
| CASE-007 | MISSING_CONTRACT | SIM-S0299 has no active contract. Group receivable and difference are blank. | Pass |
| CASE-008 | CONTRACT_OVERLAP | SIM-S0273 falls under SIM-C0024 and SIM-C0032. Group receivable and difference are blank. | Pass |
| CASE-009 | UNMATCHED_PAYMENT | SIM-P0032 contributes CNY 875.00 to the unmatched bucket. | Pass |
| CASE-010 | INVALID_DATA | SIM-S0264 has quantity -1. Group receivable and difference are blank. | Pass |

## Observed balances and expected failure paths

The sample run had 31 groups, 22 without anomalies and nine flagged for review. Three groups were held. Twenty-seven comparable groups had CNY 287,468.40 in receivables, CNY 277,900.10 in eligible receipts and a net shortfall of CNY 9,568.30. Receipts of CNY 30,010.00 in held groups and CNY 875.00 in the unmatched group were tracked separately.

The tests also observed the intended failure behaviors. A missing file returned code 1 and named the source. Invalid month and hospital keys produced unassigned findings, provisional reports and code 2. Invalid or ambiguous pricing and unresolved payment references withheld affected balances without changing the corresponding source rows.

Verification used the project sample and local synthetic fixtures. Standalone audits of unused contract windows, production workloads and persisted review decisions are outside this test run.

## Step 04 analysis

The project virtual environment ran OpenAI SDK 2.54.0 and HTTPX 0.28.1. The financial CLI completed with 31 groups and nine findings. The bilingual Mock CLI wrote all four JSON and Markdown reports. The 28 Step 03 regression tests and 31 Step 04 tests passed.

```powershell
.\.venv\Scripts\python.exe -B main.py
.\.venv\Scripts\python.exe -B analyze.py --provider mock --language both
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -B -m pip check
```

| New suite | Passed | Coverage |
| --- | ---: | --- |
| LLM client | 9 | Offline default, missing SDK/key/model, bounded timeout and retries, strict Responses request, redacted authentication errors, transport failures, rate limiting, and refused or incomplete replies. |
| LLM analyzer | 11 | Bilingual files, nine existing findings, no findings, prompt-injection projection and Markdown escaping, held amounts, incomplete and invalid inputs, rejected reports, isolated provider failures, and Mock versus simulated Live metadata. |
| Output validator | 11 | JSON syntax and key uniqueness, missing and extra fields, exact anomaly ID and type, scoped evidence references, invented or zeroed amounts, definitive causes, overdue claims, operation instructions, and mandatory review. |

The SDK tests mock the HTTP transport to exercise the installed SDK and inspect request and response behavior. The rate-limit test observed three local attempts with two retries configured. The integration test compared the financial inputs byte for byte after a provider failure. No model request was sent to the real API, and no model API charges were incurred. Live API acceptance is **NOT VERIFIED**.

## Step 04B Qwen

The 59 existing tests and 19 new Qwen tests passed on the project interpreter using OpenAI SDK 2.54.0 and HTTPX 0.28.1. The two CLI help commands and `pip check` also passed.

```powershell
.\.venv\Scripts\python.exe -B -m unittest tests.test_qwen_provider
.\.venv\Scripts\python.exe -B -m unittest discover -s tests
.\.venv\Scripts\python.exe -B scripts\verify_qwen_live.py --help
.\.venv\Scripts\python.exe -B analyze.py --help
.\.venv\Scripts\python.exe -B -m pip check
```

| New suite | Passed | Coverage |
| --- | ---: | --- |
| Qwen provider | 12 | Allowed and rejected endpoints, isolated credentials and headers, no redirects or environment proxy, documented wire format, response metadata and token counts, sanitized errors, and separate retry policies. |
| Qwen analysis and verification | 7 | Live metadata through a simulated transport, shared output validation, financial file integrity on failure, explicit Live authorization, hidden input behavior, minimal console metadata and separate structured verification. |

The Qwen SDK connected only to local HTTP mock transports. The first-contact test observed a single request with a 32-output-token cap and no retries on rate limiting. The regular-analysis test observed three requests with two retries configured. Existing sample CSVs and the three financial reports retained their hashes. No real key was read, no real request was sent and no API charges were incurred. Offline acceptance is **PASS**. Live API acceptance is **NOT VERIFIED**.

## Step 04C.2 output compatibility

The reported Live response reached the local hypothesis check. That check formerly required an exact English or Chinese prefix. The actual response text was unavailable, so the report cannot distinguish a valid paraphrase from a non-tentative statement.

The 86 existing tests and 15 new compatibility tests passed. The new suite covers varied bilingual hypotheses, misleading hedge words, field-specific redacted diagnostics, prompt and schema consistency, all nine sample findings, and Mock plus both SDK transports. It also exercises the connectivity, single-finding, full and saved-report verification modes. Qwen and OpenAI requests in these tests used simulated HTTP transport. Live structured verification remains pending.

## Step 04C.2 structured hypothesis refactor

The next Live single-finding response again reached the local tentative-sentence check and failed there. Its text was unavailable. The refactor replaces cause prose with catalog selections and validated evidence. The program now renders the executive summary and cause descriptions.

```powershell
.\.venv\Scripts\python.exe -B -m unittest tests.test_hypothesis_catalog
.\.venv\Scripts\python.exe -B -m unittest discover -s tests
.\.venv\Scripts\python.exe -B -m pip check
```

All **115 tests passed**. The suite kept all 101 prior test slots, with 83 existing assertions retained and 18 cases adapted to the changed contract. The 14 new catalog tests cover eligible and ineligible codes, evidence ownership and role coverage, missing and duplicate selections, explicit insufficient evidence, reference aliases, multilingual templates, and financial report integrity. Existing offline transport tests exercise the actual OpenAI and Qwen SDK paths with the new schema. No Live API request was made in this stage.

### Existing test migrations

| Module | Test | Reason for adjustment |
| --- | --- | --- |
| `test_output_validator` | Missing or added fields | Restore a valid cause object before checking the unrelated extra field. |
| `test_output_validator` | Definitive cause, overdue and operations | Require the old causal sentence to fail the object contract. Retain the overdue and operation assertions. |
| `test_output_validator` | Provisional summary | Reject an injected model summary. The existing analyzer test still checks the program-rendered provisional summary. |
| `test_output_validator` | Eight entries without truncating | Check the eight-entry boundary on both remaining prose lists. Independent catalog tests reject repeated causes instead of padding a list. |
| `test_output_validator` | Invalid item index | Precede a malformed entry with a valid cause object and still require the second item's path. |
| `test_output_validator` | Prompt and schema bounds | Check string items for the prose lists, object items for causes, and the same cardinality bounds for both. |
| `test_llm_compatibility` | English hypothesis | Validate a selected code and the English catalog template instead of accepted English sentence forms. |
| `test_llm_compatibility` | Simplified Chinese hypothesis | Validate the same selected code and the Chinese catalog template. |
| `test_llm_compatibility` | Case and spacing | Check that case or whitespace cannot turn an invalid code into an accepted enum value. |
| `test_llm_compatibility` | Definitive causes in both languages | Reject old free-text causal assertions as invalid cause items. |
| `test_llm_compatibility` | Misleading hedge words | Reject a model-supplied description that attempts to override the catalog text, in both languages. |
| `test_llm_compatibility` | Prompt, schema and validator agreement | Check the enum, evidence terms, review boolean and explicit insufficient-evidence fallback. |
| `test_llm_compatibility` | OpenAI multi-finding transport | Send structured cause fixtures through the SDK while retaining the exact schema, nine IDs and report checks. |
| `test_llm_compatibility` | Single-finding verification | Return cause objects and check the number of validated causes. |
| `test_llm_compatibility` | Full verification | Return cause objects for all nine findings and check the cause count without writing reports. |
| `test_llm_compatibility` | Saved report verification | Use cause objects while retaining the unknown amount, net difference and localized report assertions. |
| `test_llm_compatibility` | Invalid saved report | Check the object-type diagnostic instead of the retired sentence rule. Retain checks for redacted output and no saved report. |
| `test_qwen_provider` | Invalid list diagnostic | Move the redaction sentinel to a remaining prose field so the intended list validation is reached. |

## Step 04C.2 final structured output

### User-reported Live history

| Observation | Outcome and response |
| --- | --- |
| Narrative list validation failed | The old schema omitted local length bounds. The prompt, schema and validator were aligned. The raw response was unavailable. |
| Cause sentence validation failed | A local tentative-language rule rejected the cause. The cause field changed to catalog codes and scoped citations. The raw response was unavailable. |
| Single succeeded under the cause-code contract | Qwen `qwen3.8-flash` returned `completed` for one finding and one cause. Usage was 950 input, 439 output and 1,389 total tokens. Elapsed time was 4.353 seconds and no report was written. |
| Full failed under the cause-code contract | The local `financial_numbers` screen matched the sixth finding's `explanation`. The triggering text was unavailable. The renderer now generates facts and the model uses catalog action codes. Supplementary prose has a separate omission path. |

### Offline result

All **128 tests passed**, including 101 prior cases with unchanged assertions, 14 adapted prior cases and 13 new tests. The new suite covers action applicability and citation requirements, all nine bilingual fact templates, financial amounts and unknowns, and the simulated sixth-finding regression in both Full and Report. The regression contains a synthetic numeric note and demonstrates that the core passes while the note is omitted. A separate test combines that note with an invalid core action and verifies that the entire run fails and writes no report. SDK transport tests remain offline. Qwen connectivity and the prior Single result are user-reported. Current v3 Live Single, Full and Report remain unverified.

```powershell
.\.venv\Scripts\python.exe -B -m unittest tests.test_structured_analysis_v3
.\.venv\Scripts\python.exe -B -m unittest discover -s tests
.\.venv\Scripts\python.exe -B -m pip check
```

| Adapted test | Reason |
| --- | --- |
| Validator valid shape | Check preserved type and evidence and that the model cannot set the review flag. Report tests check the deterministic review flag. |
| Validator invented amounts and zero | Exercise the same payloads in the note screen and verify their omission. |
| Validator definitive cause, overdue and operations | Retain the unsafe examples. The action list rejects prose and the note screen omits it. |
| Validator mandatory review | Reject a supplied false review flag as an unexpected field. |
| Validator empty arrays | Check both mandatory selection lists after retiring provider limitations. |
| Validator one-entry arrays | Keep the valid lower-bound assertion for causes and actions. |
| Validator eight-entry arrays | Check the shared structural upper bound independently of per-finding catalog applicability and duplication. |
| Validator oversized arrays | Retain the upper-bound rejection and exact path for both lists. |
| Validator wrong array types | Keep wrong-type and redaction checks for both core lists. |
| Validator prompt and bounds | Check catalog objects and a nullable note in the shared wire schema. |
| Compatibility prompt and schema | Check that the priority and cause enum remain and the model review flag is absent. |
| Compatibility text diagnostics | Preserve the five unsafe prose cases, now with safe note-omission reasons and paths. |
| Qwen structured verifier | Assert both catalog list bounds and the nullable note on the actual SDK transport. |
| Qwen invalid list diagnostic | Place the sentinel in the optional note. A malformed core action list still fails without leaking it. |

## Step 04 v3 user-reported Live acceptance

The user ran these checks locally in Windows PowerShell against the real Qwen API. The metrics below are user-reported. Each run used `qwen3.8-flash`, returned `completed` with `core_validation: passed` and `report_schema_version: 3.0`, and had zero omitted notes and no warnings. Both report runs returned `reports_written: true`.

| Scenario | Total tokens | Elapsed seconds | Findings | Cause codes | Manual review actions |
| --- | ---: | ---: | ---: | ---: | ---: |
| Single | 1199 | 4.359 | 1 | 1 | 1 |
| Full | 6354 | 21.836 | 9 | 13 | 13 |
| English Report | 6224 | 23.367 | 9 | 12 | 13 |
| Simplified Chinese Report | 5945 | 11.89 | 9 | 9 | 9 |

Qwen Live v3 analysis passed. OpenAI analysis remains offline-tested. Agent tool calling has a separate acceptance status.

## Step 05 Agent offline acceptance

The project environment passed all 128 existing tests and 36 new tests, for a total of **164**. The new tests cover 20 Agent and SDK transport cases, nine financial-tool projections and seven registry cases. The scenarios exercise a one-tool answer and a multi-turn list-to-detail lookup. Simulated Qwen HTTP responses verified the flat function definitions, call and output pairing, citation gating, limits, refusal, errors and zero retries. Both language modes ran locally. The sample CSVs and financial CSV/JSON reports retained their hashes.

```powershell
.\.venv\Scripts\python.exe -B -m unittest tests.test_agent tests.test_agent_tools tests.test_tool_registry
.\.venv\Scripts\python.exe -B -m unittest discover -s tests
.\.venv\Scripts\python.exe -B -m pip check
```

Offline acceptance was **PASS**. Live Agent tool calling had yet to be tested at this point. No real model request or API charge occurred during this stage.

## Step 05B Hospital scenario verification

The user ran the following Live scenarios locally in Windows PowerShell on `qwen3.8-flash`. The times and token counts are user-reported.

| Scenario | Verification | Model requests | Tool calls | Total tokens | Elapsed seconds |
| --- | --- | ---: | ---: | ---: | ---: |
| Summary | PASS | 2 | 1 | 3194 | 2.853 |
| Hospital | FAIL | 3 | 2 | 4914 | 5.865 |
| Multi | PASS | 3 | 2 | 4630 | 5.495 |

Hospital returned `status: answered` and `error: null`. The reported calls were `get_hospital_reconciliation` for `SIM-H004` in `2026-05` and `get_anomaly_details` for `ANOM-000006`. The first result had an eligible payment of CNY 10406.50 and null expected and difference amounts. The visible part of the answer omitted the hospital ID, settlement period, expected amount and difference amount. The previous verifier required Live mode and an answered result, plus a citation to the requested hospital lookup containing both `settlement_status` and `anomalies`. It allowed additional tool calls. The supplied excerpt leaves the presence of `anomalies` in the complete answer and the exact failed assertion unconfirmed.

The offline repair projects the complete settlement fields and linked anomaly evidence from an actual cited hospital result. Verification checks the exact scope, the citation, each required field and equality with source evidence, including nulls. `verification_failures` reports why acceptance failed even when the Agent answered successfully. Summary and Multi acceptance predicates retained their original requirements.

```powershell
.\.venv\Scripts\python.exe -B -m unittest tests.test_hospital_verification -v
.\.venv\Scripts\python.exe -B -m unittest discover -s tests
```

All **172 tests passed** in the project environment, including the **164 existing tests** and **8 new tests**. The new cases cover simulated Qwen multi-step lookups, omitted fields, bilingual unknown amounts and genuine zero, incorrect scopes, missing or mismatched fields, missing citations, incomplete tool evidence and safe verification diagnostics. SHA-256 checks matched all four sample CSVs and all three existing financial reports against their previous hashes.

Step 05B offline acceptance was **PASS**. The first Hospital Live run was **FAIL**. The later Live retest is recorded below. The offline repair used simulated transport and incurred no API charges.

## Step 05 Agent final response JSON reliability

The user reported these follow-up runs from Windows PowerShell using the real Qwen API in Live mode with `qwen3.8-flash`. They predate the JSON reliability fix.

| Scenario | Verification | Agent status | Model requests | Tool calls | Elapsed seconds |
| --- | --- | --- | ---: | ---: | ---: |
| Hospital | PASS | `answered` | 3 | 2 | Unreported |
| Summary | FAIL | `failed` | 2 | 1 | 3.466 |
| Multi | PASS | `answered` | 3 | 2 | Unreported |

Hospital and Multi returned `verification_failures: []`. Summary returned `not_answered` even though `get_reconciliation_summary` executed successfully and returned evidence `E1`. The full legacy message in the decoder was `Expected a valid JSON object with unique keys.` It covered malformed JSON, duplicate keys, nonstandard constants and decoder limit errors. The raw model output was unavailable, so the exact trigger remains unknown. A parsed top-level non-object, a provider-reported incomplete response and empty text each had a different legacy error path. The Hospital field projection occurs after this decoder and applies solely to hospital tool evidence.

Qwen requests now send the nested strict `text.format.json_schema` configuration used by Step 04 and specify the Agent citation plan schema. Each turn still sends `tools` with `tool_choice: auto`. The SDK transport tests verify that both options are serialized on the same request and that the tool output immediately follows the corresponding call with the same `call_id`. The plan is checked locally for JSON validity, unique keys, schema shape and citations to actual tool evidence. A failure produces static diagnostic codes, safe numeric locations or citation indexes where available, and an allowlisted reason for incomplete responses. The Agent keeps its five-request cap, eight-tool cap, 1,024-output-token limit and zero retries.

```powershell
.\.venv\Scripts\python.exe -B -m unittest tests.test_agent_json -v
.\.venv\Scripts\python.exe -B -m unittest discover -s tests
```

All **184 tests passed** in the project environment, including the **172 existing tests** and **12 new tests**. The new tests inspect actual SDK requests and exercise ordered text extraction, malformed or wrapped JSON, duplicate keys, invalid types, truncation, missing text, schema and evidence failures, HTTP rejection, and safe diagnostic output. Existing simulated SDK coverage confirms Hospital retains its required fields and null amounts and Multi still follows the list-to-detail protocol. SHA-256 hashes matched all four sample CSVs and all three existing financial reports.

Offline acceptance was **PASS**. The later Live runs are recorded below. No real model call was made during that fix, and no API charges were incurred.

## Step 05 Agent evidence citation reliability

The user ran these scenarios with the previous strict citation-object schema in Live mode on `qwen3.8-flash`.

| Scenario | User-reported verification | Result |
| --- | --- | --- |
| Summary | PASS | `answered`, two model requests, one tool call, no verification failures or error details. |
| Hospital | FAIL | `failed`, verifier `not_answered`. On model request 4, `final_answer` returned `schema_validation_failed` at `citation_index: 0` with `The citation has invalid field or reference types or length.` |
| Multi | Not run on that version | The earlier Live PASS predates the strict citation-object schema. |

The Hospital message identifies the type or length check. The raw model response was unavailable, so the offending property and value remain unknown. The previous API schema required `ref` and `fields`, described strings, rejected extra keys, and declared up to eight citations and one to eight fields per citation. Local validation also required successful references, field ownership, unique references and field names, status-dependent citation counts and complete hospital evidence. That difference matters for reliability independently of the unknown cause of the reported failure.

The new Agent plan carries `status` and a list of evidence-reference strings. The SDK emits a per-turn enum of successful references and the matching citation bounds. Python rejects duplicate or unavailable references, invalid types or counts, unexpected properties and incomplete required tool evidence. Each answer section draws its bounded field set from its own cited tool result, including null settlement amounts. Strict JSON and tool-selection boundaries still apply.

```powershell
.\.venv\Scripts\python.exe -B -m unittest tests.test_agent tests.test_agent_json tests.test_hospital_verification -v
.\.venv\Scripts\python.exe -B -m unittest discover -s tests
```

The targeted run passed all **43 tests**. The full suite passed all **187 tests**, including **184 previous cases** and **3 new cases**. Existing scripted plans and wire assertions were updated for string references. Tests continue to enforce unknown and duplicate reference rejection, unsupported field selection, verified amounts, exact hospital scope, evidence ownership, null versus zero, and the multi-turn `call_id` protocol. The new cases verify diagnostic paths and counts, omission of failed tool lookups from the enum, and rejection of old citation objects that try to select fields from a different result. SHA-256 hashes matched the four sample CSVs and three existing financial reports.

Offline acceptance was **PASS**. The subsequent Live results for the reference-only contract are recorded below. No real model request or API charge occurred during the offline fix.

## Step 05 final acceptance

The user ran the final reference-only Agent in Windows PowerShell and supplied screenshots of the real Qwen API results. The final runs used `provider: qwen`, `model: qwen3.8-flash` and `run_mode: Live`.

| Scenario | Verification | Model requests | Tool calls |
| --- | --- | ---: | ---: |
| Summary | PASS | 2 | 1 |
| Hospital | PASS | 3 | 2 |
| Multi | PASS | 3 | 2 |

Each run reported `verification_failures: []`, `status: answered`, `error: null`, `error_details: null`, `provisional: false` and `requires_human_review: true`. Token usage and elapsed times were unreported for these runs.

The accepted Agent plan contains `status` and a `citations` array of evidence reference strings. Each request limits these strings to successful tool references from the same run. Python renders the required fields from their cited results, preserves unknown amounts as null and enforces evidence ownership and human review. The Step 05 Agent core is frozen at this checkpoint. RAG and Streamlit remain planned.

The project virtual environment passed **187 of 187 tests**. `pip check` reported `No broken requirements found.` The four source fixture CSVs and the three existing financial outputs matched their previous SHA-256 values. The final checkpoint ran offline.

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s tests
.\.venv\Scripts\python.exe -B -m pip check
```

Final acceptance is **PASS** for both the offline regression suite and all three user-verified Live Qwen Agent scenarios.

## Step 06 RAG offline acceptance

The project virtual environment passed **202 of 202 tests**. The suite retained the **187 Step 05 cases** and added **15** knowledge tests. One existing Summary SDK test changed its fixed count of five tools to assert all five original names plus the new knowledge tool. Its existing financial values, reference schema and call pairing assertions continue to pass. `pip check` reported `No broken requirements found.`

```powershell
.\.venv\Scripts\python.exe -B -m unittest tests.test_knowledge_base tests.test_knowledge_agent -v
.\.venv\Scripts\python.exe -B -m unittest discover -s tests
.\.venv\Scripts\python.exe -B -m pip check
```

| Scenario | Offline outcome | Evidence |
| --- | --- | --- |
| A. English contract overlap | PASS | Mock CLI and simulated SDK returned `K1`. Default search returned `KB-06 §1`, `KB-02 §2` and `KB-04 §2`, including contract version review and escalation. |
| B. Chinese duplicate payment | PASS | Mock CLI returned `K1` in Simplified Chinese. The top passage was `KB-03 §2`, followed by `KB-04 §3` and `KB-06 §2`. |
| C. Combined financial and policy lookup | PASS | Mock CLI and simulated SDK used three model turns and two tools. Financial `E1` reported `SIM-H004`, `2026-05`, `REVIEW_REQUIRED`, `CONTRACT_OVERLAP` and CNY `10406.50` paid. Receivable and difference stayed null. The knowledge query used the anomaly label returned by `E1`, with `K1` citing contract and review guidance. |
| D. Financial regressions | PASS | Summary, Hospital and Multi passed their existing scenario predicates in simulated SDK runs with all six tools available. Financial references retained the `E` prefix. |
| E. Insufficient knowledge | PASS | An employee leave question returned no matching result, no reference and `insufficient_evidence`. |
| F. Safety boundaries | PASS | Invalid limits, language, paths and fake document references were rejected. A simulated injected document was supplied as tool data and could not authorize a payment tool. |

The 12 UTF-8 Markdown documents contain 36 numbered source sections indexed as 36 chunks. Tests verified matching document and section IDs in both languages, all nine anomaly codes, original excerpts, retrieval ordering, deduplication and scoped no-match behavior. The corpus and tools used synthetic inputs only. The four sample CSVs and three original financial outputs matched their SHA-256 baselines. The financial engine, five financial tools and Step 04 analysis code matched the Step 05 checkpoint.

Step 06 offline acceptance was **PASS**. The later user-reported Live results are recorded below. The offline stage used no real credential, model or embedding requests and incurred no API charges. [RAG design and verification commands](rag_design.md)

## Step 06B citation reliability regression

These are the user's local Live Qwen results from before the Step 06B change. Usage and timing were supplied for the combined scenario only.

| Scenario | Live result | Model requests | Tool calls | Evidence or error |
| --- | --- | ---: | ---: | --- |
| English RAG | FAIL | 4 | 3 | Final answer failed with `unknown_evidence_reference` at `$.citations[1]` on request 4. The validator reported three available references. |
| Chinese RAG | PASS | 4 | 3 | `answered` with `K1` and `KB-03 §2`, `KB-04 §3`, `KB-06 §2` and `KB-01 §3`. The guidance addressed duplicate payments. |
| Agent + RAG combined | PASS | 3 | 3 | `answered` with `E1` hospital reconciliation, `E2` anomaly details, and `K1` knowledge search citing `KB-06 §1` and `KB-01 §2`. |

The combined run took **4.901 seconds** and reported **6,466 input tokens**, **192 output tokens**, and **6,658 total tokens**. It identified `CONTRACT_OVERLAP` for `SIM-H004` in `2026-05` with `REVIEW_REQUIRED`, paid CNY `10406.50`, and null expected and difference amounts. Related records were `SIM-S0273`, `SIM-C0024`, and `SIM-C0032`.

The English run reached final citation validation and the second citation failed membership in the local evidence set. The raw model response was unavailable, so the rejected value and exact trigger are unknown. Code review and simulated transport tests found no reset, overwrite, or omission when accumulating three successful knowledge results. The existing request schema already used the current local evidence keys. The prior instructions used a fixed `E1` example even for a knowledge-only turn. The instructions now show the same per-turn reference list as the strict schema, explain that a top-level `K` reference covers its returned passages, and keep document and section IDs as source metadata. Errors now report the server-assigned `available_refs` alongside the count. Invalid citations still reject the full answer, and the invalid model value is excluded from diagnostics.

```powershell
.\.venv\Scripts\python.exe -B -m unittest tests.test_knowledge_agent tests.test_hospital_verification tests.test_agent_json -v
.\.venv\Scripts\python.exe -B -m unittest discover -s tests
.\.venv\Scripts\python.exe -B -m pip check
```

The targeted suite passed **35 tests**. The complete suite passed **205 tests**, including the 202 existing cases and three new cases for sequential knowledge references, invalid second citations, and financial detail and knowledge returned in the same turn. The wire tests verify that the tool history, prompt list and dynamic schema agree on every request. Chinese knowledge, combined and pure financial regressions passed offline. `pip check` reported `No broken requirements found.` The four sample CSVs and three financial reports matched their SHA-256 baselines. The financial engine and Step 04 analysis files matched the Step 05 checkpoint.

Step 06B offline acceptance was **PASS**. The subsequent user-run Live results are recorded below. This offline stage made no real API requests and incurred no charges. [PowerShell retest commands](rag_design.md#run-locally)

## Step 06C language-independent final answer status

The user ran these Live Qwen scenarios with the Step 06B instructions before the Step 06C change.

| Scenario | Live result | Model requests | Tool calls | Evidence or error |
| --- | --- | ---: | ---: | --- |
| English RAG | PASS | 2 | 1 | `answered`, `error: null`. |
| Chinese RAG | FAIL twice | 2 at failure | Unreported | Both runs failed at `$.status` with `schema_validation_failed` and `The answer status is not allowed.` |
| Agent + RAG combined | PASS | 3 | 3 | `answered`, `error: null`. |

The legacy error identifies an out-of-enum status string in the parsed model plan. `failed` in the CLI output is the application's run status after rejection. The raw model value was unavailable. Translation, casing, extra whitespace and other unexpected values remain unconfirmed. Before the change, simulated HTTP captured identical English and Chinese second-turn request formats for `K1`, including `json_schema`, `strict: true`, and the same three English status strings.

Step 06C makes the prompt explicitly require exact English status values and preserves all protocol fields, identifiers and enum values across languages. The prompt lists the same per-turn statuses as the strict schema. There are two allowed statuses before evidence and three with evidence. An `answered` plan still needs valid citations. Status diagnostics report the field path, presence, expected and actual types, category, allowed values and string length where applicable. Raw rejected values are excluded. Invalid status and invalid citations still fail the run.

```powershell
.\.venv\Scripts\python.exe -B -m unittest tests.test_knowledge_agent tests.test_hospital_verification tests.test_agent_json
.\.venv\Scripts\python.exe -B -m unittest discover -s tests
.\.venv\Scripts\python.exe -B -m pip check
```

The targeted run passed **37 tests**. The full suite passed **207 tests**, retaining all 205 previous cases and adding two tests with bilingual SDK wire checks and malformed-status subcases. The regressions covered English and Chinese knowledge queries, the combined query, Summary, Hospital, Multi and invalid citation rejection. `pip check` reported `No broken requirements found.` The four sample CSVs and three financial reports matched their SHA-256 baselines.

Offline acceptance was **PASS**. The subsequent user-run Live results are recorded below. This offline stage made no real API requests and incurred no charges. [PowerShell retest commands](rag_design.md#run-locally)

## Step 06 final acceptance and Checkpoint 02

The user ran the three acceptance scenarios in Windows PowerShell after the Step 06C fix. All runs used Qwen `qwen3.8-flash` in `Live` mode. All returned `status: answered`, `error: null` and `error_details: null`, and retained the human review requirement. The metrics and outcomes are user-reported.

| Scenario | Result | Model requests | Tool calls | Input tokens | Output tokens | Total tokens | Elapsed seconds | Answer references |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| English RAG | PASS | 2 | 1 | 3,898 | 64 | 3,962 | 3.495 | `K1` |
| Chinese RAG | PASS | 2 | 1 | 4,044 | 72 | 4,116 | 3.395 | `K1` |
| Agent + RAG Combined | PASS | 4 | 4 | 9,263 | 230 | 9,493 | 7.575 | `E1`, `E3`, `K1` |

- English RAG cited `KB-06 §1`, `KB-02 §2` and `KB-04 §2` through `K1`.
- Chinese RAG cited `KB-03 §2`, `KB-04 §3`, `KB-06 §2` and `KB-01 §3` through `K1`. The preceding Chinese status enum failure did not recur in this retest.
- The combined run used `get_hospital_reconciliation`, `list_anomalies`, `get_anomaly_details` and `search_business_knowledge`. For `SIM-H004` in `2026-05`, it returned `REVIEW_REQUIRED`, payment bucket `HELD`, and anomaly `CONTRACT_OVERLAP`. Paid was CNY `10406.50`. Expected and difference amounts remained null. Candidate contracts were `SIM-C0024` and `SIM-C0032`. The cited knowledge sections were `KB-02 §2`, `KB-06 §1` and `KB-04 §2`.

The project virtual environment passed all **207** offline tests. `pip check` reported `No broken requirements found.` The four sample CSV files and three local financial outputs matched their SHA-256 baselines. The checkpoint work ran without real API calls or costs.

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s tests
.\.venv\Scripts\python.exe -B -m pip check
```

Step 06 final acceptance is **PASS** for these three Live Qwen scenarios and the offline suite. OpenAI analysis remains offline-verified only. Acceptance applies to an MVP using synthetic records and simulated guidance. BM25 can miss relevant passages when wording differs from the indexed terms. Live model output may still violate the response contract. Invalid statuses or citations cause rejection and require human review. Steps 03 through 06 are frozen at Checkpoint 02.

## Step 07 Streamlit offline acceptance

The Windows project virtual environment passed **217 of 217 tests** using Streamlit 1.66.0. All 207 prior cases were retained. Ten new cases use the local service layer and Streamlit AppTest. `pip check` reported `No broken requirements found.`

| Check | Result |
| --- | --- |
| Navigation, language and defaults | All five views loaded. Language switching changed display labels under Mock without a provider call. |
| Local finance and uploads | Sample summary matched the baseline engine report. Separate upload content produced a changed payment count. Invalid headers, filenames, oversized files and formula-prefixed identifiers were rejected. Switching input removed old results and uploads were isolated across sessions. |
| Amounts and anomalies | The held group's paid amount remained `10406.50`, and unknown expected and difference values received the localized label. The view showed the linked contract evidence and validated v3.0 Mock analysis. |
| Assistant and knowledge | The Mock combined run returned financial `E1` and knowledge `K1`. Local search returned ranked original sections and reported insufficient evidence on a missing topic. |
| Explicit Live submissions | Simulated SDK HTTP accepted a valid v3.0 analysis and produced a two-request Agent answer after explicit submission. Navigation, language switching and reruns produced no further requests. A simulated authentication failure left deterministic financial results available, and insufficient evidence rendered an explicit status. |
| Isolation and integrity | Live test credentials and the private endpoint were absent from the app's state after the form was cleared. Provisional artifacts could not be sent for AI analysis. Four sample CSVs and three local financial outputs retained their SHA-256 hashes. Frozen Step 03–06 code matched Checkpoint 02. |

The Streamlit process bound to `127.0.0.1:8501`, and `/_stcore/health` returned HTTP 200. A real local browser rendered the dashboard and completed a Mock assistant query. The language selector switched to Simplified Chinese, and the knowledge search for `重复付款` displayed the original passage and review guidance from `KB-03 §2`. This was a local visual smoke check. The full page regression used AppTest.

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s tests
.\.venv\Scripts\python.exe -B -m pip check
.\.venv\Scripts\python.exe -B -m streamlit run app.py --server.address=127.0.0.1 --server.port=8501
```

Offline acceptance at this checkpoint was **PASS**. Browser Live calls had yet to be verified. This offline run made no real model or other paid API calls. [Local usage guide](streamlit_guide.md)

## Step 07E–07F analysis diagnostics and display regression

The user reported browser acceptance of all five pages, both interface languages, the repository sample run and summary download, Mock anomaly analysis and the combined Mock assistant query. The user also ran the following Qwen Live browser scenarios before this fix.

| Browser scenario | Result | Observations |
| --- | --- | --- |
| AI Assistant combined Agent + RAG | PASS | `qwen3.8-flash`, 4 model requests, 3 tool calls, 8,924 total tokens and 6.321 seconds. The answer referenced `E1`, `E2` and `K1` and retained human review. For `SIM-H004` in `2026-05`, the result was `REVIEW_REQUIRED`, payment bucket `HELD`, paid CNY `10406.50`, and unknown expected and difference amounts. The Base URL, API key and consent controls cleared on submission. |
| Anomaly Review AI analysis | FAIL | The page displayed a generic failure after submission. The terminal showed no failure details. Nine anomaly types, deterministic priorities, amounts and evidence remained available. The AI priority was undetermined. The transport status, response and validation details of this run are unknown. |

The analysis page and CLI both use the Step 04 v3.0 context builder, analyzer, Qwen adapter and local output validator. Simulated HTTP confirmed identical request bodies when the model, report inputs and language agree, including the strict `anomaly_analysis` schema. The Streamlit form supplies per-request configuration and uses zero retries. The confirmed defect was that the UI mapped every handled analysis exception to the same message, with no diagnostic fields. The separate Assistant function-calling path was unaffected.

The Analysis result panel now offers an expandable diagnostic with an allowlisted code, stage and applicable metadata. Authentication errors can show the HTTP status. Validation errors can show the field path, expected and actual type, and a static enum when relevant. Request counts are included when their values can be established. Provider errors, invalid JSON, duplicate keys, schema rejection and evidence rejection remain fail-closed. Diagnostics never render a raw exception, model value, credential, private endpoint, request body or response body. A failed submission clears the previous analysis and any assistant result that could have used it, while deterministic results remain available.

| Offline check | Result |
| --- | --- |
| Focused Streamlit, Qwen and validator tests | **52 passed**. Simulated HTTP covered Live success, authentication failure, invalid JSON, schema and evidence rejection, CLI request parity, and redaction. Further navigation, filtering and ordinary reruns made no additional model requests. |
| Complete regression | **221 passed**, including all 217 prior tests and 4 new tests. `pip check` reported `No broken requirements found.` |
| Local browser display | The loopback smoke server returned HTTP 200. English and Chinese Dashboard showed the full comparable receivable `CNY 287,468.40`, comparable paid `CNY 277,900.10` and held payments `CNY 30,010.00`. Chinese plots displayed all nine anomaly labels and the settlement statuses. The Anomaly Review displayed complete related IDs and the grouped evidence disclosure. AppTest also checked the chart tooltip enums and the Mock request-count label. |
| Data and safety | All four sample CSV and three baseline financial output SHA-256 hashes matched. No real API key was read and no model or paid API was called during this work. The finance engine, v3.0 schema and analyzer, Agent core and BM25 retrieval remained at the baseline. |

```powershell
.\.venv\Scripts\python.exe -B -m unittest tests.test_streamlit_app tests.test_qwen_provider tests.test_output_validator
.\.venv\Scripts\python.exe -B -m unittest discover -s tests
.\.venv\Scripts\python.exe -B -m pip check
```

Step 07E–07F offline acceptance was **PASS**. Browser Live Agent + RAG remained **PASS** for the user-reported scenario. The separate Live anomaly analysis retest is recorded below. [Live retest steps](streamlit_guide.md)

## Step 07G Qwen Live analysis contract review

The user restarted Streamlit with the Step 07E–07F build and submitted **Run AI analysis** in **Anomaly Review**, using English, repository samples and `qwen3.8-flash` in Qwen Live mode. The application reported one model request and rejected the output during local validation with `schema_validation_failed` at `anomaly_findings[0].possible_causes[1].cause_code`. The message was “The response did not match the analysis output schema.” The UI indicated that the financial results remained available. This is a user-reported Live failure on the earlier build. It is separate from the successful Assistant Agent + RAG scenario.

The observed code and path could come from a non-string or unlisted value, a duplicate selection or a mixed `INSUFFICIENT_EVIDENCE` fallback. The previous validator used the same error category for all four and the UI exposed only the priority enum. The raw model response was unavailable. The rejected value and exact triggering rule remain unknown.

Step 07G keeps the strict v3.0 request schema and the existing accepted report shapes. The prompt lists schema-derived required fields and priorities and tells the model to copy exact per-finding option keys and evidence references in both languages. One supported cause and one supported review action are sufficient. Local diagnostics distinguish schema type or enum violations from selection and evidence rules. The UI exposes the field path, constraint, safe type names, static enum choices, string length and request count where applicable. It excludes the raw value, evidence identifiers, credentials and private endpoints. Invalid core analysis still rejects the full report. The financial snapshot, business priorities and evidence remain available, and stale analysis is cleared. [Constraint matrix](streamlit_design.md#v30-analysis-output-checks)

| Offline check | Result |
| --- | --- |
| Targeted regression | **85 passed.** Valid and invalid cause codes, null and wrong types, legal and illegal second selections, action and priority enums, evidence scoping, required fields and unchanged strict Qwen wire schema were verified. |
| Streamlit and CLI | Simulated HTTP verified CLI and Streamlit request parity and matching English and Chinese machine fields. AppTest reproduced the reported path with a test code, confirmed full rejection and stale-report cleanup, and checked that the diagnostic, form state and financial artifacts remained safe. |
| Full regression | **227 passed**, retaining all 221 existing cases and adding 6. `pip check` reported `No broken requirements found.` |
| Data and safety | All four sample CSVs and three baseline financial outputs retained their SHA-256 hashes. The finance engine, Agent core and BM25 retrieval were unchanged. No real key was read and no real API request or charge occurred. |

```powershell
.\.venv\Scripts\python.exe -B -m unittest tests.test_output_validator tests.test_hypothesis_catalog tests.test_structured_analysis_v3 tests.test_qwen_provider tests.test_streamlit_app
.\.venv\Scripts\python.exe -B -m unittest discover -s tests
.\.venv\Scripts\python.exe -B -m pip check
```

Step 07G offline acceptance was **PASS**. The subsequent browser Live anomaly analysis retest is recorded below. [Local usage guide](streamlit_guide.md)

## Step 07 final acceptance and Checkpoint 03

The following browser results come from the user's local Windows acceptance on the repository's synthetic data and simulated business guidance.

| Page | Result | User-verified coverage |
| --- | --- | --- |
| Dashboard | PASS | Financial metrics, anomaly and settlement-status distributions, and filters. |
| Reconciliation | PASS | Sample run, results, status filtering and download controls. The user downloaded `summary.json`. |
| Anomaly Review | PASS | Nine anomaly types, filters, amount separation, original evidence, manual review guidance and the Live retest below. |
| AI Assistant | PASS | Mock and Qwen Live combined financial and knowledge queries. |
| Knowledge Base | PASS | English and Simplified Chinese document browsing and local BM25 search. |

The user also verified switching between English and Simplified Chinese and the display of the main business fields.

### User-run Qwen Live acceptance

The **Agent + RAG** browser query passed with `qwen3.8-flash`. The user reported **4 model requests, 3 tool calls, 8,924 total tokens and 6.321 seconds**. The answer showed financial evidence `E1` and `E2`, and knowledge evidence `K1`. For `SIM-H004` in `2026-05`, it showed `CONTRACT_OVERLAP`, settlement status `REVIEW_REQUIRED`, payment bucket `HELD` and paid CNY `10406.50`. Receivable and difference remained unknown. Human review remained required.

The separate **Anomaly Review** browser retest passed after Step 07G. It displayed `Completed`, mode `Live`, model `qwen3.8-flash` and JSON and Markdown download controls. Token usage and timing were not supplied for this run. The generic failure and the later cause-code rejection remain recorded in the preceding Step 07E–07G sections.

| Finding | Business priority | AI suggested priority |
| --- | --- | --- |
| `ANOM-000001` | Medium | High |
| `ANOM-000002` | Medium | Medium |
| `ANOM-000003` | Medium | Medium |
| `ANOM-000004` | High | Low |
| `ANOM-000005` | Medium | Medium |
| `ANOM-000006` | High | Medium |
| `ANOM-000007` | High | Low |
| `ANOM-000008` | High | Medium |
| `ANOM-000009` | Medium | Medium |

Four business-high anomalies received lower AI suggested priorities. All nine findings still required human review. The report left business priorities, financial amounts, settlement states and review flags intact. This run verifies the separation of deterministic results and AI advice in the interface. It provides no estimate of overall model accuracy or stability.

The user's screenshots confirmed that the approved Qwen HTTPS Base URL and DashScope key fields cleared after submission and the Live authorization checkbox reset. The non-sensitive model name remained visible. Code review confirmed masked short-lived form input, a fresh form identity after submission, allowlisted diagnostic metadata, and suppression of request logs from the configured SDK and HTTP loggers. No credentials or screenshots were used as test inputs or stored in the acceptance record.

### Final offline and integrity checks

- **227 tests passed** in the Windows project virtual environment. AppTest and simulated HTTP cover submit-only model calls, navigation and filter reruns, stale report cleanup, evidence validation, financial result isolation, review flags and credential cleanup. Simulated responses are separate from the user-run Live results.
- `pip check` reported `No broken requirements found.`
- All four sample CSV and three baseline financial output SHA-256 hashes matched. The deterministic finance engine, v3.0 output schema, Agent core and BM25 retrieval remained at the Checkpoint 02 baseline. The Step 07 changes add local UI integration and preserve those contracts.

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s tests
.\.venv\Scripts\python.exe -B -m pip check
```

Step 07 final acceptance is **PASS** for the local MVP. Checkpoint 03 freezes the Step 01–07 feature scope. Real model output can still fail validation, and BM25 may miss differently worded questions. Human review remains mandatory. Production validation remains pending. This checkpoint work did not read a real API key or call a real model.

## Step 08B screenshot delivery and final acceptance

The published gallery contains nine screenshots from the offline Mock walkthrough and three English screenshots from two real Qwen Live runs performed by the user in the local browser. All runs used the repository's synthetic data. This delivery review made no model calls. The earlier [Step 07 Live acceptance](#user-run-qwen-live-acceptance) remains a separate record.

| Step 08B Live scenario | Reviewed evidence |
| --- | --- |
| Agent + RAG combined query | `qwen3.8-flash` in Live mode, `Answered · evidence references validated`, 3 model requests, 3 tool calls, 7,200 total tokens and 5.148 seconds. `E1` shows `SIM-H004` in `2026-05` with `CONTRACT_OVERLAP`, `REVIEW_REQUIRED` and payment classification `HELD`. Paid is CNY 10406.50. Receivable and difference remain unknown, and human review is required. [Assistant result](assets/screenshots/08-assistant-combined-en-live.png) |
| Knowledge evidence from the same query | `K1` shows KB-06 §1, KB-01 §2 and KB-06 §2, with simulated source documents, original excerpts and human review guidance. [Knowledge evidence](assets/screenshots/08b-assistant-evidence-en-live.png) |
| Anomaly analysis | The UI shows `Completed`, Live mode and `qwen3.8-flash`. The separate priority columns differ on five rows. All nine findings show that review is required. [Anomaly analysis](assets/screenshots/09-anomaly-priority-en-live.png) |

| Finding with a priority difference | Business priority | AI suggested priority |
| --- | --- | --- |
| `ANOM-000001` | Medium | High |
| `ANOM-000005` | Medium | Low |
| `ANOM-000006` | High | Medium |
| `ANOM-000007` | High | Low |
| `ANOM-000008` | High | Medium |

The other four displayed rows have matching priorities. The suggestions are advisory and the business priorities and review requirements remain separate. The observed latency and suggestions describe these particular runs.

Final delivery verification passed. All 12 published PNGs decoded successfully, had distinct hashes and matched their originals byte for byte. The three new Live images were visually checked for readable evidence and the absence of visible credentials, private endpoints and personal information. The PNG files have no ancillary metadata or trailing data. The full offline suite passed **227 tests**, `pip check` reported no broken requirements, and all four sample CSV plus three baseline financial output SHA-256 hashes matched. Core code, dependencies and entry points match Checkpoint 03. [Screenshot guide and publication review](demo_capture_plan.md)
