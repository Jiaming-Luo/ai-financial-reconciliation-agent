"""Load versioned Markdown sections and rank them with local BM25."""

import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


LANGUAGES = ("en", "cn")
DEFAULT_TOP_K = 3
MAX_TOP_K = 5
MAX_QUERY_LENGTH = 320
MAX_DOCUMENT_BYTES = 24_000
MAX_SECTION_BYTES = 1_400
MAX_CHUNKS = 128
_K1 = 1.5
_B = 0.75
_TOKEN = re.compile(r"[a-z0-9]+|[\u3400-\u9fff]+")
_HEADING = re.compile(r"(?m)^## ([1-9][0-9]{0,2})\. ([^\r\n]+)\n")
_STOP = frozenset("a an and are as at be can do does did for from has have how i in is it may of on or should the to was what when where which who why will with would you".split())
_TOPICS = {
    "contract_overlap": ("contract overlap", "overlapping contracts", "version conflict", "contract conflict", "合同重叠", "版本冲突", "合同冲突"),
    "duplicate_payment": ("duplicate payment", "duplicated payment", "duplicate receipt", "repeated payment reference", "重复付款", "重复收款", "重复支付"),
    "missing_contract": ("missing contract", "no active contract", "合同缺失", "无有效合同", "缺少合同"),
    "price_mismatch": ("price mismatch", "pricing discrepancy", "申报价差", "价格差异", "定价不一致"),
    "missing_payment": ("missing payment", "missing receipt", "no receipt", "付款缺失", "未付款", "缺少收款"),
    "unmatched_payment": ("unmatched payment", "no service rows", "无对应业务付款", "无业务行"),
    "underpayment": ("underpayment", "short payment", "少付"),
    "overpayment": ("overpayment", "excess payment", "多付"),
    "invalid_data": ("invalid data", "invalid input", "无效数据", "无效输入"),
    "effective_dates": ("effective date", "inclusive date", "date boundary", "生效日", "有效期", "到期日"),
    "payment_reference": ("payment reference", "transaction reference", "付款参考号", "交易参考号"),
    "settlement_hold": ("held settlement", "settlement hold", "on hold", "review required", "结算挂起", "挂起结算", "挂起组"),
    "human_review": ("human review", "manual review", "escalation", "人工复核", "异常升级"),
    "billing_unit": ("billing unit", "contractual unit", "计费单位", "合同单位"),
    "settlement_period": ("settlement month", "settlement period", "结算月", "结算期"),
}
_ALIASES = {
    key: re.compile(r"(?<![a-z0-9])(?:" + "|".join(re.escape(term) for term in terms) + r")(?![a-z0-9])")
    for key, terms in _TOPICS.items()
}


class KnowledgeBaseError(ValueError):
    """A safe corpus or search validation error."""


def normalize(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).casefold().replace("_", " ").replace("-", " ").split())


def _terms(text: str) -> list[str]:
    normalized = normalize(text)
    raw = _TOKEN.findall(normalized)
    terms = []
    for token in raw:
        if token.isascii():
            if token not in _STOP and not token.isdecimal():
                terms.append(token)
        else:
            terms.extend(token[i:i + 2] for i in range(len(token) - 1))
    terms.extend(f"topic:{key}" for key, pattern in _ALIASES.items() if pattern.search(normalized))
    return terms


@dataclass(frozen=True)
class KnowledgeChunk:
    document_id: str
    document_title: str
    section_id: str
    section_title: str
    version: str
    language: str
    scope: str
    source_file: str
    excerpt: str
    review_guidance: str


@dataclass(frozen=True)
class KnowledgeHit:
    chunk: KnowledgeChunk
    score: float


class KnowledgeRetriever(Protocol):
    def search(self, query: str, *, language: str, top_k: int = DEFAULT_TOP_K) -> list[KnowledgeHit]: ...


