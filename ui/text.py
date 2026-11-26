"""Bilingual UI copy and display-only field labels."""

from src.agent_prompts import FIELD_LABELS_CN


LANGUAGES = {"en": "English", "cn": "简体中文"}
PAGES = ("dashboard", "reconciliation", "anomalies", "assistant", "knowledge")
_COPY = {
    "product": ("AI Financial Reconciliation Agent", "智能财务对账助手"),
    "language": ("Language · 语言", "Language · 语言"),
    "navigation": ("Workspace", "工作区"),
    "dashboard": ("Dashboard", "财务总览"),
    "reconciliation": ("Reconciliation", "财务对账"),
    "anomalies": ("Anomaly Review", "异常复核"),
    "assistant": ("AI Assistant", "智能财务助手"),
    "knowledge": ("Knowledge Base", "业务知识库"),
    "prototype": ("Synthetic data and simulated business guidance only. This prototype is for human review and is not a production financial system.",
                  "仅使用模拟数据和模拟业务规范。本原型用于人工复核，非生产级财务系统。"),
    "provider": ("AI mode", "AI 模式"),
    "mock": ("Mock · offline", "Mock · 离线模拟"),
    "live": ("Qwen Live · explicit requests", "Qwen Live · 手动请求"),
    "mock_notice": ("Mock uses deterministic analysis and selected Agent scenarios. It cannot answer arbitrary questions as a real model would.",
                    "Mock 使用确定性分析和指定的助手演示场景，不能像真实模型一样回答任意问题。"),
    "live_notice": ("Submitting the form sends the current synthetic evidence to Qwen. Enter credentials for this request. Viewing pages never calls the model.",
                    "提交表单会将当前模拟证据发送给 Qwen。请为本次请求填写凭证。浏览页面不会调用模型。"),
    "live_confirm": ("Authorize this Live request", "授权本次 Live 请求"),
    "live_needs_confirmation": ("Confirm this Live request before submitting.", "请先确认授权本次 Live 请求。"),
    "api_key": ("DashScope API key", "百炼 API Key"),
    "base_url": ("Approved Qwen HTTPS Base URL", "受信任的 Qwen HTTPS Base URL"),
    "model": ("Model", "模型"),
    "run_mode": ("Run mode", "运行模式"),
    "run_status": ("Run status", "运行状态"),
    "not_run": ("Not run for the current data.", "当前数据尚未运行。"),
    "finance_needed": ("Run reconciliation for the current source to use this page.", "请先为当前数据源运行对账。"),
    "finance_failed": ("The reconciliation run failed. Check the input files and run again.", "对账运行失败。请核对输入文件后重试。"),
    "ai_failed": ("The AI request failed or its output was rejected. Financial results are still available.",
                  "AI 请求失败或输出未通过校验。财务结果仍可查看。"),
    "invalid_config": ("Check the API key, model, and approved HTTPS Base URL ending in /compatible-mode/v1.",
                       "请检查 API Key、模型名称及以 /compatible-mode/v1 结尾的受信任 HTTPS Base URL。"),
    "question_invalid": ("Enter a question with up to 3,000 characters.", "请输入不超过 3,000 个字符的问题。"),
    "credential_in_question": ("Remove credentials from the question.", "请从问题中移除凭证。"),
    "provisional": ("Input is incomplete. Group rows are provisional, portfolio amounts are withheld, and AI actions are disabled.",
                    "输入不完整。结算组记录仅供临时核查，汇总金额已隐藏，AI 操作已停用。"),
    "provisional_ai_block": ("Resolve unassigned input issues before using AI.", "请先解决未归组的输入问题，再运行 AI。"),
    "review": ("Human review required. Verify source evidence before acting.", "须人工复核。采取任何动作前请核对源证据。"),
    "unknown": ("Not determinable", "暂无法确定"),
    "all": ("All", "全部"), "yes": ("Yes", "是"), "no": ("No", "否"),
    "none": ("No matching records.", "没有符合条件的记录。"),
    "data_source": ("Data source", "数据源"), "sample": ("Repository samples", "仓库模拟样例"),
    "upload": ("Upload synthetic CSVs", "上传自定义模拟 CSV"),
    "sample_unavailable": ("The repository sample files are unavailable.", "仓库模拟样例文件不可用。"),
    "upload_help": ("Upload the three UTF-8 CSV tables. Each may contain up to 2 MB and 10,000 rows. Use synthetic records only.",
                    "上传三张 UTF-8 CSV 表。每份最多 2 MB、10,000 行。仅使用模拟记录。"),
    "clear_uploads": ("Clear uploaded files", "清除已上传文件"),
    "files_ready": ("Files retained for this browser session", "本浏览器会话已保留的文件"),
    "required_fields": ("Required fields", "必填字段"),
    "sample_downloads": ("Sample CSV downloads", "下载样例 CSV"),
    "contracts.csv": ("Contract versions and unit prices", "合同版本及单价"),
    "service_records.csv": ("Service quantities, dates and reported amounts", "业务数量、发生日期及报送金额"),
    "payments.csv": ("Payment references, amounts and settlement periods", "付款参考号、金额及结算期"),
    "expected_anomalies.csv": ("Test expectations · excluded from reconciliation", "测试预期 · 不参与对账"),
    "invalid_file_type": ("Choose a plain CSV filename without a path.", "请选择不含路径的 CSV 文件。"),
    "invalid_file_size": ("The CSV must be nonempty and no larger than 2 MB.", "CSV 不能为空且不得超过 2 MB。"),
    "invalid_csv": ("The file is not a well-formed UTF-8 CSV.", "文件不是格式正确的 UTF-8 CSV。"),
    "invalid_header": ("The CSV header does not match the required fields.", "CSV 表头与必填字段不匹配。"),
    "invalid_identifier": ("Identifiers must not begin with a spreadsheet formula prefix.", "标识字段不能以电子表格公式前缀开头。"),
    "incomplete_upload": ("Upload all three required tables before running reconciliation.", "运行对账前请上传全部三张必需表。"),
    "too_many_rows": ("The CSV exceeds the 10,000-row limit.", "CSV 超过 10,000 行上限。"),
    "workspace_error": ("The local operation directory is unavailable.", "本地运行目录不可用。"),
    "run_finance": ("Run reconciliation", "运行对账"),
    "run_analysis": ("Run AI analysis", "运行 AI 分析"),
    "ask": ("Ask assistant", "向助手提问"),
    "question": ("Question", "问题"),
    "example": ("Example question", "示例问题"),
    "custom": ("Custom question", "自定义问题"),
    "full_run": ("Run-wide metrics. Filters apply to the preview table only.", "指标为本次完整运行口径，筛选仅影响预览表。"),
    "scope_metrics": ("Comparable amounts exclude held and unmatched groups. Group counts can overlap.",
                      "可比较金额排除挂起及无对应业务付款组。结算组计数可能交叉。"),
    "preview": ("Reconciliation results", "对账结果"),
    "net_difference": ("Comparable net difference", "可比较净差额"),
    "held_eligible_payment_amount": ("Held group payments", "挂起组付款金额"),
    "preview_limit": ("Showing up to 200 matching rows. Downloads include the entire run.", "最多展示 200 条匹配记录，下载包含本次完整结果。"),
    "download_finance": ("Download financial results", "下载财务结果"),
    "download_analysis": ("Download AI analysis", "下载 AI 分析"),
    "category": ("Category", "类别"), "count": ("Count", "数量"),
    "anomaly_distribution": ("Anomaly distribution", "异常类型分布"),
    "status_distribution": ("Settlement status distribution", "结算状态分布"),
    "review_select": ("Anomaly to review", "待复核异常"),
    "records": ("Related records", "关联记录"), "source_evidence": ("Source evidence", "源证据"),
    "technical": ("Structured details", "结构化详情"),
    "anomaly_amounts": ("Anomaly amounts · CNY", "异常金额 · CNY"),
    "group_amounts": ("Settlement group amounts · CNY", "结算组金额 · CNY"),
    "hypotheses": ("Possible causes · human review required", "原因假设 · 需人工复核"),
    "actions": ("Human review actions", "人工核查动作"),
    "analysis_language": ("Report language", "报告语言"),
    "answer_language": ("Answer source language", "回答证据语言"),
    "analysis_result": ("AI analysis result", "AI 分析结果"),
    "assistant_result": ("Assistant result", "助手结果"),
    "tools": ("Tool call trace", "工具调用轨迹"),
    "model_requests": ("Model requests", "模型请求次数"),
    "mock_model_requests": ("Simulated model requests", "模拟模型请求次数"),
    "tool_calls": ("Tool calls", "工具调用次数"),
    "total_tokens": ("Total tokens", "Token 总量"),
    "elapsed_seconds": ("Elapsed seconds", "耗时（秒）"),
    "knowledge_evidence": ("Knowledge evidence", "知识证据"),
    "financial_evidence": ("Financial evidence", "财务证据"),
    "files": ("Source files", "来源文件"),
    "catalog": ("Document library", "规范文档库"), "document": ("Document", "文档"),
    "doc_language": ("Document language", "文档语言"),
    "keywords": ("Search keywords", "检索关键词"),
    "kb_notice": ("Local BM25 search. The ranking score measures relevance, not correctness or confidence.",
                  "使用本地 BM25 检索。分数表示检索相关性，不代表正确率或置信概率。"),
    "kb_invalid": ("Enter printable search text with up to 320 characters.", "请输入不超过 320 个字符的可显示检索文字。"),
    "kb_failed": ("The local knowledge index is unavailable.", "本地知识索引不可用。"),
    "scope": ("Scope", "适用范围"), "guidance": ("Review guidance", "人工核查建议"),
    "score": ("BM25 relevance", "BM25 相关性"),
    "source_excerpt": ("Original excerpt", "章节原文"),
    "completed": ("Completed", "已完成"), "completed_with_omissions": ("Completed with omitted content", "已完成，有内容省略"),
    "answered": ("Answered · evidence references validated", "已回答 · 证据引用通过校验"),
    "insufficient_evidence": ("Insufficient verified evidence", "有效证据不足"),
    "refused": ("Outside read-only scope", "超出只读权限范围"),
    "failed": ("Request failed", "请求失败"),
    "diagnostic": ("Error diagnostics", "错误诊断"),
    "error_code": ("Error code", "错误代码"), "error_stage": ("Error stage", "错误阶段"),
    "http_status": ("HTTP status", "HTTP 状态"), "validation_path": ("Validation path", "校验路径"),
    "validation_constraint": ("Validation constraint", "校验约束"),
    "expected_type": ("Expected type", "预期类型"), "actual_type": ("Actual type", "实际类型"),
    "actual_string_length": ("Actual string length", "实际字符串长度"),
    "allowed_values": ("Allowed values", "允许值"), "model_request_count": ("Model request count", "模型请求数"),
    "configuration": ("Configuration", "配置"), "request": ("Request", "请求"), "response": ("Response", "响应"),
    "validation": ("Output validation", "输出校验"), "context": ("Financial context", "财务上下文"), "storage": ("Local files", "本地文件"),
    "enum_code": ("Enum code", "枚举编码"),
}

