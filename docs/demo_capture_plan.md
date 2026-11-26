# Step 08B screenshot capture plan

The Step 08B gallery is complete. Nine offline Mock captures show the walkthrough and two Simplified Chinese views at 1920 × 1080. Three English Live images, supplied by the user, cover the combined query and a separate completed anomaly analysis. Both sets use the repository's synthetic data.

### Locations and naming

- Stage working images in `screenshots/step-08b/`. The repository already ignores the top-level `screenshots/` directory.
- The 12 reviewed images are in [the publication directory](assets/screenshots/) and linked from both README previews. The published copies match the originals byte for byte and retain their original dimensions.
- Use PNG filenames with a two-digit order, a page or scenario, the language and the mode. Use `en` or `cn` and `mock` or `live`.

### English walkthrough

| Suggested filename | Page and mode | Selection | Information to capture |
| --- | --- | --- | --- |
| `01-dashboard-en-mock.png` | Dashboard, English, Mock | Repository samples, hospital and period set to All | Comparable receivable, paid and net difference, held and unmatched payments, and a distribution chart. Include the simulated-data notice. |
| `01b-dashboard-settlement-status-en-mock.png` | Dashboard, English, Mock | Switch to Settlement status distribution. | The second chart tab, with settlement status counts. |
| `02-reconciliation-held-en-mock.png` | Reconciliation, English, Mock | Run Repository samples. Filter `SIM-H004`, `2026-05` and `REVIEW_REQUIRED`. | Held result, paid CNY 10406.50, unknown receivable and difference, and financial download controls. |
| `03-anomaly-contract-overlap-en-mock.png` | Anomaly Review, English, Mock | Filter `SIM-H004`, `2026-05` and `CONTRACT_OVERLAP`. Select `ANOM-000006` and expand evidence by role. | Business priority, human review, `SIM-S0273` and both candidate contracts. Include known and unknown financial fields where visible. |
| `04-assistant-combined-en-mock.png` | AI Assistant, English, Mock | Choose the combined question about `SIM-H004` in May 2026. | Full question, answer status, Mock label, simulated request metrics and human-review notice. The evidence continues in 04b. |
| `04b-assistant-evidence-en-mock.png` | AI Assistant, English, Mock | Scroll the same answer to the two evidence cards. | Financial fields in `E1`, plus the policy source and chapter in `K1`. |
| `05-knowledge-contract-overlap-en-mock.png` | Knowledge Base, English, Mock | Select English documents, search `contract overlap` and expand a matching contract or escalation section. | Search phrase, document and section identifiers, original simulated guidance and review advice. |

### Simplified Chinese views

| Suggested filename | Page and mode | Selection | Information to capture |
| --- | --- | --- | --- |
| `06-anomaly-contract-overlap-cn-mock.png` | 异常复核, 简体中文, Mock | Same hospital, period and finding as the English anomaly view. | Localized labels, 暂无法确定 for unknown amounts, contract identifiers and manual review guidance. |
| `07-knowledge-duplicate-payment-cn-mock.png` | 业务知识库, 简体中文, Mock | Select Simplified Chinese documents, search `重复付款` and expand the relevant simulated payment procedure. | Localized search result, original Chinese passage and its document and section reference. |

### Manual browser Live capture

Use English and Repository samples in the local app. Switch to **Qwen Live · explicit requests**. For each run, enter the approved Qwen HTTPS Base URL, model `qwen3.8-flash` and masked DashScope key privately, select **Authorize this Live request**, and submit once. Capture the result only after the endpoint and key fields clear and consent resets. Keep the form and browser chrome outside the frame.

1. **`08-assistant-combined-en-live.png`**. Open **AI Assistant**, select the combined example or enter “Why is the May 2026 settlement for SIM-H004 on hold, and what should the finance team do next?” Select **Ask assistant**. Capture Live mode, model name, model requests, tool calls, total tokens, elapsed time and human review. Show the financial and knowledge evidence, including paid CNY 10406.50 and the unknown receivable and difference. If the evidence is below the fold, take a second image from the same answer as `08b-assistant-evidence-en-live.png`. Keep the actual evidence IDs and metrics.
2. **`09-anomaly-priority-en-live.png`**. Open **Anomaly Review**, submit **Run AI analysis**, and verify a completed Live result. Leave the anomaly filters at All to show the nine sample rows. Frame the completion status, mode, **Business priority**, **AI suggested priority** and the review flags. Preserve the actual priorities whether they agree or differ. If the run fails, keep it out of the completed gallery and use the redacted diagnostics to troubleshoot.

Save the raw PNGs under `screenshots/step-08b/`. Check the full frame for credentials, account data and endpoints before copying them to the publication directory.

### Reviewed Live captures

| Capture | What the image shows |
| --- | --- |
| [08 · Assistant result](assets/screenshots/08-assistant-combined-en-live.png) | `qwen3.8-flash`, validated citation status, 3 model requests, 3 tools, 7,200 tokens, 5.148 seconds, and `E1` held settlement evidence. |
| [08b · Knowledge evidence](assets/screenshots/08b-assistant-evidence-en-live.png) | `K1`, with KB-06 §1, KB-01 §2 and KB-06 §2, including original excerpts and review guidance. |
| [09 · Anomaly analysis](assets/screenshots/09-anomaly-priority-en-live.png) | Live completion, five differences between independent priority columns, and a review flag on all nine rows. |

These captures document the Step 08B user-run demonstration. The previous Step 07 acceptance has separate request counts, timing and priority observations. [Step 08B record](test_report.md#step-08b-screenshot-delivery-and-final-acceptance) · [Step 07 Live record](test_report.md#user-run-qwen-live-acceptance)

### Publication review

Review the final image at full size. Use only synthetic records. Exclude the credential form, private endpoints, API keys, account identifiers, browser bookmarks, personal paths and notifications. Keep the app's simulated-data and human-review context visible in the walkthrough. Publish captions describing what each actual image shows. [Local usage](streamlit_guide.md)
