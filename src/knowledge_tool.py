"""Read-only tool adapter for the business knowledge retriever."""

from collections.abc import Callable
from dataclasses import asdict
from functools import cached_property

from .knowledge_base import DEFAULT_TOP_K, KnowledgeBaseError, KnowledgeRetriever
from .tool_registry import RecordNotFound, ToolError


class KnowledgeTool:
    def __init__(self, load_retriever: Callable[[], KnowledgeRetriever], language: str):
        self._load_retriever = load_retriever
        self.language = language

    @cached_property
    def retriever(self) -> KnowledgeRetriever:
        return self._load_retriever()

    def search(self, query: str, top_k: int = DEFAULT_TOP_K, language: str | None = None) -> dict:
        try:
            retriever = self.retriever
        except KnowledgeBaseError:
            raise RecordNotFound("The local business knowledge index is unavailable.") from None
        try:
            hits = retriever.search(query, top_k=top_k, language=self.language if language is None else language)
        except KnowledgeBaseError:
            raise ToolError("Invalid business knowledge search arguments.") from None
        if not hits:
            raise RecordNotFound("No sufficiently relevant business knowledge was found.")
        matches = []
        for hit in hits:
            row = asdict(hit.chunk)
            row["source_file"] = f"knowledge_base/{hit.chunk.source_file}"
            matches.append({**row, "retrieval_score": round(hit.score, 6)})
        return {"source_files": list(dict.fromkeys(row["source_file"] for row in matches)),
                "data": {"matches": matches, "simulation": True, "review_required": True}}