DIAGNOSTIC_MESSAGES = {
    "authentication_failed": ("Qwen rejected authentication. Check the key and its workspace.", "Qwen 认证失败。请检查密钥和对应工作空间。"),
    "permission_denied": ("Qwen denied access. Check workspace and model permissions.", "Qwen 拒绝访问。请检查工作空间和模型权限。"),
    "endpoint_not_found": ("The Qwen endpoint or model was not found.", "未找到 Qwen 接入地址或模型。"),
    "rate_limited": ("Qwen reported a quota or rate limit.", "Qwen 报告配额不足或限流。"),
    "request_timeout": ("The Qwen request timed out.", "Qwen 请求超时。"),
    "connection_failed": ("The application could not connect to Qwen.", "应用无法连接 Qwen。"),
    "redirect_rejected": ("Qwen redirected the request. The redirect was blocked.", "Qwen 重定向请求，重定向已被阻止。"),
    "http_request_failed": ("Qwen rejected the request or reported a service error.", "Qwen 拒绝请求或报告服务错误。"),
    "sdk_response_error": ("The SDK could not complete the request or process its response.", "SDK 无法完成请求或处理响应。"),
    "sdk_unavailable": ("The required SDK is unavailable.", "所需 SDK 不可用。"),
    "unexpected_destination": ("The request destination did not match the validated endpoint.", "请求目标与已校验的接入地址不一致。"),
    "incomplete_response": ("Qwen returned an incomplete or failed response.", "Qwen 返回不完整或失败的响应。"),
    "invalid_response_output": ("The response did not contain usable analysis output.", "响应未包含可用的分析输出。"),
    "sensitive_response": ("The response was rejected by the sensitive-content check.", "响应未通过敏感内容检查。"),
    "schema_validation_failed": ("The response did not match the analysis output schema.", "响应不符合分析输出结构。"),
    "business_validation_failed": ("The analysis violated a selection rule.", "分析未通过选项规则校验。"),
    "evidence_validation_failed": ("The analysis did not match the allowed financial evidence.", "分析未通过有效财务证据校验。"),
    "invalid_json": ("The model output was not valid JSON.", "模型输出不是有效的 JSON。"),
    "duplicate_json_key": ("The model output contained duplicate JSON keys.", "模型输出包含重复的 JSON 字段。"),
    "analysis_context_rejected": ("The current financial context could not be used for analysis.", "当前财务上下文无法用于分析。"),
    "analysis_storage_failed": ("The local analysis files could not be accessed.", "无法访问本地分析文件。"),
    "provider_failed": ("The model provider reported a failure.", "模型服务报告失败。"),
    "analysis_failed": ("The analysis could not be completed.", "分析未能完成。"),
}

