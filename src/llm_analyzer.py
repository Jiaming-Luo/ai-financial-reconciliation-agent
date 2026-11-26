"""Run advisory analysis and render it alongside authoritative engine data."""

import json
from datetime import datetime, timezone
from html import escape
from pathlib import Path

from .action_catalog import ACTION_CATALOG
from .context_builder import SOURCE_FILES, AnalysisContext, ContextError
from .hypothesis_catalog import CATALOG
from .llm_client import LLMProvider
from .output_validator import optional_analysis, validate_output
from .prompts import OPTIONAL_ANALYSIS


REPORT_SCHEMA_VERSION = "3.0"

FACT_EXPLANATIONS = {
    "en": {
        "MISSING_PAYMENT": "The engine found no payment record for this settlement group.",
        "UNDERPAYMENT": "Eligible receipts fall below the engine-calculated receivable.",
        "OVERPAYMENT": "Eligible receipts exceed the engine-calculated receivable.",
        "DUPLICATE_PAYMENT": "The engine flagged repeated use of a payment reference.",
        "PRICE_MISMATCH": "The reported charge differs from the charge calculated using the matching contract.",
        "MISSING_CONTRACT": "The engine found no effective contract for the service.",
        "CONTRACT_OVERLAP": "Multiple effective contracts cover the service. The engine withheld a definitive charge.",
        "UNMATCHED_PAYMENT": "The payment group has no associated service record in the source.",
        "INVALID_DATA": "The engine flagged invalid source data for review.",
    },
    "cn": {
        "MISSING_PAYMENT": "财务引擎未在该结算组找到付款记录。",
        "UNDERPAYMENT": "有效付款低于财务引擎计算的应收。",
        "OVERPAYMENT": "有效付款高于财务引擎计算的应收。",
        "DUPLICATE_PAYMENT": "财务引擎发现付款参考号重复出现。",
        "PRICE_MISMATCH": "报送金额与按匹配合同计算的金额有差异。",
        "MISSING_CONTRACT": "财务引擎未找到适用于该业务的有效合同。",
        "CONTRACT_OVERLAP": "该业务日期落在多个有效合同的适用范围内。引擎未确定最终金额。",
        "UNMATCHED_PAYMENT": "该付款组在源文件中没有对应的业务记录。",
        "INVALID_DATA": "财务引擎标记了需要复核的无效源数据。",
    },
}


