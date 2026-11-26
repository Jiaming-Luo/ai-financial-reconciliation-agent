"""Explicitly verify Qwen connectivity or synthetic structured analysis."""

import argparse
import json
import os
import sys
import warnings
from dataclasses import replace
from getpass import GetPassWarning, getpass
from pathlib import Path
from time import perf_counter


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if not __package__:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.context_builder import ContextError, build_context
from src.llm_analyzer import analyze, write_analysis
from src.llm_client import LLMError
from src.output_validator import OutputValidationError
from src.qwen_provider import QwenProvider, QwenSettings


def _prompt_key() -> str:
    if not sys.stdin.isatty() or not sys.stderr.isatty():
        raise LLMError("Hidden input requires an interactive terminal. Set DASHSCOPE_API_KEY in the process instead.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", GetPassWarning)
            return getpass("Alibaba Cloud Model Studio API key (hidden): ").strip()
    except (GetPassWarning, EOFError, OSError):
        raise LLMError("Hidden API key input was unavailable. No request was sent.") from None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", required=True, help="Explicitly permit one live request.")
    parser.add_argument("--prompt-key", action="store_true", help="Use hidden input even if a key is set.")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--mode", choices=("connection", "single", "full", "report"),
                       help="Select connectivity, a single finding, all findings, or saved reports.")
    modes.add_argument("--structured", dest="mode", action="store_const", const="full",
                       help="Alias for --mode full.")
    parser.add_argument("--input-dir", type=Path, default=PROJECT_ROOT / "outputs")
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "outputs" / "qwen-verification",
                        help="Destination for JSON and Markdown in report mode.")
    parser.add_argument("--language", choices=("en", "cn"), default="en")
    args = parser.parse_args(argv)

    try:
        mode = args.mode or "connection"
        context = build_context(args.input_dir) if mode != "connection" else None
        if mode == "single":
            first = next(iter(context.findings.items()), None)
            if first is None:
                raise ContextError("Single-finding verification requires at least one finding in the input reports.")
            finding_id, finding = first
            context = replace(context, findings={finding_id: finding})
        if mode in ("full", "report") and not context.findings:
            raise ContextError("Full or report verification requires at least one finding in the input reports.")
        env = {
            option: os.environ[option] for option in
            ("QWEN_BASE_URL", "QWEN_MODEL", "LLM_TIMEOUT", "LLM_MAX_RETRIES") if option in os.environ
        }
        if not env.get("QWEN_BASE_URL", "").strip():
            raise LLMError("Set QWEN_BASE_URL for the region or workspace associated with the key.")
        key = "" if args.prompt_key else os.environ.get("DASHSCOPE_API_KEY", "").strip()
        env["DASHSCOPE_API_KEY"] = key or _prompt_key()
        provider = QwenProvider(replace(QwenSettings.from_env(env), max_retries=0))

        started = perf_counter()
        if context is None:
            result = provider.probe()
            model, usage = result.model, result.usage
        else:
            report = analyze(context, provider, args.language)
            model, usage = report["model"], report.get("usage")
            if mode == "report":
                write_analysis(report, args.output_dir)
        metadata = {
            "model": model,
            "status": report["analysis_status"] if context is not None else "completed",
            "usage": usage,
            "elapsed_seconds": round(perf_counter() - started, 3),
        }
        if args.mode is not None:
            metadata["verification_scope"] = mode
            metadata["finding_count"] = len(context.findings) if context is not None else 0
            metadata["reports_written"] = mode == "report"
            if context is not None:
                metadata["validated_cause_count"] = sum(
                    len(finding["possible_causes"]) for finding in report["anomaly_findings"]
                )
                metadata["validated_action_count"] = sum(
                    len(finding["recommended_actions"]) for finding in report["anomaly_findings"]
                )
                metadata["core_validation"] = report["core_validation"]
                metadata["omitted_note_count"] = len(report["warnings"])
                metadata["warnings"] = report["warnings"]
                metadata["report_schema_version"] = report["report_schema_version"]
        print(json.dumps(metadata))
    except (ContextError, LLMError, OutputValidationError) as error:
        print(f"Qwen verification failed: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Qwen verification interrupted.", file=sys.stderr)
        return 130
    except OSError:
        print("Qwen verification could not write the analysis reports.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
