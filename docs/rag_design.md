# Local business knowledge retrieval

Step 06 adds a read-only knowledge tool to the Agent. After Step 06C, the user's Live `qwen3.8-flash` retest passed English RAG, Chinese RAG and combined Q&A. All 207 offline tests passed. This MVP uses synthetic data and simulated guidance. OpenAI analysis remains offline-verified only. [Step 06 final acceptance](test_report.md#step-06-final-acceptance-and-checkpoint-02)

## Corpus and retrieval

The repository ships six simulated topics, each in English and Simplified Chinese under `knowledge_base/`. The 12 Markdown files provide 36 numbered sections indexed as 36 chunks. Each pair shares its document ID and section numbering and records a version, language, scope, and simulation status. Every section provides original prose and a distinct review guidance line. The documents cover reconciliation policy, contract pricing, payment handling, nine anomaly types, data quality, and human escalation. All guidance is for this synthetic demonstration.

1. `KnowledgeIndex.load()` reads local UTF-8 Markdown, validates the metadata and section boundaries, and builds an in-memory index when the knowledge tool is first used. A missing or invalid corpus does not prevent financial tools from running.
2. Normalize text with Unicode NFKC, case folding and whitespace normalization. Split English words and Chinese character bigrams. Map curated English and Chinese terminology and normalized anomaly codes to common topic tokens.
3. Rank sections in the requested language using BM25 with `k1=1.5` and `b=0.75`. Titles contribute twice to term frequency, and topic matches weigh more than ordinary tokens. A known topic must match a topical token in the section. For queries without a mapped topic, a section needs at least two matching tokens and half of the query's useful tokens. These heuristics suppress weak matches.
4. Rank by score, then document and section ID. Remove duplicate excerpts before the Top-K cutoff. Return the unchanged excerpt and review guidance with precise provenance. The score measures retrieval relevance and does not establish correctness or model confidence.

`KnowledgeRetriever.search()` is the adapter-facing interface for a future local embedding or hybrid retriever. The current implementation uses the Python standard library, has no external index, and calls no embedding service. English stop words and a curated synonym map cover common demo questions. More distant paraphrases, mixed-topic requests and unsupported languages may miss relevant evidence or surface marginal matches. The index does not interpret policy applicability or authenticate its content.

## Tool and evidence contract

`search_business_knowledge` is the sixth tool in the CLI registry. It accepts `query` (required, nonblank printable text up to 320 characters), `top_k` (integer from 1 to 5, default 3), and `language` (`en` or `cn`, defaulting to the CLI language). The model can select and refine this lookup within its existing request budget. The tool accepts no paths, document selectors, network addresses or operations to execute.

Successful financial evidence uses `E1`, `E2` and so on. Knowledge evidence uses `K1`, `K2` and so on. JSON results label each as `financial` or `knowledge`. Each knowledge hit includes its file, document ID and title, section ID and title, version, source language, scope, raw excerpt and source review guidance. A document ID is source metadata. The model cites the successful tool reference in the existing `{status, citations}` plan. The dynamic enum and the local validator reject unavailable or fabricated references. A lookup with no sufficiently relevant hits yields no citable result. A mixed answer may show a supported financial portion and explicitly state that relevant knowledge was unavailable.

The request instructions and schema use the same list of references from successful calls in this question. For example, three successful knowledge calls make `K1`, `K2` and `K3` available on the final turn. Each `K` reference represents one tool result, which may contain several `KB` document sections. Local validation requires an exact reference and rejects the entire answer if any citation is unavailable. `error_details.available_refs` shows the eligible server-assigned references without echoing the rejected value.

English and Simplified Chinese use the same protocol. The exact model status values are `answered`, `insufficient_evidence` and `refused`, subject to evidence availability. Localization applies to the rendered answer and preferred source language. An invalid status sets the application run status to `failed` and produces a redacted diagnostic at `$.status`.

Python renders each evidence section from its cited tool. Policy excerpts and guidance display the simulation scope and human review statement. Financial amounts continue to come from the existing engine reports. Document text is untrusted and remains data inside `function_call_output`. The closed registry grants read-only capabilities and the project never executes document instructions. Reviewers should check the cited text before using it. The model still selects evidence relevance for the question, and local checks guarantee provenance and shape rather than complete semantic relevance.

## Run locally

From the project root, use existing financial outputs from `main.py` and run these scripted demos. `knowledge` sends the question as the local search text. `combined` demonstrates a fixed synthetic hospital lookup followed by search using the anomaly returned by that lookup. The CLI labels these examples as Mock.

```powershell
.\.venv\Scripts\python.exe -B agent_cli.py 'How should a contract overlap be handled?' --mock-scenario knowledge --language en
.\.venv\Scripts\python.exe -B agent_cli.py '发现重复付款记录时应该如何处理？' --mock-scenario knowledge --language cn
.\.venv\Scripts\python.exe -B agent_cli.py 'Why is the May 2026 settlement for SIM-H004 on hold, and what should the finance team do next?' --mock-scenario combined --language en
```

The following commands reproduce the three Live acceptance scenarios. Each question begins a new run. The script prompts for the key without echoing it. Live uses the same per-question caps of five requests and eight tool executions, up to 1,024 output tokens per turn, and zero automatic retries. Inspect the `tool_trace`, evidence kinds and `answer_sections` returned by `--json`.

```powershell
$env:QWEN_BASE_URL = [System.Net.NetworkCredential]::new('', (Read-Host 'Alibaba Cloud base URL ending in /compatible-mode/v1' -AsSecureString)).Password
$env:QWEN_MODEL = 'qwen3.8-flash'
.\.venv\Scripts\python.exe -B agent_cli.py 'How should a contract overlap be handled?' --language en --provider qwen --live --prompt-key --input-dir outputs --json
.\.venv\Scripts\python.exe -B agent_cli.py '发现重复付款记录时应该如何处理？' --language cn --provider qwen --live --prompt-key --input-dir outputs --json
.\.venv\Scripts\python.exe -B agent_cli.py 'Why is the May 2026 settlement for SIM-H004 on hold, and what should the finance team do next?' --language en --provider qwen --live --prompt-key --input-dir outputs --json
```

Expect knowledge-only evidence in the first two scenarios and both financial and knowledge evidence in the third. For the third question, verify `CONTRACT_OVERLAP`, paid `10406.50` CNY, and null expected and difference amounts. Inspect the source sections and human review statement for all three questions.