REPORT_TEXT = {
    "en": {
        "title": "Financial anomaly analysis",
        "mock_notice": "Simulated analysis generated locally. No model API was called.",
        "review": "A human reviewer must verify the evidence, hypotheses and proposed actions before use.",
        "limits": "Selected hypotheses, review actions, priorities and supplementary notes are advisory. Language checks cannot establish factual accuracy.",
        "omission_notice": "Some supplementary AI notes were omitted by validation. The core structured analysis passed.",
        "optional_note": "Supplementary AI note (unverified)",
        "exact_duplicate": "The engine counted the exact duplicate only once.",
        "unresolved_duplicate": "The repeated reference remains unresolved.",
        "provisional": "The financial input is incomplete. This report is for source review only. Aggregate financial totals are withheld.",
        "provisional_summary": "The input is provisional. Focus review on source completeness and unresolved evidence.",
        "empty_summary": "The supplied financial reports contain no detected anomalies.",
        "findings_summary": "Review the flagged findings and verify the supporting evidence before deciding how to proceed.",
        "source": "Data source", "provider": "Provider", "model": "Model", "mode": "Run mode",
        "time": "Analysis time (UTC)", "scope": "Scope", "summary": "Executive summary",
        "usage": "Token usage", "input_tokens": "Input", "output_tokens": "Output", "total_tokens": "Total",
        "engine": "Authoritative engine figures (CNY where applicable)", "findings": "Anomaly findings",
        "metric": "Metric", "value": "Value",
        "limitations": "Limitations", "references": "Evidence references", "group": "Settlement group",
        "settlement_status": "Engine settlement status",
        "priority": "Suggested priority", "causes": "Possible causes (unverified)", "actions": "Manual review actions",
        "unknown": "Unknown", "none": "None", "finding_amounts": "Finding amounts",
        "group_amounts": "Settlement amounts", "expected_amount": "Expected", "actual_amount": "Actual",
        "paid_amount": "Paid", "difference_amount": "Difference (expected minus actual or paid)",
        "settlement_group_count": "Settlement groups", "anomalous_group_count": "Groups with findings",
        "held_group_count": "Held groups", "comparable_group_count": "Comparable groups",
        "reliable_receivable_amount": "Reliable receivable",
        "comparable_receivable_amount": "Comparable receivable", "comparable_paid_amount": "Comparable payments",
        "net_difference": "Net difference", "held_eligible_payment_amount": "Eligible payments in held groups",
        "unmatched_payment_amount": "Unmatched payments",
    },
    "cn": {
        "title": "财务异常分析",
        "mock_notice": "本报告为本地生成的模拟分析，未调用模型 API。",
        "review": "使用前须由人工核实证据、原因假设和处理建议。",
        "limits": "所选原因假设、核查建议、优先级及补充分析仅供复核。语言检查无法确认内容真实。",
        "omission_notice": "部分 AI 补充分析未通过校验，已省略。核心结构化分析已通过。",
        "optional_note": "AI 补充分析（待复核）",
        "exact_duplicate": "引擎对完全重复的记录只计入一次。",
        "unresolved_duplicate": "该重复付款参考号仍待核实。",
        "provisional": "财务输入不完整。本报告仅用于复核来源数据，暂不展示财务汇总金额。",
        "provisional_summary": "输入为临时结果，请优先核查数据完整性及存在疑问的原始证据。",
        "empty_summary": "提供的财务报告中未检出异常。",
        "findings_summary": "请复核报告列出的异常与支持证据，再决定如何处理。",
        "source": "数据来源", "provider": "供应商", "model": "模型", "mode": "运行模式",
        "time": "分析时间（UTC）", "scope": "分析范围", "summary": "管理层摘要",
        "usage": "Token 用量", "input_tokens": "输入", "output_tokens": "输出", "total_tokens": "合计",
        "engine": "财务引擎统计（金额为 CNY）", "findings": "异常发现",
        "metric": "指标", "value": "数值",
        "limitations": "已知限制", "references": "证据记录编号", "group": "结算组",
        "settlement_status": "财务引擎结算状态",
        "priority": "建议优先级", "causes": "可能原因（待核实）", "actions": "人工核查建议",
        "unknown": "未知", "none": "无", "finding_amounts": "异常金额",
        "group_amounts": "结算组金额", "expected_amount": "应收或合同预期",
        "actual_amount": "实际", "paid_amount": "实付", "difference_amount": "差额（预期减实际）",
        "settlement_group_count": "结算组数", "anomalous_group_count": "异常组数",
        "held_group_count": "挂起组数", "comparable_group_count": "可比较组数",
        "reliable_receivable_amount": "可可靠计算的应收",
        "comparable_receivable_amount": "可比较组应收", "comparable_paid_amount": "可比较组实付",
        "net_difference": "净差额", "held_eligible_payment_amount": "挂起组有效付款",
        "unmatched_payment_amount": "无对应业务的付款",
    },
}
DISPLAY_TOTALS = (
    "settlement_group_count", "anomalous_group_count", "held_group_count",
    "comparable_group_count", "reliable_receivable_amount", "comparable_receivable_amount",
    "comparable_paid_amount", "net_difference", "held_eligible_payment_amount",
    "unmatched_payment_amount",
)


def _fact_explanation(source: dict, language: str) -> str:
    kind = source["anomaly_type"]
    labels = REPORT_TEXT[language]
    fact = FACT_EXPLANATIONS[language][kind]
    if kind == "DUPLICATE_PAYMENT":
        resolution = source["payment_reference_resolution"]
        if resolution == "EXACT_COPY_COUNTED_ONCE":
            return f"{fact} {labels['exact_duplicate']}"
        if resolution == "UNRESOLVED_REFERENCE":
            return f"{fact} {labels['unresolved_duplicate']}"
    if kind in {"MISSING_PAYMENT", "UNDERPAYMENT", "OVERPAYMENT", "UNMATCHED_PAYMENT", "PRICE_MISMATCH"}:
        parts = []
        for field, amount in source["amounts"].items():
            value = f"CNY {amount}" if amount is not None else labels["unknown"]
            parts.append(f"{labels[field]} {value}")
        return f"{fact} {' · '.join(parts)}"
    return fact


