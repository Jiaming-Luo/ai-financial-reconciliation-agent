# Local Streamlit usage

## Start on Windows

Run from the repository root in Windows PowerShell. The project was verified with Python 3.13.7. On a fresh checkout, confirm Python 3.13 is on PATH with `python --version` and create `.venv` with `python -m venv .venv`. Reuse an existing project virtual environment if it already uses the tested Python version.

```powershell
.\.venv\Scripts\python.exe -B -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -B -m streamlit run app.py --server.address=127.0.0.1 --server.port=8501
```

Open `http://127.0.0.1:8501` in a local browser. The app starts in English and Mock mode with the repository sample reconciliation. Choose **简体中文** in the sidebar to switch display language. Stop the server with Ctrl+C in the launching terminal.

## Offline demonstration

1. **Dashboard** shows run-wide amounts and counts. Select a hospital and period to filter the table. For `SIM-H004` and `2026-05`, compare the held payment with the unknown expected amount and difference.
2. **Reconciliation** can rerun the repository samples or run the three synthetic UTF-8 CSV uploads. Review each file's columns and preview, then select **Run reconciliation**. Choose the financial result you need under the download expander. The fourth repository sample contains test expectations and is available only as a sample reference.
3. **Anomaly Review** lets you filter the findings and select an anomaly to inspect group amounts, records and actions. Select **Run AI analysis** to run the deterministic Mock analysis and download its version 3.0 JSON or Markdown. AI recommendations are advisory.
4. **AI Assistant** offers fixed Mock scenarios. For a mixed example, select the question about `SIM-H004` in May 2026 and select **Ask assistant**. Inspect the financial `E` evidence and the simulated policy `K` evidence. Use the tool-trace expander to inspect the validated calls.
5. **Knowledge Base** supports local document browsing or keywords such as `contract overlap` or `重复付款`. Select either source language. Scores rank relevance. Conclusions still require independent review.

## Explicit Qwen Live requests

Select **Qwen Live · explicit requests** in the sidebar, then open **Anomaly Review** or **AI Assistant**. In the form, enter an approved Alibaba Cloud HTTPS Base URL ending in `/compatible-mode/v1`, the model name and the DashScope key in the masked field. Confirm **Authorize this Live request**, then select the relevant action button. The key and endpoint fields clear after submission. Real API usage and charges depend on the account. The application is read-only and should receive only synthetic data.

The application does not contact Qwen on startup or when changing language, navigating, filtering or downloading. If an analysis fails, expand **Error diagnostics** under **AI analysis result**. Record the error code, stage and any displayed HTTP status, validation path, constraint, types and string length. A cause, action or priority type or enum error also shows the static schema choices. Individual findings can allow fewer codes depending on their evidence. Share only the displayed diagnostic metadata. Financial results and deterministic review priorities remain available. The previous AI report is cleared, and a retry requires a new submission.

The user completed the browser Live Agent + RAG scenario on `qwen3.8-flash`. The separate Live anomaly analysis initially failed, including a local rejection at `anomaly_findings[0].possible_causes[1].cause_code` after the first diagnostics update. After Step 07G, the user's browser retest displayed **Completed** with JSON and Markdown download controls. OpenAI analysis remains available in the CLI and has offline validation only. [Final acceptance and failure history](test_report.md#step-07-final-acceptance-and-checkpoint-03)

To reproduce the analysis scenario, select **English**, **Repository samples**, and **Qwen Live**. In **Anomaly Review**, submit one authorized analysis with `qwen3.8-flash`. A successful response produces a validated v3.0 report, AI suggested priorities and download controls. Read those priorities alongside **Business priority** and retain human review. On failure, expand **Error diagnostics**. No old AI report should remain, and business priorities and financial evidence remain available. The endpoint, masked key and consent controls clear after submission.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Python or Streamlit fails to start | Check `python --version`, then confirm that the app and `pip install -r requirements.txt` use the same `.venv` interpreter. Use `pip check` inside that environment. |
| Port 8501 is already in use | Stop the earlier instance from its terminal with Ctrl+C, or choose another local port with `--server.port` and use that port in the browser. |
| The Agent or analysis CLI cannot read reports | Run `main.py` first and give both consumers the same `--input-dir` pointing to the generated report directory. The Streamlit sample workflow runs its own local reconciliation. |
| Financial results are provisional | Inspect the source issues. The finance CLI writes a provisional report and exits with code 2 for unassignable input errors. Streamlit blocks the AI forms on a provisional run. |
| Live analysis returns an error | Inspect **Error diagnostics** and share only the redacted fields. For authentication and permission errors, verify the key, workspace and model permissions. For rejected model output, keep the deterministic results for manual review. |

## Limits

Uploads allow up to 2 MB and 10,000 rows per required file. The table preview caps rows at 200. Report downloads retain the entire run. Each browser session needs its own uploads. There is no cross-session persistence. Streamlit's own table and chart controls may appear in English. BM25 and model output have the limitations documented in the RAG design. [RAG design](rag_design.md) · [Streamlit design](streamlit_design.md)
