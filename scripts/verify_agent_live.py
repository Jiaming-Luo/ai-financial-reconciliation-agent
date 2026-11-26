"""Explicitly run one Qwen Agent acceptance scenario and report its evidence."""

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if not __package__:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent_cli import build_registry, live_provider
from src.agent import HOSPITAL_ANSWER_FIELDS, HOSPITAL_TOOL, AgentError, run_agent
from src.context_builder import ContextError
from src.llm_client import LLMError
from src.tool_registry import ToolError


HOSPITAL_SCOPE = {"hospital_id": "SIM-H004", "settlement_period": "2026-05"}

QUESTIONS = {
    "summary": {
        "en": "What are the comparable net difference and number of held groups in the overall portfolio?",
        "cn": "总体可比较净差额和挂起结算组数分别是多少？",
    },
    "hospital": {
        "en": "For hospital SIM-H004 in settlement period 2026-05, show the settlement status, amounts, and any linked anomalies.",
        "cn": "请查询医院 SIM-H004 在结算期 2026-05 的结算状态、金额及关联异常。",
    },
    "multi": {
        "en": "List price mismatch anomalies, then look up the first returned anomaly for its amounts and review actions. Cite the list and detail results.",
        "cn": "先列出价格差异异常，再用列表第一条编号查询金额和核查建议。请同时引用列表及明细结果。",
    },
}


def _hospital_failures(sections: dict, tool_trace: list[dict]) -> list[dict]:
    lookups = [event for event in tool_trace if event["name"] == HOSPITAL_TOOL]
    scoped = [event for event in lookups if event["arguments"] == HOSPITAL_SCOPE]
    if lookups and not scoped:
        return [{"code": "incorrect_hospital_scope", "message": "Incorrect hospital or settlement period."}]
    successful = [event["result"] for event in scoped if event.get("result", {}).get("status") == "ok"]
    if not successful:
        return [{"code": "missing_hospital_tool_result", "message": "Missing successful hospital reconciliation tool result."}]
    if not any(source["ref"] in sections for source in successful):
        return [{"code": "missing_evidence_reference", "message": "Missing citation to the requested hospital reconciliation result."}]

    # The Agent prevents repeating the same tool call with the same arguments.
    source = next(source for source in successful if source["ref"] in sections)
    section = sections[source["ref"]]
    financial, answer = source["data"], section["data"]
    failures = []
    if (section["tool"] != HOSPITAL_TOOL or section["arguments"] != HOSPITAL_SCOPE
            or any(financial.get(field) != value for field, value in HOSPITAL_SCOPE.items())):
        failures.append({"code": "incorrect_hospital_scope", "message": "Incorrect hospital or settlement period in cited evidence."})
    for data, code, message in (
        (financial, "incomplete_tool_evidence", "Hospital tool evidence is missing required fields."),
        (answer, "missing_required_answer_field", "Missing required hospital answer fields."),
    ):
        missing = [field for field in HOSPITAL_ANSWER_FIELDS if field not in data]
        if missing:
            failures.append({"code": code, "message": message, "fields": missing})
    mismatched = [field for field in HOSPITAL_ANSWER_FIELDS if field in financial and field in answer
                  and (type(answer[field]) is not type(financial[field]) or answer[field] != financial[field])]
    if mismatched:
        failures.append({"code": "answer_evidence_mismatch", "message": "Hospital answer values differ from cited evidence.",
                         "fields": mismatched})
    return failures


def _summary_or_multi_accepted(scenario: str, sections: dict, tool_trace: list[dict]) -> bool:
    cited = [event for event in tool_trace if event.get("result", {}).get("ref") in sections]
    if scenario == "summary":
        return any(
            event["name"] == "get_reconciliation_summary"
            and {"net_difference", "held_group_count"} <= sections[event["result"]["ref"]]["data"].keys()
            and sections[event["result"]["ref"]]["data"]["net_difference"] is not None
            for event in cited
        )
    for event in cited:
        if event["name"] != "list_anomalies" or event["arguments"].get("anomaly_type") != "PRICE_MISMATCH":
            continue
        rows = sections[event["result"]["ref"]]["data"].get("anomalies", [])
        if not rows:
            continue
        if any(
            detail["name"] == "get_anomaly_details"
            and detail["model_request"] > event["model_request"]
            and detail["arguments"]["anomaly_id"] == rows[0]["anomaly_id"]
            and {"amounts", "manual_review_actions"} <= sections[detail["result"]["ref"]]["data"].keys()
            for detail in cited
        ):
            return True
    return False


def verification_failures(scenario: str, result: dict) -> list[dict]:
    if result["run_mode"] != "Live":
        return [{"code": "not_live", "message": "Verification requires a Live run."}]
    if result["status"] != "answered":
        failure = {"code": "not_answered", "message": "The Agent did not produce a verified answer."}
        if result.get("error_details"):
            failure["cause"] = result["error_details"]
        return [failure]
    sections = {entry["ref"]: entry for entry in result["answer_sections"]}
    trace = result["tool_trace"]
    if scenario == "hospital":
        return _hospital_failures(sections, trace)
    if _summary_or_multi_accepted(scenario, sections, trace):
        return []
    return [{"code": "scenario_evidence_missing", "message": "The answer did not meet the scenario evidence requirements."}]


def accepted(scenario: str, result: dict) -> bool:
    return not verification_failures(scenario, result)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", required=True, help="Explicitly permit Qwen requests.")
    parser.add_argument("--prompt-key", action="store_true", help="Read the key with hidden terminal input.")
    parser.add_argument("--scenario", choices=tuple(QUESTIONS), required=True)
    parser.add_argument("--language", choices=("en", "cn"), default="en")
    parser.add_argument("--input-dir", type=Path, default=PROJECT_ROOT / "outputs")
    args = parser.parse_args(argv)
    try:
        registry = build_registry(args.input_dir, args.language)
        result = run_agent(QUESTIONS[args.scenario][args.language], args.language, live_provider(args.prompt_key), registry)
    except (AgentError, ContextError, LLMError, ToolError) as error:
        print(f"Agent verification setup failed: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130

    failures = verification_failures(args.scenario, result)
    passed = not failures
    print(json.dumps({"scenario": args.scenario, "verification": "PASS" if passed else "FAIL",
                      "verification_failures": failures, **result},
                     ensure_ascii=False, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