def _render_selections(selections: list[dict], catalog: dict, code_field: str, references: dict, language: str) -> list[dict]:
    rendered = []
    for selection in selections:
        code = selection[code_field]
        entry = catalog[code]
        rendered.append({
            code_field: code,
            "evidence_references": [references[ref] for ref in selection["evidence_references"]],
            "description": entry.describe(language),
            "review_required": entry.review_required,
        })
    return rendered


def analyze(context: AnalysisContext, provider: LLMProvider, language: str) -> dict:
    """Reject invalid provider output before constructing a publishable report."""
    labels = REPORT_TEXT[language]
    payload = context.model_input(language)
    if len(payload["findings"]) > 40 or len(json.dumps(payload, ensure_ascii=False)) > 75_000:
        raise ContextError("The report exceeds the single-analysis limit of 40 findings or 75,000 context characters.")
    response = provider.generate(language, payload)
    result = validate_output(response.text, payload)
    findings = []
    warnings = []
    for index, finding in enumerate(result["anomaly_findings"]):
        source = context.findings[finding["anomaly_id"]]
        reference_map = source["reference_map"]
        note, warning = optional_analysis(finding.get(OPTIONAL_ANALYSIS), f"anomaly_findings[{index}].{OPTIONAL_ANALYSIS}")
        if warning:
            warnings.append(warning)
        findings.append({
            "anomaly_id": finding["anomaly_id"],
            "anomaly_type": source["anomaly_type"],
            "explanation": _fact_explanation(source, language),
            "evidence_references": [reference_map[ref] for ref in finding["evidence_references"]],
            "possible_causes": _render_selections(finding["possible_causes"], CATALOG, "cause_code", reference_map, language),
            "recommended_actions": _render_selections(
                finding["recommended_actions"], ACTION_CATALOG, "action_code", reference_map, language,
            ),
            "priority": finding["priority"],
            "requires_human_review": True,
            OPTIONAL_ANALYSIS: note,
            "optional_analysis_status": "rejected" if warning else ("accepted" if note is not None else "not_provided"),
            "hospital_id": source["hospital_id"],
            "settlement_period": source["settlement_period"],
            "settlement_status": source["settlement_status"],
            "engine_amounts": source["amounts"],
            "engine_group_amounts": source["group_amounts"],
        })

    limitations = [labels["limits"]]
    summary = labels["findings_summary"] if findings else labels["empty_summary"]
    if context.provisional:
        limitations.insert(0, labels["provisional"])
        summary = labels["provisional_summary"]
    report = {
        "report_schema_version": REPORT_SCHEMA_VERSION,
        "analysis_status": "completed_with_omissions" if warnings else "completed",
        "core_validation": "passed",
        "warnings": warnings,
        "provider": provider.name,
        "model": response.model,
        "run_mode": provider.mode,
        "analysis_time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "language": language,
        "analysis_scope": payload["analysis_scope"],
        "financial_run_status": context.summary["run_status"],
        "financial_summary": None if context.provisional else context.summary,
        "data_sources": list(SOURCE_FILES),
        "requires_human_review": True,
        "human_review_statement": labels["review"],
        "mode_notice": labels["mock_notice"] if provider.mode == "Mock" else None,
        "executive_summary": summary,
        "anomaly_findings": findings,
        "limitations": limitations,
    }
    if response.usage is not None:
        report["usage"] = response.usage
    return report


def _plain(value) -> str:
    text = escape(str(value).replace("\r", " ").replace("\n", " "))
    return text.translate(str.maketrans({char: f"&#{ord(char)};" for char in r"\[]()`*_#|!~"}))


def _shown(value, labels: dict) -> str:
    return labels["unknown"] if value is None else _plain(value)


