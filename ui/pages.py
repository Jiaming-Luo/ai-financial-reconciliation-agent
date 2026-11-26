"""Dashboard, reconciliation, anomaly review, assistant and knowledge views."""

import json
from dataclasses import asdict
from decimal import Decimal
from textwrap import fill

import streamlit as st

from src.action_catalog import ACTION_CATALOG, eligible_actions
from src.agent import MAX_QUESTION_LENGTH
from src.context_builder import ContextError
from src.hypothesis_catalog import CATALOG
from src.knowledge_base import MAX_QUERY_LENGTH, KnowledgeBaseError, KnowledgeIndex
from src.llm_client import LLMError
from src.output_validator import OutputValidationError
from src.qwen_provider import DEFAULT_MODEL, QwenSettings
from src.tool_registry import ToolError
from ui import services
from ui.diagnostics import analysis_diagnostic
from ui.session import invalidate
from ui.text import EXAMPLES, LANGUAGES, chart_label, code_label, diagnostic_message, example_text, field_label, text


GROUP_FIELDS = ("hospital_id", "settlement_period", "settlement_status", "expected_amount", "paid_amount",
                "difference_amount", "eligible_paid_amount", "payment_bucket", "review_required")
AI_ERRORS = (LLMError, ContextError, OutputValidationError, ToolError, OSError)


def _error(lang: str, args: tuple) -> None:
    code, *files = args
    st.error(" · ".join((*files, text(lang, code))))


def _display(lang: str, value, field: str = "") -> str:
    if value is None or value == "":
        return text(lang, "unknown")
    if isinstance(value, bool) or field == "review_required" and value in ("true", "false"):
        return text(lang, "yes" if value is True or value == "true" else "no")
    if isinstance(value, (tuple, list)):
        return ", ".join(_display(lang, item) for item in value) or "—"
    return code_label(lang, value) if isinstance(value, str) else str(value)


def _table(lang: str, rows: list[dict], fields: tuple[str, ...] | None = None) -> None:
    if not rows:
        st.info(text(lang, "none"))
        return
    keys = fields or tuple(rows[0])
    st.dataframe([{field_label(lang, key): _display(lang, row.get(key), key) for key in keys} for row in rows[:200]],
                 hide_index=True, width="stretch")
    if len(rows) > 200:
        st.caption(text(lang, "preview_limit"))


def _values(lang: str, row: dict) -> None:
    st.dataframe([{text(lang, "category"): field_label(lang, key), field_label(lang, "value"): _display(lang, value, key)}
                  for key, value in row.items()], hide_index=True, width="stretch")


def _filters(lang: str, rows: list[dict], namespace: str, fields: tuple[str, ...]) -> list[dict]:
    selected = {}
    for col, field in zip(st.columns(len(fields)), fields):
        options = sorted({row.get(field, "") for row in rows}, key=lambda value: str(value))
        with col:
            selected[field] = st.selectbox(field_label(lang, field), [None, *options],
                                           format_func=lambda value, field=field: text(lang, "all") if value is None else _display(lang, value, field),
                                           key=f"{namespace}_{field}_{st.session_state.get('revision', 0)}")
    return [row for row in rows if all(value is None or row.get(field, "") == value for field, value in selected.items())]


def _bar(lang: str, label: str, counts: dict) -> None:
    st.subheader(text(lang, label))
    if counts:
        rows = [{"label": chart_label(lang, code), "code": code, "count": count} for code, count in counts.items()]
        st.vega_lite_chart(rows, {
            "mark": {"type": "bar", "color": "#285787"},
            "height": {"step": 27},
            "encoding": {
                "y": {"field": "label", "type": "nominal", "title": None, "axis": {"labelLimit": 0}},
                "x": {"field": "count", "type": "quantitative", "title": text(lang, "count"), "axis": {"tickMinStep": 1}},
                "tooltip": [{"field": key, "title": text(lang, caption), "type": kind}
                            for key, caption, kind in (("label", "category", "nominal"), ("code", "enum_code", "nominal"),
                                                       ("count", "count", "quantitative"))],
            },
        }, width="stretch")
    else:
        st.info(text(lang, "none"))