def _load_document(file: Path) -> list[KnowledgeChunk]:
    if file.is_symlink() or file.resolve() != file or not file.is_file():
        raise KnowledgeBaseError("The knowledge corpus contains an invalid Markdown source.")
    try:
        with file.open("rb") as stream:
            raw = stream.read(MAX_DOCUMENT_BYTES + 1)
        text = raw.decode("utf-8").replace("\r\n", "\n")
    except (OSError, UnicodeError):
        raise KnowledgeBaseError("A knowledge document could not be read as UTF-8.") from None
    if len(raw) > MAX_DOCUMENT_BYTES or any(not ch.isprintable() and ch not in "\n\t" for ch in text):
        raise KnowledgeBaseError("A knowledge document exceeds its bounds or contains control characters.")
    headings = list(_HEADING.finditer(text))
    if not headings:
        raise KnowledgeBaseError("A knowledge document has no numbered sections.")
    header = text[:headings[0].start()].splitlines()
    meta = {}
    for line in header[1:]:
        if ": " in line and not line.startswith(">"):
            key, value = line.split(": ", 1)
            if key in meta:
                raise KnowledgeBaseError("A knowledge document repeats metadata.")
            meta[key] = value.strip()
    if (not header[0].startswith("# ") or not header[0][2:].strip()
            or set(meta) != {"Document ID", "Version", "Language", "Scope", "Status"}
            or not re.fullmatch(r"KB-[0-9]{2,4}", meta["Document ID"])
            or not re.fullmatch(r"[0-9]{1,3}\.[0-9]{1,3}", meta["Version"])
            or meta["Language"] not in LANGUAGES or meta["Status"] != "SIMULATION" or not meta["Scope"]
            or not any(line.startswith("> ") for line in header)
            or len(file.name.encode("utf-8")) > 96):
        raise KnowledgeBaseError("A knowledge document has invalid simulation metadata.")
    chunks, ids = [], set()
    for index, heading in enumerate(headings):
        section_id, section_title = heading.groups()
        end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        body = text[heading.end():end].strip()
        excerpt, separator, advice = body.rpartition("\nReview guidance: ")
        if (section_id in ids or not section_title.strip() or not separator or not excerpt.strip() or not advice.strip()
                or "\n" in advice or len((header[0] + meta["Scope"] + section_title + body).encode()) > MAX_SECTION_BYTES):
            raise KnowledgeBaseError("A knowledge section has duplicate IDs, invalid guidance, or exceeds its size limit.")
        ids.add(section_id)
        chunks.append(KnowledgeChunk(meta["Document ID"], header[0][2:].strip(), section_id, section_title.strip(),
                                     meta["Version"], meta["Language"], meta["Scope"], file.name,
                                     excerpt.strip(), advice.strip()))
    return chunks


class KnowledgeIndex:
    """An in-memory, language-specific BM25 index over bounded source sections."""

    @classmethod
    def load(cls, directory: Path) -> "KnowledgeIndex":
        try:
            root = directory.resolve()
            if root != directory.absolute():
                raise KnowledgeBaseError("The knowledge corpus directory must not redirect to another location.")
            files = sorted(root.glob("*.md"))
        except OSError:
            raise KnowledgeBaseError("The knowledge corpus could not be opened.") from None
        if not 1 <= len(files) <= MAX_CHUNKS:
            raise KnowledgeBaseError("The knowledge corpus has no Markdown documents or exceeds its size limit.")
        chunks, documents = [], set()
        for file in files:
            sections = _load_document(file)
            pair = sections[0].document_id, sections[0].language
            if pair in documents or len(chunks) + len(sections) > MAX_CHUNKS:
                raise KnowledgeBaseError("The knowledge corpus has duplicate document versions or too many sections.")
            documents.add(pair)
            chunks.extend(sections)
        return cls(tuple(chunks))

    def __init__(self, chunks: tuple[KnowledgeChunk, ...]):
        self.chunks = chunks
        self._rows = {lang: [] for lang in LANGUAGES}
        for chunk in chunks:
            headings = f"{chunk.document_title} {chunk.section_title}"
            counts = Counter(_terms(headings) * 2 + _terms(f"{chunk.excerpt} {chunk.review_guidance}"))
            self._rows[chunk.language].append((chunk, counts, sum(counts.values())))
        self._df = {lang: Counter(term for _, counts, _ in rows for term in counts) for lang, rows in self._rows.items()}
        self._average = {lang: sum(length for _, _, length in rows) / len(rows) if rows else 1
                         for lang, rows in self._rows.items()}

    def search(self, query: str, *, language: str, top_k: int = DEFAULT_TOP_K) -> list[KnowledgeHit]:
        if (not isinstance(query, str) or not query.strip() or len(query) > MAX_QUERY_LENGTH
                or any(not ch.isprintable() for ch in query)
                or language not in LANGUAGES or type(top_k) is not int or not 1 <= top_k <= MAX_TOP_K):
            raise KnowledgeBaseError("Invalid knowledge query, language, or result limit.")
        terms = set(_terms(query))
        topics = {term for term in terms if term.startswith("topic:")}
        if not terms:
            return []
        rows, df, average = self._rows[language], self._df[language], self._average[language]
        weights = {term: math.log1p((len(rows) - df[term] + 0.5) / (df[term] + 0.5)) for term in sorted(terms) if df[term]}
        ranked = []
        for chunk, counts, length in rows:
            matches = terms & counts.keys()
            if (topics and not topics & matches) or (not topics and (len(matches) < 2 or 2 * len(matches) < len(terms))):
                continue
            base = _K1 * (1 - _B + _B * length / average)
            score = sum(weights[term] * counts[term] * (_K1 + 1) / (counts[term] + base)
                        * (2.5 if term in topics else 1) for term in sorted(matches))
            if score > 0:
                ranked.append(KnowledgeHit(chunk, score))
        ranked.sort(key=lambda hit: (-hit.score, hit.chunk.document_id, int(hit.chunk.section_id)))
        results, seen = [], set()
        for hit in ranked:
            text = " ".join(hit.chunk.excerpt.split())
            if text not in seen:
                results.append(hit)
                seen.add(text)
            if len(results) == top_k:
                break
        return results