_CODES = {
    "MATCHED": "匹配", "MISSING_PAYMENT": "缺少付款", "UNDERPAYMENT": "少付", "OVERPAYMENT": "多付",
    "DUPLICATE_PAYMENT": "重复付款", "PRICE_MISMATCH": "价格差异", "MISSING_CONTRACT": "缺少合同",
    "CONTRACT_OVERLAP": "合同重叠", "UNMATCHED_PAYMENT": "无对应业务付款", "INVALID_DATA": "无效数据",
    "REVIEW_REQUIRED": "须复核", "COMPLETED": "已完成", "INCOMPLETE_INPUT": "输入不完整",
    "COMPARABLE": "可比较", "HELD": "挂起", "UNMATCHED": "无对应业务",
    "HIGH": "高", "MEDIUM": "中", "LOW": "低",
}
_FIELDS_CN = {
    **FIELD_LABELS_CN, "contract_record_count": "合同记录数", "service_record_count": "业务记录数",
    "raw_payment_count": "付款原始记录数", "eligible_payment_count": "有效付款记录数",
    "service_date": "业务发生日期", "contract_id": "合同编号", "payment_id": "付款编号", "service_id": "业务编号",
    "test_type": "检测类型", "collection_type": "采集类型", "service_type": "服务类型", "billing_unit": "计费单位",
    "unit_price": "单价", "effective_date": "生效日期", "expiry_date": "到期日期", "quantity": "数量",
    "reported_amount": "报送金额", "payment_date": "付款日期", "payment_amount": "付款金额",
    "payment_reference": "付款参考号", "case_id": "样例编号", "expected_type": "预期类型", "expected_result": "预期结果",
    "contract": "合同", "service": "业务", "payment": "付款", "other": "其他", "amount": "金额", "value": "值",
    "tool": "工具", "call_id": "调用编号", "ref": "证据编号", "hospital_id": "医院编号",
}