def _snapshot(lang: str) -> services.FinancialSnapshot | None:
    current = st.session_state.get("snapshot")
    if current is None:
        st.warning(text(lang, "finance_needed"))
    elif current.provisional:
        st.warning(text(lang, "provisional"))
    return current


def _metrics(lang: str, source: dict, fields: tuple[str, ...]) -> None:
    for column, key in zip(st.columns(len(fields)), fields):
        column.metric(field_label(lang, key), _display(lang, source.get(key)), border=True)


def _money_cards(lang: str, source: dict, fields: tuple[str, ...]) -> None:
    for column, key in zip(st.columns(len(fields)), fields):
        value = source.get(key)
        with column.container(border=True):
            st.caption(field_label(lang, key))
            st.markdown(f"**CNY {Decimal(value):,.2f}**" if value is not None else text(lang, "unknown"))


def dashboard(lang: str, _mode: str) -> None:
    snapshot = _snapshot(lang)
    if snapshot is None:
        return
    summary = snapshot.summary
    st.caption(text(lang, "full_run"))
    _metrics(lang, summary, ("settlement_group_count", "comparable_group_count", "anomalous_group_count", "held_group_count", "normal_group_count"))
    amounts = {} if snapshot.provisional else summary
    _money_cards(lang, amounts, ("comparable_receivable_amount", "comparable_paid_amount", "net_difference"))
    _money_cards(lang, amounts, ("held_eligible_payment_amount", "unmatched_payment_amount"))
    st.caption(text(lang, "scope_metrics"))
    first, second = st.tabs((text(lang, "anomaly_distribution"), text(lang, "status_distribution")))
    with first:
        _bar(lang, "anomaly_distribution", summary["anomaly_counts"])
    with second:
        _bar(lang, "status_distribution", summary["settlement_status_counts"])
    st.subheader(text(lang, "preview"))
    _table(lang, _filters(lang, snapshot.settlements, "dashboard", GROUP_FIELDS[:2]), GROUP_FIELDS)


def _upload_changed(name: str, widget_key: str) -> None:
    upload = st.session_state.get(widget_key)
    uploads = st.session_state["uploads"]
    errors = st.session_state["upload_errors"]
    uploads.pop(name, None)
    errors.pop(name, None)
    invalidate(st.session_state)
    if upload is not None:
        try:
            uploads[name] = services.safe_upload(upload.name, upload.getvalue())
        except services.AppInputError as error:
            errors[name] = str(error)


def _clear_uploads() -> None:
    st.session_state["uploads"] = {}
    st.session_state["upload_errors"] = {}
    st.session_state["upload_generation"] += 1
    invalidate(st.session_state)


def _preview_source(lang: str, name: str, payload: bytes) -> None:
    with st.expander(name):
        st.caption(text(lang, name))
        try:
            _table(lang, services.preview_csv(payload, name))
        except services.AppInputError as error:
            _error(lang, error.args)


