# LLM Integration

## Run modes

The read-only analysis layer supports Mock, OpenAI and Alibaba Cloud Qwen. Mock uses deterministic selections and makes no network requests. The user locally verified Qwen v3 in Single, Full and both language report modes through the real API. See the [user-reported measurements](test_report.md#step-04-v3-user-reported-live-acceptance). OpenAI analysis remains offline-tested. The user verified all three Step 05 Agent scenarios through Live Qwen with the final reference-only contract. The Agent core is frozen after passing all 187 offline tests. See the [Agent design](agent_design.md).

```powershell
.\.venv\Scripts\python.exe -B main.py
.\.venv\Scripts\python.exe -B analyze.py --provider mock --language both
```

The analysis defaults to English and Mock when no provider is selected. Use `--language en`, `--language cn` or `--language both`. The input directory defaults to `outputs/` and must contain the three reports from one financial run. The output directory defaults to `outputs/`. Each selected language generates a JSON and Markdown file. Reports identify the provider, model, mode, UTC analysis time, source files and review requirements.

## Live configuration

Install the pinned dependencies with the project interpreter. Set process environment variables directly or through your deployment's secret mechanism. `.env.example` documents their names, and the application does not load local dotenv files automatically.

| Variable | Meaning |
| --- | --- |
| `LLM_PROVIDER` | `mock` by default. Set `openai` or `qwen`, or use the corresponding `--provider` option to opt in. The CLI takes precedence. A key alone does not enable Live mode. |
| `LLM_API_KEY` | OpenAI key. `OPENAI_API_KEY` is used if this value is empty. |
| `LLM_MODEL` | Required for OpenAI. Select a model available to your API project that supports Responses Structured Outputs. |
| `DASHSCOPE_API_KEY` | Alibaba Cloud Model Studio key. Qwen does not use OpenAI credentials. |
| `QWEN_BASE_URL` | Required for Qwen. Use the official HTTPS OpenAI-compatible base URL for the region or workspace that issued the key. Include `/compatible-mode/v1`. |
| `QWEN_MODEL` | Defaults to `qwen3.8-flash`. Availability and structured output support depend on the configured model and deployment. |
| `LLM_TIMEOUT` | SDK request timeout in seconds, greater than zero and at most 300. Default is 30. |
| `LLM_MAX_RETRIES` | SDK retries after the initial request, from 0 to 5. Default is 2. |

Run the following only when intentionally making a potentially billable Live request. The key entry is hidden in the terminal.

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
$env:LLM_MODEL = Read-Host 'Enter the model ID for your API project'
$env:LLM_API_KEY = [System.Net.NetworkCredential]::new('', (Read-Host 'API key' -AsSecureString)).Password
.\.venv\Scripts\python.exe -B analyze.py --provider openai --language en
Remove-Item Env:LLM_API_KEY
```

The OpenAI adapter calls `responses.create` with strict JSON Schema, `store=False` and a bounded output token budget. Both providers present sanitized errors and use the SDK retry policy during regular analysis. A failed Live run never becomes Mock automatically. Previously written reports may still be present after a failed run, so check the exit status and report timestamp. See the [Responses API reference](https://developers.openai.com/api/reference/resources/responses/methods/create), [Structured Outputs guide](https://developers.openai.com/api/docs/guides/structured-outputs) and [official Python SDK](https://github.com/openai/openai-python#handling-errors).

### Qwen connectivity check

Run this in an interactive PowerShell terminal at the project root only when authorizing a Live request. Enter the official region or workspace URL at the first prompt and the Alibaba Cloud key at the second. The prompts hide both values. The script keeps the key in process memory and writes no files.

```powershell
$env:QWEN_BASE_URL = [System.Net.NetworkCredential]::new('', (Read-Host 'Alibaba Cloud base URL ending in /compatible-mode/v1' -AsSecureString)).Password
$env:QWEN_MODEL = 'qwen3.8-flash'
.\.venv\Scripts\python.exe -B scripts\verify_qwen_live.py --live --prompt-key
```

The connectivity check sends one short synthetic prompt, with no retries and a 32-output-token cap. It prints the returned model, status, available token counts and elapsed time. If the key is already injected as `DASHSCOPE_API_KEY`, omit `--prompt-key` to use it. If hidden input is unavailable, the script exits.

The structured verification stages use the synthetic engine reports and each explicitly authorizes one request with zero retries. Run each stage separately after the preceding stage passes. The legacy `--structured` flag selects `--mode full`.

```powershell
.\.venv\Scripts\python.exe -B scripts\verify_qwen_live.py --live --prompt-key --mode single --input-dir outputs --language en
.\.venv\Scripts\python.exe -B scripts\verify_qwen_live.py --live --prompt-key --mode full --input-dir outputs --language en
.\.venv\Scripts\python.exe -B scripts\verify_qwen_live.py --live --prompt-key --mode report --input-dir outputs --output-dir outputs/qwen-verification --language en
```

`single` sends the first finding only. `full` validates all input findings, which is nine for the shipped sample, and discards the analysis. `report` validates the full input and saves JSON and Markdown in a separate verification directory. Structured verification reports scope, finding count, cause and action counts, core validation, omitted note warnings and whether it wrote reports. Each verification command sends one request with zero retries. `--mode connection` checks connectivity. Use `--language cn` for Simplified Chinese.

To publish Qwen analysis reports, set `DASHSCOPE_API_KEY` through the process environment or a secret manager and use the analysis command below. It uses the configured retry policy.

```powershell
.\.venv\Scripts\python.exe -B analyze.py --provider qwen --language en
```

### Qwen compatibility and request security

- Alibaba Cloud lists `qwen3.8-flash` for Responses and documents strict JSON Schema for the Qwen3.8 series. The adapter uses the SDK to send Alibaba Cloud's nested `text.format.json_schema` via `extra_body`. The application still validates the returned content against source evidence. Alibaba Cloud's Responses API supports a subset of OpenAI parameters. The adapter uses synchronous text only and sends `reasoning.effort=none` to disable thinking for this workload. For Qwen3.8, Alibaba Cloud documents a minimum of 16 for `max_output_tokens` and counts reply plus reasoning tokens against that limit. Responses marked incomplete are rejected. Alibaba Cloud documents a smaller effective input context for Responses than the underlying model window. [Create a response](https://help.aliyun.com/zh/model-studio/qwen-api-via-openai-responses) · [Responses compatibility](https://help.aliyun.com/zh/model-studio/compatibility-with-openai-responses-api) · [Structured output](https://help.aliyun.com/zh/model-studio/qwen-structured-output)
- The allowlist covers documented Model Studio shared, workspace and trial HTTPS hosts with the exact compatible API base path. Workspace and region must match the issued key. Redirects, environment proxies and inherited OpenAI headers are disabled for Qwen. Token Plan and Coding Plan endpoints are outside this adapter's scope. [Alibaba Cloud base URLs](https://help.aliyun.com/zh/model-studio/base-url)
- Requests set `store=false` to opt out of storing the generated response for later access. This setting does not establish zero server retention. Model Studio token usage is included when returned, and missing usage remains unknown. [Alibaba Cloud Responses reference](https://help.aliyun.com/zh/model-studio/qwen-api-via-openai-responses)

## Inputs, prompt and output

- `context_builder.py` reads only `summary.json`, `anomaly_details.csv` and `reconciliation_results.csv`. It checks that group keys, status, labels and finding counts agree. The model receives language, scope, anomaly IDs and types, settlement group identifiers and status, scoped record references, recognized duplicate resolution, and flags for amount availability. Raw rows, free-text source evidence, monetary values, unrelated files and expected test cases stay outside the model prompt.
- Source identifiers outside the safe format use scoped aliases or are withheld. All fields in the input JSON are untrusted data. The instruction template is passed separately. It requests a short management summary, finding explanations, tentative causes, manual checks and review priorities, and denies authority to change financial results or execute operations.
- The provider JSON schema contains `anomaly_findings`. Each item provides the exact anomaly ID and type, distinct evidence references, cause and action objects, priority and nullable `optional_analysis`. The renderer generates facts, bilingual descriptions, human-review flags, the executive summary and limitations. It reads authoritative amounts from the engine. Unknown amounts remain null and display as unknown.
- `output_validator.py` rejects malformed JSON, missing or duplicated findings, invalid selections and cross-finding or invented citations. It screens optional notes for numbers, unverifiable conclusions, unsafe markup and unauthorized actions. The checks are conservative and partial. Every report requires human review.

### Bilingual output validation

| Rule | Generation and enforcement |
| --- | --- |
| JSON and field types | The prompt requests a single plain JSON object. Schema requires exact keys and types. The local parser rejects malformed JSON, duplicate keys, non-finite constants and oversized responses. |
| Lists | Schema and local checks enforce one to eight objects for `possible_causes` and `recommended_actions`, with distinct codes within each list. |
| Hypotheses | The schema enumerates catalog codes. The local validator checks type applicability, scoped references and the minimum citations for each evidence role. The report renders the selected cause using an English or Simplified Chinese template. |
| Financial safety | The context sends amount availability flags. The report uses engine amounts, keeps unknown values null and omits aggregate figures for provisional runs. The prompt prohibits numeric claims, treating unknown amounts as zero, overdue statements, confirmed causes and external operations. Local checks reject recognizable examples. |
| Review and presentation | The schema limits priority to HIGH, MEDIUM or LOW. Catalog entries and authoritative report review flags require human review. The renderer labels causes and optional notes as unverified. Optional notes must be non-blank single-line plain text to appear. |

### Cause catalog

The earlier Live single-finding response was rejected by the tentative-sentence rule. Its text was unavailable. The new contract removes sentence parsing for causes and supplies eligible options alongside each finding. A cause citation must also be present in the finding's references. Codes express hypotheses for investigation only and do not establish a root cause.

| Code | Applicable finding types | Minimum cited evidence |
| --- | --- | --- |
| `REPORTING_DELAY` | `MISSING_PAYMENT` | A linked service record |
| `DATA_ENTRY_ERROR` | `INVALID_DATA` | An invalid source record |
| `INCORRECT_CONTRACT_PRICE` | `PRICE_MISMATCH` | The service and matched contract |
| `MISSING_CONTRACT_RECORD` | `MISSING_CONTRACT` | The affected service |
| `CONTRACT_VERSION_CONFLICT` | `CONTRACT_OVERLAP` | Two distinct candidate contracts |
| `DUPLICATE_IMPORT` | `DUPLICATE_PAYMENT` | A payment reference with an exact-copy resolution |
| `INCORRECT_SETTLEMENT_PERIOD` | `UNDERPAYMENT`, `OVERPAYMENT`, `UNMATCHED_PAYMENT` | A related payment |
| `PARTIAL_PAYMENT` | `UNDERPAYMENT` | A related payment |
| `PAYMENT_ALLOCATION_ERROR` | `UNDERPAYMENT`, `OVERPAYMENT`, `UNMATCHED_PAYMENT` | A related payment |
| `INSUFFICIENT_EVIDENCE` | All nine finding types | No minimum. Select this code alone. |

Reports retain codes and source references, with a localized description and `review_required: true` for each selection. The MVP catalogs constrain the hypotheses and checks the model can select. A reviewer may consider additional explanations when investigating.

### Manual review action catalog

| Code | Applicable finding types | Minimum cited evidence |
| --- | --- | --- |
| `CHECK_PAYMENT_REGISTER` | `MISSING_PAYMENT` | Related service record |
| `VERIFY_PAYMENT_RECORDS` | `UNDERPAYMENT`, `OVERPAYMENT`, `UNMATCHED_PAYMENT` | Related payment |
| `REVIEW_CONTRACT_EFFECTIVE_DATE` | `MISSING_CONTRACT` | Affected service |
| `COMPARE_CONTRACT_VERSIONS` | `CONTRACT_OVERLAP` | Two candidate contracts |
| `CHECK_DUPLICATE_IMPORT` | `DUPLICATE_PAYMENT` | Payment with an exact-copy resolution |
| `VERIFY_DUPLICATE_REFERENCE` | `DUPLICATE_PAYMENT` | Related payment |
| `CONFIRM_BILLING_QUANTITY` | `PRICE_MISMATCH` | Related service and matched contract |
| `REVIEW_SETTLEMENT_PERIOD` | `UNDERPAYMENT`, `OVERPAYMENT`, `UNMATCHED_PAYMENT` | Related payment |
| `VALIDATE_SOURCE_FIELDS` | `INVALID_DATA` | Invalid source record |
| `REQUEST_ADDITIONAL_EVIDENCE` | All nine finding types | No minimum |

The validator checks that a code is defined, applies to the finding, requires manual review and has the required evidence. All action citations must appear in that finding's evidence references. The catalog contains manual evidence checks only. Core failures are fatal.

### Report JSON 3.0 and optional notes

Consumers should check `report_schema_version`. The prior unversioned report already used cause objects. Version `3.0` also changes `recommended_actions` from strings to objects with `action_code`, `evidence_references`, `description` and `review_required`. `explanation`, `limitations`, `executive_summary` and `requires_human_review` remain present in the report and are generated by Python. The model no longer returns those fields.

On success, `core_validation` is `passed`. An absent or null optional note is `not_provided`. A safe note is `accepted` and remains advisory. A rejected note is recorded as `rejected` with a null value. JSON warnings and the verifier carry only the field path and rule. Markdown marks the omission. The report status becomes `completed_with_omissions`. The system supplies no replacement text. Input or response parsing errors, invalid required fields and invalid codes still stop the entire analysis. The note screen does not verify semantic truth.

## Failure and scope

Missing, unreadable or inconsistent source files stop the analysis before provider initialization. An engine report marked `INCOMPLETE_INPUT` permits review-only analysis and omits aggregate financial figures. The application can check the files it receives and cannot infer a later failed engine run from an older coherent set. Check the engine exit code before analysis and use a separate output directory for each run if retaining history.

The current CLI handles up to 40 findings and 75,000 serialized context characters in one request. Larger reports fail with a clear message. The prototype has no automatic batching or production data handling. Validation and API failures produce no new advisory report. The analysis CLI writes only the analysis files and leaves the financial reports and input data untouched.

The Step 04 run generated both language pairs in Mock mode and passed 31 new offline tests plus 28 reconciliation regression tests. No live request or model expenditure was part of this stage. See the [test report](test_report.md).
