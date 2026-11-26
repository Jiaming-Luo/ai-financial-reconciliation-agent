# Read-only financial Agent

## Scope and request flow

Step 04 produces advisory reports from a predefined analysis context. The Step 05 Agent accepts one user question, lets Qwen select functions and follows the results within that question. The local application owns the tool registry, dispatch, evidence checks and final rendering. Mock uses explicit scripted scenarios to exercise the same protocol offline.

1. Load and validate the three engine reports. An optional v3 analysis JSON can supply separate AI priority suggestions after a financial snapshot and finding-evidence check.
2. Send the question, instructions and allowlisted Responses function definitions to Qwen with `tool_choice: auto`. The CLI exposes five financial tools and the Step 06 knowledge lookup. The nested `text.format.json_schema` format carries a strict Agent plan schema. Its allowed citation strings come from successful tool results in the current run. The model decides whether to request another tool or return the plan.
3. Receive `response.output` items with `type: function_call`. Validate each name, argument object and unique call ID before executing the batch.
4. Replay the original validated `function_call` and corresponding `function_call_output` consecutively with the same `call_id`. The output is serialized JSON with bounded, read-only evidence. Subsequent turns can use exact IDs from prior tool results. The client replays bounded history and sets `store=false`.
5. Validate the final JSON plan and render cited fields from the engine-owned tool evidence. Each citation includes its tool name, normalized arguments and source filenames.

Alibaba Cloud documents Function Calling, Responses text configuration and JSON Schema support for Qwen3.8 Flash. The SDK tests exercise multiple turns with both request settings. The user's final Live tests on `qwen3.8-flash` passed Summary (two requests, one tool call), Hospital (three requests, two tool calls), and Multi (three requests, two tool calls). The final offline suite passed all 187 tests. The Step 05 Agent core is frozen. [Alibaba Cloud Function Calling guide](https://help.aliyun.com/zh/model-studio/qwen-function-calling) · [Responses API reference](https://help.aliyun.com/zh/model-studio/qwen-api-via-openai-responses) · [Structured output guide](https://help.aliyun.com/zh/model-studio/qwen-structured-output)

## Tools and parameters

| Tool | Arguments | Evidence |
| --- | --- | --- |
| `get_reconciliation_summary` | An empty object | Portfolio totals, comparable differences, anomaly counts and held groups. |
| `list_anomalies` | Optional `hospital_id`, `settlement_period`, `anomaly_type`, `limit` | Exact-match filters, count, truncation and linked anomaly IDs. |
| `get_anomaly_details` | Required `anomaly_id` | Finding-level and group-level amount evidence, related record references and catalog-based manual review actions. |
| `get_hospital_reconciliation` | Required `hospital_id` and `settlement_period` | Scoped group amounts, settlement state and linked anomalies. |
| `get_review_priorities` | Same optional filters as `list_anomalies` | Rankings from the business rule and separately labeled AI suggestions, where supplied. |
| `search_business_knowledge` | Required `query`, optional `top_k` and `language` | Local simulated policy excerpts and review guidance with document and section IDs. |

The registry defines the JSON Schema and enforces it locally. Each object rejects extra keys. IDs have at most 80 characters and allow letters, digits, underscores, periods, colons and hyphens. Settlement periods use a valid `YYYY-MM`. Anomaly types are limited to the engine enum. Integer limits range from 1 to 10 and default to 5. A valid ID without a record yields a scoped lookup error. The assistant may refine that query. List results include the total matches and whether the displayed rows were truncated.

Step 05 ranks held groups and invalid data, contract conflicts, missing contracts and duplicate-payment controls as high business priority. Other anomalies are medium. The independent AI suggestion may be null. An optional report, for example with `--analysis-dir outputs/qwen-verification`, supplies suggestions with its recorded Mock or Live provenance. It cannot change the business sort order or financial amounts.

## Evidence and failure rules

The plan has two required properties, `status` and `citations`. An example is `{"status":"answered","citations":["E1"]}`. Before any successful tool call, the schema permits only `insufficient_evidence` and `refused` with an empty list. After successful calls, `answered` requires at least one distinct reference. The maximum is the number of successful results, up to eight. Python enforces citation uniqueness locally because the Qwen JSON Schema subset rejects `uniqueItems`. Each cited result supplies its curated fields, required amounts, review context and provenance. Model-generated field selectors are rejected. Python renders amounts as stored by the engine and preserves nulls. A group can have matched amounts and still carry anomalies. A missing payment record does not establish lateness. Provisional input is labeled and portfolio amounts are withheld. Cause and action recommendations require human review.