def reconciliation(lang: str, _mode: str) -> None:
    samples = st.session_state["samples"]
    mode = st.radio(text(lang, "data_source"), ("sample", "upload"),
                    index=("sample", "upload").index(st.session_state["source_mode"]),
                    format_func=lambda item: text(lang, item), key="source_widget", horizontal=True,
                    on_change=_source_changed)
    with st.expander(text(lang, "sample_downloads")):
        for name, payload in samples.items():
            st.download_button(name, payload, file_name=name, mime="text/csv", key=f"sample_download_{name}", on_click="ignore")
    if mode == "upload":
        st.caption(text(lang, "upload_help"))
        st.button(text(lang, "clear_uploads"), on_click=_clear_uploads)
        for name, fields in services.SOURCE_FIELDS.items():
            key = f"upload_{name}_{st.session_state['upload_generation']}"
            st.file_uploader(f"{name} · {text(lang, name)}", type=["csv"], key=key,
                             on_change=_upload_changed, args=(name, key))
            st.caption(f"{text(lang, 'required_fields')} · " + ", ".join(fields))
            if error := st.session_state["upload_errors"].get(name):
                st.error(text(lang, error))
        files = st.session_state["uploads"]
        if files:
            st.caption(f"{text(lang, 'files_ready')} · {', '.join(files)}")
    else:
        files = samples
        for name, fields in services.SOURCE_FIELDS.items():
            st.caption(f"{name} · {text(lang, 'required_fields')} · {', '.join(fields)}")
    for name, content in files.items():
        _preview_source(lang, name, content)
    ready = services.SOURCE_FIELDS.keys() <= files.keys()
    if not ready:
        st.info(text(lang, "incomplete_upload") if mode == "upload" else text(lang, "sample_unavailable"))
    if st.button(text(lang, "run_finance"), type="primary", disabled=not ready, key="run_finance"):
        run_financial(files)
    if error := st.session_state.get("finance_error"):
        _error(lang, error)
    if snapshot := st.session_state.get("snapshot"):
        if snapshot.provisional:
            st.warning(text(lang, "provisional"))
        else:
            st.success(code_label(lang, snapshot.summary["run_status"]))
        _metrics(lang, snapshot.summary, ("contract_record_count", "service_record_count", "raw_payment_count", "eligible_payment_count"))
        st.subheader(text(lang, "preview"))
        _table(lang, _filters(lang, snapshot.settlements, "reconciliation", GROUP_FIELDS[:3]), GROUP_FIELDS)
        with st.expander(text(lang, "download_finance")):
            for name, payload in snapshot.files.items():
                st.download_button(name, payload, file_name=name, mime="application/json" if name.endswith(".json") else "text/csv",
                                   on_click="ignore")
    elif "finance_error" not in st.session_state:
        st.info(text(lang, "not_run"))


def _source_changed() -> None:
    st.session_state["source_mode"] = st.session_state["source_widget"]
    invalidate(st.session_state)


def run_financial(files: dict[str, bytes]) -> None:
    invalidate(st.session_state)
    try:
        st.session_state["snapshot"] = services.reconcile_files(files)
    except services.AppInputError as error:
        st.session_state["finance_error"] = error.args
    except ContextError:
        st.session_state["finance_error"] = ("finance_failed",)


def _credentials(lang: str, mode: str, namespace: str) -> tuple | None:
    if mode != "live":
        return None
    st.caption(text(lang, "live_notice"))
    base = st.text_input(text(lang, "base_url"), key=f"{namespace}_base", autocomplete="off")
    model = st.text_input(text(lang, "model"), value=DEFAULT_MODEL, key=f"{namespace}_model")
    key = st.text_input(text(lang, "api_key"), type="password", key=f"{namespace}_key", autocomplete="off")
    allowed = st.checkbox(text(lang, "live_confirm"), key=f"{namespace}_confirm")
    return base, model, key, allowed


def _settings(credentials: tuple | None) -> QwenSettings | None:
    if credentials is None:
        return None
    base, model, key, allowed = credentials
    if not allowed:
        raise services.AppInputError("live_needs_confirmation")
    try:
        return QwenSettings(model.strip(), key.strip(), base.strip(), max_retries=0)
    except LLMError:
        raise services.AppInputError("invalid_config") from None


def _finish_live_form(namespace: str) -> None:
    # A fresh widget identity discards submitted password and endpoint values from the session.
    key = f"{namespace}_generation"
    st.session_state[key] = st.session_state.get(key, 0) + 1
    st.rerun()


def _result_status(lang: str, result: dict, status: str, language_label: str, language: str) -> None:
    label = text(lang, status)
    display = st.error if status == "failed" else st.warning if status in ("insufficient_evidence", "refused", "completed_with_omissions") else st.success
    display(label)
    st.text(f"{text(lang, 'run_mode')} · {result['run_mode']}    {text(lang, 'model')} · {result.get('model') or '—'}    "
            f"{text(lang, language_label)} · {LANGUAGES[language]}")


