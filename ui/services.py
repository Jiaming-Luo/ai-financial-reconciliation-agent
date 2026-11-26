"""Use the frozen services with per-operation files and in-memory session snapshots."""

import csv
import io
import json
from contextlib import contextmanager
from dataclasses import dataclass
from itertools import islice
from pathlib import Path
from tempfile import TemporaryDirectory

from agent_cli import build_registry
from src.agent import MockAgentProvider, QwenAgentProvider, run_agent
from src.agent_tools import AgentTools
from src.context_builder import SOURCE_FILES, build_context
from src.data_loader import CONTRACT_FIELDS, PAYMENT_FIELDS, SERVICE_FIELDS, DataLoadError, load_data
from src.llm_analyzer import analyze, render_markdown
from src.llm_client import MockProvider
from src.qwen_provider import QwenProvider, QwenSettings
from src.reconciliation import reconcile
from src.reporting import write_reports


ROOT = Path(__file__).resolve().parents[1]
SAMPLE_ROOT = ROOT / "data" / "sample"
SOURCE_FIELDS = {"contracts.csv": CONTRACT_FIELDS, "service_records.csv": SERVICE_FIELDS, "payments.csv": PAYMENT_FIELDS}
ORACLE = "expected_anomalies.csv"
MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_ROWS = 10_000
_IDENTIFIER_FIELDS = {"contract_id", "service_id", "payment_id", "hospital_id", "payment_reference"}


class AppInputError(ValueError):
    """A short UI message key without source values or machine paths."""


@dataclass
class FinancialSnapshot:
    summary: dict
    settlements: list[dict]
    anomalies: list[dict]
    findings: dict[str, dict]
    priorities: dict[str, str]
    files: dict[str, bytes]

    @property
    def provisional(self) -> bool:
        return self.summary["run_status"] == "INCOMPLETE_INPUT"


def sample_files() -> dict[str, bytes]:
    try:
        return {name: (SAMPLE_ROOT / name).read_bytes() for name in (*SOURCE_FIELDS, ORACLE)}
    except OSError:
        raise AppInputError("sample_unavailable") from None


def safe_upload(filename: str, payload: bytes) -> bytes:
    if (not filename.lower().endswith(".csv") or any(char in filename for char in "/\\:")
            or not filename.isprintable()):
        raise AppInputError("invalid_file_type")
    if not payload or len(payload) > MAX_FILE_BYTES:
        raise AppInputError("invalid_file_size")
    return payload


def _csv_text(payload: bytes) -> io.StringIO:
    if not payload or len(payload) > MAX_FILE_BYTES:
        raise AppInputError("invalid_file_size")
    if b"\0" in payload:
        raise AppInputError("invalid_csv")
    return io.StringIO(payload.decode("utf-8-sig"), newline="")


def preview_csv(payload: bytes, name: str, *, validate: bool = False) -> list[dict]:
    try:
        reader = csv.DictReader(_csv_text(payload), strict=True)
        fields = SOURCE_FIELDS.get(name)
        if fields and (len(reader.fieldnames or ()) != len(fields) or set(reader.fieldnames or ()) != set(fields)):
            raise AppInputError("invalid_header")
        preview = []
        for index, row in enumerate(reader if validate else islice(reader, 8)):
            if index >= MAX_ROWS:
                raise AppInputError("too_many_rows")
            if None in row:
                raise AppInputError("invalid_csv")
            if validate and any((row.get(key) or "").lstrip().startswith(("=", "+", "-", "@"))
                                for key in _IDENTIFIER_FIELDS):
                raise AppInputError("invalid_identifier")
            if index < 8:
                preview.append(row)
        return preview
    except (UnicodeError, csv.Error):
        raise AppInputError("invalid_csv") from None


@contextmanager
def _operation_dir():
    parent = ROOT / "outputs"
    parent.mkdir(exist_ok=True)
    if parent.resolve() != parent:
        raise AppInputError("workspace_error")
    with TemporaryDirectory(prefix="streamlit-run-", dir=parent) as folder:
        yield Path(folder)


def reconcile_files(files: dict[str, bytes]) -> FinancialSnapshot:
    if not SOURCE_FIELDS.keys() <= files.keys():
        raise AppInputError("incomplete_upload")
    for name in SOURCE_FIELDS:
        try:
            preview_csv(files[name], name, validate=True)
        except AppInputError as error:
            raise AppInputError(str(error), name) from None
    try:
        with _operation_dir() as folder:
            inputs = folder / "source"
            inputs.mkdir()
            for name in SOURCE_FIELDS:
                (inputs / name).write_bytes(files[name])
            summary = write_reports(reconcile(load_data(inputs)), folder)
            reports = {name: (folder / name).read_bytes() for name in SOURCE_FILES}
            settlements = list(csv.DictReader(io.StringIO(reports["reconciliation_results.csv"].decode())))
            anomalies = list(csv.DictReader(io.StringIO(reports["anomaly_details.csv"].decode())))
            tools = AgentTools(folder, "en")
            rows = tools.get_review_priorities(limit=len(anomalies))["data"]["priorities"]
            priorities = {row["anomaly_id"]: row["business_priority"] for row in rows}
    except (DataLoadError, OSError):
        raise AppInputError("finance_failed") from None
    return FinancialSnapshot(summary, settlements, anomalies, tools.context.findings, priorities, reports)


def _hydrate(snapshot: FinancialSnapshot, folder: Path) -> None:
    if snapshot.provisional:
        raise AppInputError("provisional_ai_block")
    for name in SOURCE_FILES:
        (folder / name).write_bytes(snapshot.files[name])


def analysis_report(snapshot: FinancialSnapshot, language: str, settings: QwenSettings | None = None) -> dict:
    with _operation_dir() as folder:
        _hydrate(snapshot, folder)
        return analyze(build_context(folder), QwenProvider(settings) if settings else MockProvider(), language)


def answer_question(snapshot: FinancialSnapshot, language: str, question: str, scenario: str,
                    settings: QwenSettings | None = None, report: dict | None = None) -> dict:
    with _operation_dir() as folder:
        _hydrate(snapshot, folder)
        # The existing registry revalidates optional priorities against this run's evidence.
        if report and report["language"] == language:
            (folder / f"ai_analysis_{language}.json").write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
        registry = build_registry(folder, language, folder if report and report["language"] == language else None)
        provider = QwenAgentProvider(settings) if settings else MockAgentProvider(scenario)
        return run_agent(question, language, provider, registry)


def analysis_downloads(report: dict) -> tuple[str, str]:
    return json.dumps(report, ensure_ascii=False, indent=2) + "\n", render_markdown(report)
