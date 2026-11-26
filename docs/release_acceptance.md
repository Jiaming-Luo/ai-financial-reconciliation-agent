# GitHub release acceptance record

Archived on 2026-11-27 for Step 08C-5. The reviewed GitHub repository is [Jiaming-Luo/ai-financial-reconciliation-agent](https://github.com/Jiaming-Luo/ai-financial-reconciliation-agent). The verified Private baseline is commit [613665f855a9ed2dfb11f5c6948da97e0615d2e6](https://github.com/Jiaming-Luo/ai-financial-reconciliation-agent/commit/613665f855a9ed2dfb11f5c6948da97e0615d2e6) on `main`. The user reported the browser results below. The browser checks cover that 100-file baseline. This record was approved for inclusion in Step 08C-6.

## User browser acceptance

| Check on the Private GitHub repository | User-reported result |
| --- | --- |
| English and Simplified Chinese README rendering | PASS for both versions |
| Two-way README language switching | PASS |
| Application screenshot rendering | PASS |
| Mermaid rendering | PASS for all four diagrams in each README |
| Live assistant financial evidence, knowledge evidence and priority comparison | All three links opened |
| Representative links to the Chinese PRD, test report and synthetic contract records | All opened |
| Blocking rendering issues | None reported |

[English README](../README.md) · [Simplified Chinese README](../README_CN.md) · [Simulation and Live screenshot sources](demo_capture_plan.md)

## Read-only release checks

- Before archiving, local `main` was clean with an empty index and tracked `origin/main`. Authenticated queries confirmed the expected owner and repository, **Private** visibility and `main` as the default. The remote advertised only `refs/heads/main` and its SHA matched the sole local root commit. GitHub listed the same 100 file paths.
- The 100 committed files and working copies matched the SHA-256 delivery manifest. Content review found no publication blockers. The approved noreply identity was the author and committer, the synthetic input identifiers were retained and all 12 PNGs decoded without ancillary metadata. The local core files and repository history stayed at their validated baseline.
- The baseline's 142 local links, anchors and screenshot references were checked across 27 Markdown files. Both README files link to all 12 screenshot assets and to each other. The eight Mermaid blocks passed local syntax and node-reference checks, while the GitHub rendering results above come from the user's manual inspection.
- All 227 offline automated tests and `pip check` passed again during Step 08C-6 in an isolated copy. The four sample CSVs and three freshly generated financial reports matched the SHA-256 baseline. The separate user-run Qwen Live results are recorded in the test report. The release review made no new model calls.

[Offline and Live test record](test_report.md) · [Architecture](architecture.md) · [Input data dictionary](data_dictionary.md)

## Before making the repository public

- [x] Confirm the Private target, expected `main` SHA, sole root commit and matching 100-file inventory.
- [x] Review the file contents, source data, commit metadata and screenshot metadata and privacy.
- [x] Record the user's GitHub rendering acceptance and retain the offline and user-run Live evidence separately.
- [x] Check that the README describes a local MVP, simulated inputs, advisory AI, mandatory human review and the limits of BM25 and model validation.
- [x] Approve inclusion of this acceptance record and confirm the repository description, topics and Release title.
- [ ] Confirm the exact candidate commit and final Release Notes before changing visibility.
- [ ] Authorize the visibility change and any tag or GitHub Release as separate publishing actions. Recheck the repository and exact released commit after those actions.

## Approved GitHub metadata copy

**Repository description**

> Bilingual AI financial reconciliation MVP with Python, Streamlit, Qwen Agent, BM25 RAG, evidence-backed anomaly review and human-in-the-loop controls.

**Topics**

`python`, `streamlit`, `ai-agent`, `llm`, `rag`, `bm25`, `qwen`, `function-calling`, `financial-reconciliation`, `anomaly-detection`, `human-in-the-loop`, `bilingual`

## v1.0.0 Release draft

**Title**

`v1.0.0 — Bilingual Financial Reconciliation MVP`

**Release notes**

First release of a bilingual, Windows-local MVP for financial reconciliation and human review using synthetic CNY records.

- A deterministic Python engine matches contract effective dates and billing units, reconciles service charges against payments, and detects nine anomaly types. Reviewers can trace findings to source evidence and inspect held settlements.
- The English and Simplified Chinese Streamlit interface has five pages covering the dashboard, reconciliation, anomaly review, AI Assistant and Knowledge Base.
- The Agent uses six allowlisted, read-only tools and local BM25 retrieval over bilingual business guidance. Anomaly reports use the v3.0 schema and the application validates evidence references before presenting them.
- Mock mode runs offline without an API key. Optional Qwen Live requests require explicit authorization. The repository includes 12 reviewed Mock and Live screenshots.
- If AI output fails validation, deterministic amounts, business priorities and review flags remain available. AI priority suggestions remain separate from business priorities, and a human must confirm the next action.
- Validation includes 227 offline automated tests, separate user-run Qwen Live scenarios on synthetic data, and manual GitHub checks for both README files, screenshots, links and Mermaid diagrams.

Run locally with Python 3.13 using the README quick start. The app starts in Mock mode with repository samples.

This MVP uses simulated records and policies. BM25 can miss paraphrases, and Live model output can still be rejected. Human review remains required. The documented validation covers specific scenarios. Production reliability and overall model accuracy have not been established.