def anomaly_review(lang: str, mode: str) -> None:
    snapshot = _snapshot(lang)
    if snapshot is None:
        return
    _bar(lang, "anomaly_distribution", snapshot.summary["anomaly_counts"])
    if not snapshot.provisional:
        form = f"analysis_{mode}_{st.session_state.get('analysis_generation', 0)}"
        with st.form(form, clear_on_submit=True, enter_to_submit=False):
            credentials = _credentials(lang, mode, form)
            submitted = st.form_submit_button(text(lang, "run_analysis"), type="primary")
        if submitted:
            # An earlier assistant answer may include priorities derived from this report.
            if "analysis" in st.session_state:
                for key in ("answer", "answer_error"):
                    st.session_state.pop(key, None)
            for key in ("analysis", "analysis_error", "analysis_diagnostic"):
                st.session_state.pop(key, None)
            try:
                st.session_state["analysis"] = services.analysis_report(snapshot, lang, _settings(credentials))
            except services.AppInputError as error:
                st.session_state["analysis_error"] = error.args
                st.session_state["analysis_diagnostic"] = analysis_diagnostic(error, live=mode == "live")
            except AI_ERRORS as error:
                st.session_state["analysis_error"] = ("ai_failed",)
                st.session_state["analysis_diagnostic"] = analysis_diagnostic(error, live=mode == "live")
            if mode == "live":
                _finish_live_form("analysis")
    report = st.session_state.get("analysis")
    findings = {item["anomaly_id"]: item for item in report["anomaly_findings"]} if report else {}
    with st.container(border=True):
        st.subheader(text(lang, "analysis_result"))
        if report:
            _result_status(lang, report, report["analysis_status"], "analysis_language", report["language"])
            json_report, markdown = services.analysis_downloads(report)
            with st.expander(text(lang, "download_analysis")):
                suffix = report["language"]
                st.download_button("JSON", json_report, file_name=f"ai_analysis_{suffix}.json", mime="application/json", on_click="ignore")
                st.download_button("Markdown", markdown, file_name=f"ai_analysis_{suffix}.md", mime="text/markdown", on_click="ignore")
        elif error := st.session_state.get("analysis_error"):
            _error(lang, error)
            if details := st.session_state.get("analysis_diagnostic"):
                _analysis_error_details(lang, details)
        else:
            st.caption(text(lang, "not_run"))
    rows = [{**row, "settlement_status": snapshot.findings[row["anomaly_id"]]["settlement_status"] or "",
             "business_priority": snapshot.priorities.get(row["anomaly_id"]),
             "ai_suggested_priority": findings.get(row["anomaly_id"], {}).get("priority")}
            for row in snapshot.anomalies]
    filtered = _filters(lang, rows, "anomaly", ("hospital_id", "settlement_period", "anomaly_type", "review_required"))
    _table(lang, filtered, ("anomaly_id", "anomaly_type", "hospital_id", "settlement_period", "settlement_status",
                            "business_priority", "ai_suggested_priority", "review_required"))
    if not filtered:
        return
    row_ids = {row["anomaly_id"]: row for row in filtered}
    selected = st.selectbox(text(lang, "review_select"), list(row_ids), key=f"review_selection_{st.session_state['revision']}")
    _anomaly_detail(lang, row_ids[selected], snapshot.findings[selected], findings.get(selected))


def _analysis_error_details(lang: str, details: dict) -> None:
    with st.expander(text(lang, "diagnostic")):
        display = {**details, "error_stage": text(lang, details["error_stage"])}
        allowed = display.pop("allowed_values", ())
        _values(lang, display)
        if allowed:
            st.caption(text(lang, "allowed_values"))
            st.markdown(", ".join(f"`{value}`" for value in allowed))
        st.caption(diagnostic_message(lang, details["error_code"]))


def _anomaly_detail(lang: str, row: dict, finding: dict, ai: dict | None) -> None:
    with st.container(border=True):
        st.subheader(f"{row['anomaly_id']} · {code_label(lang, row['anomaly_type'])}")
        st.caption(text(lang, "review"))
        left, right = st.columns(2)
        with left:
            st.subheader(text(lang, "anomaly_amounts"))
            _values(lang, finding["amounts"])
        with right:
            st.subheader(text(lang, "group_amounts"))
            _values(lang, finding["group_amounts"])
        st.subheader(text(lang, "records"))
        references = finding["reference_map"]
        _record_ids(lang, references.values())
        roles = {role: [references.get(ref, ref) for ref in refs] for role, refs in finding["review_evidence"].items() if refs}
        if roles:
            _evidence_roles(lang, roles)
        if ai:
            st.subheader(text(lang, "hypotheses"))
            for item in ai["possible_causes"]:
                _prose(CATALOG[item["cause_code"]].describe(lang))
        st.subheader(text(lang, "actions"))
        codes = [item["action_code"] for item in ai["recommended_actions"]] if ai else eligible_actions(
            row["anomaly_type"], finding["review_evidence"])
        for code in codes:
            _prose(ACTION_CATALOG[code].describe(lang))
        with st.expander(text(lang, "source_evidence")):
            st.json(json.loads(row["evidence"]))


