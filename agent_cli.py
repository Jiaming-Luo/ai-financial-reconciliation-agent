"""Ask one read-only financial question or run a scripted Mock demonstration."""

import argparse
import json
import os
import sys
from pathlib import Path

from scripts.verify_qwen_live import _prompt_key
from src.agent import MOCK_SCENARIOS, AgentError, MockAgentProvider, QwenAgentProvider, render_answer, run_agent
from src.agent_prompts import TEXT
from src.agent_tools import AgentTools
from src.context_builder import ContextError
from src.knowledge_base import KnowledgeIndex
from src.knowledge_tool import KnowledgeTool
from src.llm_client import LLMError
from src.qwen_provider import QwenSettings
from src.tool_registry import ToolError, ToolRegistry


PROJECT_ROOT = Path(__file__).resolve().parent


def live_provider(prompt_key: bool) -> QwenAgentProvider:
    env = {name: os.environ[name] for name in ("QWEN_BASE_URL", "QWEN_MODEL", "LLM_TIMEOUT", "LLM_MAX_RETRIES")
           if name in os.environ}
    if not env.get("QWEN_BASE_URL", "").strip():
        raise LLMError("Set QWEN_BASE_URL for the region or workspace associated with the key.")
    key = "" if prompt_key else os.environ.get("DASHSCOPE_API_KEY", "").strip()
    env["DASHSCOPE_API_KEY"] = key or _prompt_key()
    return QwenAgentProvider(QwenSettings.from_env(env))


def build_registry(input_dir: Path, language: str, analysis_dir: Path | None = None) -> ToolRegistry:
    tools = AgentTools(input_dir, language, analysis_dir)
    knowledge = KnowledgeTool(lambda: KnowledgeIndex.load(PROJECT_ROOT / "knowledge_base"), language)
    return ToolRegistry(tools, knowledge_search=knowledge.search)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("question", help="One question in English or Simplified Chinese.")
    parser.add_argument("--provider", choices=("mock", "qwen"), default="mock")
    parser.add_argument("--live", action="store_true", help="Explicitly permit Qwen requests.")
    parser.add_argument("--prompt-key", action="store_true", help="Read the Qwen key with hidden terminal input.")
    parser.add_argument("--language", choices=("en", "cn"), default="en")
    parser.add_argument("--input-dir", type=Path, default=PROJECT_ROOT / "outputs")
    parser.add_argument("--analysis-dir", type=Path, help="Optional directory containing a matching v3 analysis JSON.")
    parser.add_argument("--mock-scenario", choices=MOCK_SCENARIOS, default="summary")
    parser.add_argument("--json", action="store_true", help="Print the structured answer, usage and tool trace.")
    args = parser.parse_args(argv)
    if args.live != (args.provider == "qwen"):
        parser.error("--live and --provider qwen must be used together.")
    if args.prompt_key and not args.live:
        parser.error("--prompt-key is available only in explicit Live mode.")

    try:
        registry = build_registry(args.input_dir, args.language, args.analysis_dir)
        provider = live_provider(args.prompt_key) if args.live else MockAgentProvider(args.mock_scenario)
        result = run_agent(args.question, args.language, provider, registry)
    except (AgentError, ContextError, LLMError, ToolError) as error:
        print(f"Agent setup failed: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        labels = TEXT[args.language]
        print(render_answer(result, args.language))
        print(f"\n{labels['tools']}")
        for event in result["tool_trace"]:
            data = event.get("result", {})
            print(f"- {event['name']} {json.dumps(event['arguments'], ensure_ascii=False)} "
                  f"· {event['call_id']} · {data.get('ref', data.get('status', 'stopped'))}")
        print(f"\n{labels['metrics']} · {json.dumps({key: result[key] for key in ('model', 'run_mode', 'model_requests', 'tool_calls', 'usage', 'elapsed_seconds')})}")
    return 1 if result["status"] == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