EXAMPLES = {
    "summary": ("summary", "What is the overall comparable net difference?", "当前财务对账的总体净差额是多少？"),
    "hospital": ("hospital", "Show the May 2026 settlement status for SIM-H004.", "查询 SIM-H004 在 2026-05 的财务结算状态。"),
    "multi": ("multi", "List price mismatches and inspect the first result.", "查询价格差异异常及对应明细。"),
    "duplicate": ("knowledge", "How should duplicate payments be handled?", "发现重复付款记录时应该如何处理？"),
    "overlap": ("knowledge", "How should a contract overlap be handled?", "合同重叠应该如何处理？"),
    "combined": ("combined", "Why is the May 2026 settlement for SIM-H004 on hold, and what should the finance team do next?",
                 "SIM-H004 在 2026-05 的结算为何挂起，财务团队接下来应该怎么做？"),
}


def text(language: str, key: str) -> str:
    return _COPY[key][language == "cn"]


def field_label(language: str, key: str) -> str:
    if key in _COPY:
        return text(language, key)
    return _FIELDS_CN.get(key, key) if language == "cn" else key.replace("_", " ").capitalize()


def code_label(language: str, value: str) -> str:
    if value not in _CODES:
        return value
    return f"{_CODES[value]} · {value}" if language == "cn" else value.replace("_", " ").capitalize()


def chart_label(language: str, code: str) -> str:
    return _CODES.get(code, code) if language == "cn" else code_label(language, code)


def diagnostic_message(language: str, code: str) -> str:
    return DIAGNOSTIC_MESSAGES[code][language == "cn"] if code in DIAGNOSTIC_MESSAGES else text(language, code)


def example_text(language: str, choice: str) -> str:
    return EXAMPLES[choice][2 if language == "cn" else 1]