def assistant(lang: str, mode: str) -> None:
    snapshot = _snapshot(lang)
    if snapshot is None or snapshot.provisional:
        return
    options = list(EXAMPLES) if mode == "mock" else ["custom", *EXAMPLES]
    selected = st.selectbox(text(lang, "example"), options, key=f"example_{mode}",
                            format_func=lambda item: text(lang, "custom") if item == "custom" else example_text(lang, item))
    initial = "" if selected == "custom" else example_text(lang, selected)
    form = f"assistant_{mode}_{st.session_state.get('assistant_generation', 0)}"
    with st.form(form, clear_on_submit=True, enter_to_submit=False):
        if mode == "live":
            question = st.text_area(text(lang, "question"), value=initial, max_chars=MAX_QUESTION_LENGTH,
                                    key=f"{form}_question_{selected}_{lang}")
        else:
            question = initial
            _prose(question)
        credentials = _credentials(lang, mode, form)
        submitted = st.form_submit_button(text(lang, "ask"), type="primary")
    if submitted:
        for key in ("answer", "answer_error"):
            st.session_state.pop(key, None)
        try:
            settings = _settings(credentials)
            if not question.strip() or len(question) > MAX_QUESTION_LENGTH:
                raise services.AppInputError("question_invalid")
            if settings and (settings.api_key in question or settings.base_url.split("/")[2] in question.lower()):
                raise services.AppInputError("credential_in_question")
            scenario = EXAMPLES[selected][0] if selected in EXAMPLES else "summary"
            result = services.answer_question(snapshot, lang, question.strip(), scenario, settings, st.session_state.get("analysis"))
            st.session_state["answer"] = (lang, result)
        except services.AppInputError as error:
            st.session_state["answer_error"] = error.args
        except AI_ERRORS:
            st.session_state["answer_error"] = ("ai_failed",)
        if mode == "live":
            _finish_live_form("assistant")
    st.subheader(text(lang, "assistant_result"))
    if error := st.session_state.get("answer_error"):
        _error(lang, error)
    elif answer := st.session_state.get("answer"):
        _render_answer(lang, *answer)
    else:
        st.info(text(lang, "not_run"))


def _prose(value: str) -> None:
    st.text("\n".join(fill(line, width=100, break_on_hyphens=False) for line in value.splitlines()))


def _record_ids(lang: str, references) -> None:
    st.text("\n".join(str(ref) for ref in references) or text(lang, "none"))


def _evidence_roles(lang: str, roles: dict) -> None:
    with st.expander(field_label(lang, "evidence_by_role")):
        for role, references in roles.items():
            st.caption(field_label(lang, role))
            _record_ids(lang, references)


def _passage(lang: str, match: dict, *, show_score: bool = False) -> None:
    with st.container(border=True):
        st.text(f"{match['document_title']} · {match['document_id']} §{match['section_id']} · v{match['version']} · {LANGUAGES[match['language']]}")
        st.text(f"{match['section_title']} · {match['source_file']}")
        st.text(f"{text(lang, 'scope')} · {match['scope']}")
        if show_score:
            st.text(f"{text(lang, 'score')} · {match['retrieval_score']:.3f}")
        st.caption(text(lang, "source_excerpt"))
        _prose(match["excerpt"])
        st.caption(text(lang, "guidance"))
        _prose(match["review_guidance"])