def render_markdown(report: dict) -> str:
    labels = REPORT_TEXT[report["language"]]
    lines = [f"# {labels['title']}", ""]
    if report["mode_notice"]:
        lines.extend([f"> {report['mode_notice']}", ""])
    lines.append(f"> {report['human_review_statement']}")
    if report["warnings"]:
        lines.append(f"> {labels['omission_notice']}")
    if report["financial_summary"] is None:
        lines.append(f"> {labels['provisional']}")
    lines.append("")
    for label, key in (("mode", "run_mode"), ("provider", "provider"), ("model", "model"),
                       ("time", "analysis_time"), ("scope", "analysis_scope")):
        lines.append(f"- **{labels[label]}** · {_plain(report[key])}")
    if report.get("usage"):
        usage = ", ".join(f"{labels[field]} {value}" for field, value in report["usage"].items())
        lines.append(f"- **{labels['usage']}** · {usage}")
    lines.append(f"- **{labels['source']}** · {', '.join(_plain(name) for name in report['data_sources'])}")
    lines.extend(["", f"## {labels['summary']}", "", _plain(report["executive_summary"])])

    summary = report["financial_summary"]
    if summary is not None:
        lines.extend(["", f"## {labels['engine']}", "",
                      f"| {labels['metric']} | {labels['value']} |", "| --- | ---: |"])
        lines.extend(f"| {labels[key]} | {_shown(summary[key], labels)} |" for key in DISPLAY_TOTALS)
    lines.extend(["", f"## {labels['findings']}", ""])
    if not report["anomaly_findings"]:
        lines.append(labels["none"])
    warnings = {warning["path"]: warning["rule"] for warning in report["warnings"]}
    for index, finding in enumerate(report["anomaly_findings"]):
        lines.extend([
            f"### {_plain(finding['anomaly_id'])} · {_plain(finding['anomaly_type'])}", "",
            _plain(finding["explanation"]), "",
            f"- **{labels['group']}** · {_shown(finding['hospital_id'], labels)} / "
            f"{_shown(finding['settlement_period'], labels)}",
            f"- **{labels['settlement_status']}** · {_shown(finding['settlement_status'], labels)}",
            f"- **{labels['priority']}** · {_plain(finding['priority'])}",
            f"- **{labels['references']}** · "
            + (", ".join(_plain(ref) for ref in finding["evidence_references"]) or labels["none"]),
        ])
        for label, key in (("finding_amounts", "engine_amounts"), ("group_amounts", "engine_group_amounts")):
            amounts = " · ".join(
                f"{labels[field]} {_shown(value, labels)}" for field, value in finding[key].items()
            )
            lines.append(f"- **{labels[label]}** · {amounts}")
        for title, key, code in (
            ("causes", "possible_causes", "cause_code"),
            ("actions", "recommended_actions", "action_code"),
        ):
            lines.extend(["", f"**{labels[title]}**", ""])
            for item in finding[key]:
                lines.append(f"- {_plain(item['description'])} ({_plain(item[code])})")
                if item["evidence_references"]:
                    refs = ", ".join(_plain(ref) for ref in item["evidence_references"])
                    lines.append(f"  - {labels['references']} · {refs}")
        if finding[OPTIONAL_ANALYSIS] is not None:
            lines.extend(["", f"**{labels['optional_note']}**", "", _plain(finding[OPTIONAL_ANALYSIS])])
        elif finding["optional_analysis_status"] == "rejected":
            path = f"anomaly_findings[{index}].{OPTIONAL_ANALYSIS}"
            lines.extend(["", f"> {labels['omission_notice']} `{warnings[path]}`"])
        lines.append("")
    lines.extend([f"## {labels['limitations']}", ""])
    lines.extend(f"- {_plain(text)}" for text in report["limitations"])
    return "\n".join(lines) + "\n"


def write_analysis(report: dict, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    basename = output_dir / f"ai_analysis_{report['language']}"
    basename.with_suffix(".json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n",
    )
    basename.with_suffix(".md").write_text(render_markdown(report), encoding="utf-8", newline="\n")
