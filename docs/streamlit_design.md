# Streamlit application design

The Windows-local application integrates the existing engine, analysis layer, Agent and BM25 knowledge base. The MVP uses synthetic data and simulated business guidance. The UI neither approves settlements nor executes financial transactions. [Local usage guide](streamlit_guide.md)

| Module | Responsibility |
| --- | --- |
| `app.py` | Page layout, bilingual navigation and initial local sample run |
| `ui/pages.py` | Five views, filters, evidence presentation, downloads and explicit AI forms |
| `ui/services.py` | Input boundaries, transient file adapter and delegation to the existing services |
| `ui/diagnostics.py` | Allowlisted error metadata for the Anomaly Review result panel |
| `ui/session.py` | Invalidate the prior dataset snapshot, AI analysis and Agent result together |
| `ui/text.py` | User-facing English and Simplified Chinese labels, with stable domain codes |
| `.streamlit/config.toml` | Local binding, upload limit, disabled analytics and the light theme |

### Financial data lifecycle

Each browser session starts with an engine run on the repository samples. The four sample files are available for viewing and download. The engine consumes only the three core tables. The oracle remains a test fixture. For user-supplied synthetic data, the app bounds the CSV size and records, validates UTF-8 and required headers, and rejects path-like names and formula-prefixed identifiers. Upload names are never used as filesystem paths. The existing engine validates data values and retains recoverable row findings. Unassigned input issues make the results provisional and block AI actions.

The app creates a unique temporary directory under ignored `outputs/` only while a service runs. The three financial artifacts are retained in the browser session's server-side memory as bytes. Later analysis and Agent actions reconstruct the same artifact set in their own temporary directory. The UI never overwrites baseline `outputs` or sample files. Selecting a different data source or changing an upload immediately discards old financial results and their derived evidence. Reloading starts a fresh session. The app uses no shared result cache.

Dashboard totals come from the engine summary. Hospital and period filters change only the preview table. Settlement statuses and anomaly counts have separate count charts. Comparable, anomalous and held group counts are not used as slices of a single pie. Provisional runs temporarily hide portfolio amounts. Original amount strings, CSV blanks and JSON nulls are preserved in downloads. Unknown amounts use a localized label on screen.

Monetary values use wrapping cards with exact two-decimal formatting. The comparable amounts have three cards across, and held and unmatched payments have two. Each dashboard distribution has a full-width chart. Axes show short language-specific names and the tooltip shows the stable enum. Related records and evidence roles present full identifiers one per line.

### AI and review boundaries

Mock is the default. Mock analysis uses the existing deterministic provider. Mock Assistant presents explicit scripted examples. Live mode merely exposes a form. An AI request requires a submission and an explicit authorization checkbox. The app validates the submitted Qwen endpoint using `QwenSettings`, then delegates to the existing provider and Agent. The model, endpoint and masked key are scoped to the form. A new form identity clears submitted credentials on success and failure. No credentials are loaded from files or written to URL parameters, persistent session files, reports or logs by the app. Page navigation, downloads, selectors, filters and reruns cannot resubmit the form.

The analysis view displays the existing v3.0 report and downloads its JSON and Markdown. Deterministic business priority comes from the existing read-only finance tool, and AI priority comes from the validated analysis finding. The Assistant preserves the six tools, request and token limits, zero retries, and exact-reference checks of the existing Agent. `E` sections render the tool's financial evidence. `K` sections show the original policy passage, document and section, guidance and simulation scope. Raw evidence uses plain text, tables or a JSON expander. The app enables no unsafe HTML. The knowledge page uses only the local BM25 index.

### Analysis failure diagnostics

The CLI and Streamlit both use `build_context()`, `analyze()` and the Qwen adapter. For the same financial artifacts and language, the simulated HTTP comparison found the same request body, including the model and strict `anomaly_analysis` schema. The CLI can read its configuration from the environment. The UI uses an explicitly authorized form with a 30-second timeout and zero retries.

Provider and validator exceptions now expose safe metadata alongside their existing messages. The result panel's **Error diagnostics** expander shows fields such as an error code, stage, available HTTP code and schema path, JSON type names and static enum values. A request count is shown only when the result or error stage establishes it. The UI maps codes to fixed localized messages and retains neither exceptions nor raw model or transport values. A new analysis clears any prior analysis and the related Assistant result if it could have used that report. Invalid output still rejects publication. Financial results and deterministic priorities remain usable on failure.

### v3.0 analysis output checks

Step 07G leaves the v3.0 schema intact. Both languages send the same machine-readable contract. The shared instructions list required fields and the priority enum from the schema. The model copies each code verbatim from the corresponding per-finding options in the input. One supported cause and one supported action meet the selection minimum. Include additional codes only when evidence supports them. The supplementary note is the only model output field that needs localization.

| Field | Request schema | Local checks |
| --- | --- | --- |
| `anomaly_findings` | Required root array of closed finding objects | Each supplied anomaly appears exactly once. An empty list is valid for empty input. |
| `anomaly_id`, `anomaly_type` | Strings | The ID must identify a supplied finding. The type must match that same finding. |
| `possible_causes`, `recommended_actions` | Arrays of one to eight closed objects, each with a code and evidence references | Selections must be distinct, applicable to the anomaly, require human review and have any required evidence. The cause fallback must appear alone. |
| `cause_code`, `action_code`, `priority` | String enums defined by the catalogs and priority list | The validator checks the same enums. A catalog member still needs to meet the selection rules for its finding. |
| `evidence_references` | Arrays of strings | Finding references must be distinct and scoped to that anomaly. The list must be nonempty if evidence is available. Selection references must be a distinct subset of the finding's citations and meet required roles and minimum counts. |
| `optional_analysis` | Required key with a string or null value | Existing fail-closed note handling remains. An omitted note is treated as absent. An invalid note body is withheld and the report records the omission after core validation passes. |
| Run, settlement and report statuses, amounts and review flags | Outside the model response | The engine, validated context and report renderer supply these values. The Agent final-answer status uses a separate contract. |

The UI distinguishes structural violations such as `type`, `enum` and `required` from selection rules such as `distinct_codes` and `exclusive_fallback`, and evidence rules such as `applicable_code` and `required_evidence`. Diagnostic enum lists come from the static schema. Each finding may allow a smaller subset. For an invalid string, the diagnostic can show its character length. It never shows the model value or source record identifiers from validation errors.

### Final acceptance scope

The user's local browser review covered five pages, both interface languages, Mock workflows and two Qwen Live workflows with `qwen3.8-flash`. After the earlier Anomaly Review failures and the Step 07G changes, the Live analysis displayed `Completed` and both report download controls. Four business-high anomalies received lower AI suggested priorities. Business priority, amounts, settlement status and review flags remained authoritative. The user confirmed that the endpoint, masked key and consent cleared after submission and the model name remained visible.

Offline AppTest and simulated HTTP cover the interface, request boundaries and failure isolation. Browser Live acceptance applies to the two user-run scenarios on synthetic records. A valid report does not establish the accuracy of model suggestions. BM25 can miss paraphrases, and real model output can still fail the contract. Production validation remains pending. [Final acceptance and failure history](test_report.md#step-07-final-acceptance-and-checkpoint-03)