The adapter reads assistant `output_text` parts in order and ignores reasoning items. Local decoding rejects malformed JSON, duplicate keys, non-object roots and extra prose. `error_details` includes a safe code, stage, request number and, where appropriate, a JSON path, types or counts. An invalid string reference and an unsupported property use distinct codes. The verifier includes these details in the `not_answered` failure's `cause`. Raw model content and credentials are excluded.

The tool data excludes raw source narratives and expected test cases. Unsafe source identifiers use existing evidence aliases or are omitted. Tools take no paths, command strings, code or network destinations. The adapter sends traffic to the configured approved Alibaba Cloud endpoint. The system prompt requests refusal of settlement approval, payment, mutation and credential access. The static tool registry enforces the capability boundary, while question interpretation and relevance of the selected evidence still depend on the model.

Each question has a maximum of five model requests and eight tool executions. The last available request is reserved for the final plan. A repeated call ID or duplicate tool signature stops the run. Two consecutive turns without successful evidence also stop it. A tool result can contain up to 12,000 UTF-8 bytes and replay history up to 88,000 bytes. The question limit is 3,000 characters and each turn has a 1,024-output-token cap. The Agent uses a timeout of at most 60 seconds per SDK timeout setting and zero automatic retries to preserve the physical request budget. Usage totals reflect reported counters across all requests. Missing usage is shown as null. API failures stop the run in Live mode.

## Commands and acceptance

```powershell
.\.venv\Scripts\python.exe -B agent_cli.py 'Show totals' --mock-scenario summary
.\.venv\Scripts\python.exe -B agent_cli.py '列出价格差异并查看第一条明细' --mock-scenario multi --language cn
```

The demo output labels scripted Mock tool selection. Select Qwen explicitly for a real question.

```powershell
.\.venv\Scripts\python.exe -B agent_cli.py 'What are the held groups?' --provider qwen --live --prompt-key
```

For Live verification in the project root, use the approved Alibaba Cloud base URL and enter the credential at the hidden terminal prompt. Each command is a separate bounded question.

```powershell
$env:QWEN_BASE_URL = [System.Net.NetworkCredential]::new('', (Read-Host 'Alibaba Cloud base URL ending in /compatible-mode/v1' -AsSecureString)).Password
$env:QWEN_MODEL = 'qwen3.8-flash'
.\.venv\Scripts\python.exe -B scripts\verify_agent_live.py --live --prompt-key --scenario summary --input-dir outputs
.\.venv\Scripts\python.exe -B scripts\verify_agent_live.py --live --prompt-key --scenario hospital --input-dir outputs
.\.venv\Scripts\python.exe -B scripts\verify_agent_live.py --live --prompt-key --scenario multi --input-dir outputs
```

The verifier reports PASS when the expected evidence matches the scenario. Hospital requires a successful and cited lookup for `SIM-H004` in `2026-05`. Python includes the hospital, period, settlement status, review flag, currency, payment bucket, engine amounts, anomaly labels and linked anomalies with their count and truncation indicator. This applies only when the model cites the verified hospital result. Unknown amounts remain null and render as `Not determinable` in English and `暂无法确定` in Simplified Chinese. Additional valid tool calls, such as an anomaly detail lookup, are allowed. The multi-step check still requires a later model turn to look up the first ID returned by the anomaly list and cite both results.

Verification output includes the tool trace, safe parameters, engine evidence, usage and `verification_failures`. Each verification failure contains a code and message. Field-level diagnostics include the field names. This separates a scenario acceptance failure from an Agent execution `error`. Use `--language cn` to verify Simplified Chinese.

Step 05 supports Mock and Qwen for the Agent. OpenAI remains available for Step 04 analysis and has offline validation only. The current Agent handles one question and one snapshot with bilingual deterministic rendering. It does not persist review decisions, assess deadlines or execute financial operations. Step 06 adds local retrieval under distinct `K` references and uses the same evidence plan as financial `E` references. The instructions and schema both list the allowed references and exact English status codes for the current turn. After Step 06C, the user passed English, Chinese and combined Live acceptance with `qwen3.8-flash`. The synthetic MVP still rejects invalid model output. BM25 ranking depends on the indexed terms and curated aliases. The test report records all 207 offline passes and the scope of Live acceptance. Streamlit remains planned. [Step 05 final acceptance](test_report.md#step-05-final-acceptance) · [Step 06 RAG design](rag_design.md)
