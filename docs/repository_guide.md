# Repository guide

The Step 01–07 feature scope is frozen at Checkpoint 03. This map groups paired policy translations and test modules for readability.

```text
ai-financial-reconciliation-agent/
├── app.py                            # Start the local Streamlit app
├── main.py                           # Reconcile the three source CSVs
├── analyze.py                        # Generate v3.0 advisory reports
├── agent_cli.py                      # Ask one read-only question
├── README.md / README_CN.md          # English and Simplified Chinese project guides
├── AGENTS.md                         # Project development conventions
├── requirements.txt                  # Pinned direct Python dependencies
├── .env.example                      # Placeholder-only provider settings
├── .gitignore                        # Local outputs, secrets and caches
├── .streamlit/config.toml             # Loopback binding, upload limit and theme
├── data/sample/
│   ├── contracts.csv
│   ├── service_records.csv
│   ├── payments.csv
│   └── expected_anomalies.csv         # Test expectations, excluded from engine input
├── src/
│   ├── __init__.py
│   ├── data_loader.py                # Load and validate source records
│   ├── reconciliation.py             # Match contracts, price services and reconcile groups
│   ├── anomaly_detector.py           # Classify findings and resolve payment references
│   ├── reporting.py                  # Write settlement and anomaly CSVs and summary JSON
│   ├── context_builder.py            # Project scoped engine evidence
│   ├── llm_analyzer.py               # Validate and render advisory analysis
│   ├── llm_client.py / qwen_provider.py
│   ├── prompts.py / output_validator.py
│   ├── hypothesis_catalog.py / action_catalog.py
│   ├── agent.py / agent_prompts.py
│   ├── agent_tools.py / tool_registry.py
│   └── knowledge_base.py / knowledge_tool.py
├── knowledge_base/
│   ├── 01-policy.en.md / 01-policy.cn.md
│   ├── 02-contract-pricing.en.md / 02-contract-pricing.cn.md
│   ├── 03-payment-sop.en.md / 03-payment-sop.cn.md
│   ├── 04-anomalies.en.md / 04-anomalies.cn.md
│   ├── 05-data-quality.en.md / 05-data-quality.cn.md
│   └── 06-human-review.en.md / 06-human-review.cn.md
├── ui/
│   ├── __init__.py
│   ├── pages.py / services.py       # Views and isolated service calls
│   └── session.py / text.py / diagnostics.py
├── tests/
│   ├── __init__.py
│   ├── fixtures.py                  # Synthetic input and workspace helpers
│   └── test_*.py                    # Finance, LLM, Agent, RAG and Streamlit tests
├── scripts/
│   ├── generate_sample_data.py       # Regenerate the four deterministic fixtures
│   ├── verify_qwen_live.py            # Explicit provider and analysis verification
│   └── verify_agent_live.py           # Explicit Agent scenario verification
├── docs/
│   ├── PRD.md / PRD_CN.md / data_dictionary.md
│   ├── architecture.md / llm_integration.md / agent_design.md / rag_design.md
│   ├── streamlit_design.md / streamlit_guide.md
│   └── test_report.md / repository_guide.md / demo_capture_plan.md
└── outputs/                          # Generated locally and ignored by Git
```

### Module boundaries

| Component | Reads | Produces |
| --- | --- | --- |
| Finance engine | Contracts, service records and payments | Deterministic settlement and anomaly CSVs and the summary JSON |
| Advisory analysis | Scoped evidence projected from the engine reports | Version 3.0 JSON and Markdown with cause codes, review actions, suggested priorities and human-review notices |
| Financial tools | Financial reports and optional matching v3.0 priorities | Read-only evidence for reconciliation totals, anomaly list and detail, hospital settlement and review priorities |
| Knowledge tool | Twelve simulated policy files containing 36 indexed sections | Excerpts and document-section references using local bilingual BM25 |
| Agent | A single question, tool definitions and results from the current run | A validated status and reference selection rendered by Python. Financial evidence uses `E` and knowledge evidence uses `K`. |
| Streamlit | A session-owned financial snapshot and optional validated AI output | Five bilingual views, filters, evidence, redacted error diagnostics and downloads. Isolated operation directories preserve existing CLI reports. |
| Tests | Synthetic fixtures and simulated model transport | Offline assertions for pricing, payments, schemas, evidence, failure isolation and UI behavior |

### Six Agent tools

| Tool | Source and purpose |
| --- | --- |
| `get_reconciliation_summary` | Engine reports for portfolio totals and held groups |
| `list_anomalies` | Engine findings filtered by hospital, period or anomaly type |
| `get_anomaly_details` | Evidence records, amounts and review actions for one anomaly |
| `get_hospital_reconciliation` | Settlement and payment status for a hospital and period |
| `get_review_priorities` | Deterministic business priority and separately validated advisory priority when available |
| `search_business_knowledge` | BM25 retrieval of simulated guidance and section identifiers |

The knowledge corpus supplies procedure and escalation guidance. The engine owns financial amounts and settlement status. The Agent cannot select contracts, alter reports or execute payments. [Architecture](architecture.md) · [Agent design](agent_design.md) · [RAG design](rag_design.md)

### Entry points

Start with the Windows commands in the [English README](../README.md#quick-start) or the [Simplified Chinese README](../README_CN.md#快速启动). Default engine and analysis CLI runs write to the ignored `outputs/` directory. Use a separate `--output-dir` to preserve existing reports. The fixture generator rewrites the four sample CSVs in place. The Streamlit sample run and the Mock walkthrough require no fixture regeneration or credentials. [Local usage and troubleshooting](streamlit_guide.md)
