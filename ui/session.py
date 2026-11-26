"""Session boundaries for financial results and derived AI evidence."""

from collections.abc import MutableMapping


def invalidate(state: MutableMapping) -> None:
    for key in ("snapshot", "finance_error", "analysis", "analysis_error", "analysis_diagnostic", "answer", "answer_error"):
        state.pop(key, None)
    state["revision"] = state.get("revision", 0) + 1