def _render_answer(lang: str, original_language: str, result: dict) -> None:
    status = result["status"]
    _result_status(lang, result, status, "answer_language", original_language)
    if status == "failed":
        st.caption(text(lang, "ai_failed"))
    st.caption(text(lang, "review"))
    requests_field = "mock_model_requests" if result["run_mode"] == "Mock" else "model_requests"
    _metrics(lang, {**result, requests_field: result["model_requests"], "total_tokens": (result.get("usage") or {}).get("total_tokens")},
             (requests_field, "tool_calls", "total_tokens", "elapsed_seconds"))
    for section in result["answer_sections"]:
        knowledge = section.get("evidence_type") == "knowledge"
        label = "knowledge_evidence" if knowledge else "financial_evidence"
        with st.container(border=True):
            st.subheader(f"{section['ref']} · {text(lang, label)}")
            st.text(f"{section['tool']} · {text(lang, 'files')} · {', '.join(section['source_files'])}")
            if knowledge:
                for match in section["data"]["matches"]:
                    _passage(lang, match)
                st.caption(text(lang, "prototype"))
            else:
                _financial_section(lang, section["data"])
    if not any(s.get("evidence_type") == "knowledge" for s in result["answer_sections"]) and any(
        entry["name"] == "search_business_knowledge" and entry.get("result", {}).get("status") == "not_found"
        for entry in result["tool_trace"]
    ):
        st.warning(text(lang, "insufficient_evidence"))
    with st.expander(text(lang, "tools")):
        if result["tool_trace"]:
            _table(lang, [{"tool": row["name"], "call_id": row["call_id"], "model_requests": row["model_request"],
                          "ref": row.get("result", {}).get("ref") or row.get("result", {}).get("status")}
                         for row in result["tool_trace"]])
        st.json(result["tool_trace"])
    with st.expander(text(lang, "technical")):
        st.json(result)


def _financial_section(lang: str, data: dict) -> None:
    plain = {key: value for key, value in data.items() if not isinstance(value, (dict, list))}
    if plain:
        _values(lang, plain)
    for key, value in data.items():
        if key == "evidence_by_role" and value:
            _evidence_roles(lang, value)
        elif key == "related_record_ids" and value:
            st.caption(field_label(lang, key))
            _record_ids(lang, value)
        elif isinstance(value, dict) and value:
            st.caption(field_label(lang, key))
            _values(lang, value)
        elif isinstance(value, list) and value:
            st.caption(field_label(lang, key))
            if isinstance(value[0], dict):
                _table(lang, value)
            else:
                _prose(", ".join(_display(lang, item) for item in value))


def knowledge_base(lang: str, _mode: str) -> None:
    st.caption(text(lang, "kb_notice"))
    try:
        index = st.session_state.get("knowledge_index")
        if index is None:
            index = KnowledgeIndex.load(services.ROOT / "knowledge_base")
            st.session_state["knowledge_index"] = index
    except KnowledgeBaseError:
        st.error(text(lang, "kb_failed"))
        return
    language = st.selectbox(text(lang, "doc_language"), list(LANGUAGES), format_func=LANGUAGES.__getitem__,
                            index=list(LANGUAGES).index(lang), key=f"kb_lang_{lang}")
    query = st.text_input(text(lang, "keywords"), max_chars=MAX_QUERY_LENGTH, key="kb_query")
    if query.strip():
        try:
            hits = index.search(query, language=language)
        except KnowledgeBaseError:
            st.error(text(lang, "kb_invalid"))
            return
        if not hits:
            st.info(text(lang, "insufficient_evidence"))
        for hit in hits:
            _passage(lang, {**asdict(hit.chunk), "retrieval_score": hit.score}, show_score=True)
    st.subheader(text(lang, "catalog"))
    docs = {chunk.document_id: chunk.document_title for chunk in index.chunks if chunk.language == language}
    selected = st.selectbox(text(lang, "document"), list(docs), format_func=lambda key: f"{key} · {docs[key]}", key=f"kb_doc_{language}")
    for chunk in index.chunks:
        if chunk.language == language and chunk.document_id == selected:
            _passage(lang, asdict(chunk))


VIEWS = {"dashboard": dashboard, "reconciliation": reconciliation, "anomalies": anomaly_review,
         "assistant": assistant, "knowledge": knowledge_base}
