import re
import unittest
from dataclasses import replace
from pathlib import Path

from src.anomaly_detector import RECOMMENDED_ACTIONS
from src.knowledge_base import KnowledgeBaseError, KnowledgeIndex
from tests.fixtures import ROOT, workspace_temp


class KnowledgeIndexTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = ROOT / "knowledge_base"
        cls.index = KnowledgeIndex.load(cls.directory)

    def test_corpus_has_six_paired_documents_and_original_numbered_excerpts(self):
        chunks = self.index.chunks
        self.assertEqual(len(list(self.directory.glob("*.md"))), 12)
        self.assertEqual(len(chunks), 36)
        for language in ("en", "cn"):
            selected = [row for row in chunks if row.language == language]
            self.assertEqual({(row.document_id, row.section_id) for row in selected},
                             {(f"KB-{number:02}", str(section)) for number in range(1, 7) for section in range(1, 4)})
            anomaly_source = " ".join(row.excerpt for row in selected if row.document_id == "KB-04")
            self.assertTrue(all(code in anomaly_source for code in RECOMMENDED_ACTIONS))
            for row in selected:
                source = (self.directory / row.source_file).read_text(encoding="utf-8")
                self.assertIn(f"## {row.section_id}. {row.section_title}", source)
                self.assertIn(row.excerpt, source)
                self.assertIn(row.review_guidance, source)
                self.assertEqual(row.version, "1.0")
                self.assertTrue(row.scope)
                self.assertIn("Status: SIMULATION", source)
                self.assertIsNone(re.search(r"SIM-H\d|[\w.-]+@[\w.-]+\.[a-z]+|sk-[\w-]{20,}", source))

    def test_english_overlap_ranks_contract_and_human_escalation(self):
        hits = self.index.search("How should a contract overlap be handled?", language="en")
        self.assertEqual(len(hits), 3)
        self.assertEqual({(h.chunk.document_id, h.chunk.section_id) for h in hits[:2]}, {("KB-02", "2"), ("KB-06", "1")})
        self.assertEqual([h.score for h in hits], sorted((h.score for h in hits), reverse=True))
        self.assertIn("contract owner", hits[0].chunk.excerpt)

    def test_chinese_and_cross_language_aliases_retrieve_in_requested_language(self):
        for query, lang, evidence in (
            ("发现重复付款记录时应该如何处理？", "cn", ("KB-03", "2")),
            ("ＤＵＰＬＩＣＡＴＥ＿ＰＡＹＭＥＮＴ", "cn", ("KB-03", "2")),
            ("合同重叠", "en", ("KB-02", "2")),
        ):
            with self.subTest(query=query, language=lang):
                hits = self.index.search(query, language=lang)
                self.assertTrue(all(h.chunk.language == lang for h in hits))
                self.assertIn(evidence, [(h.chunk.document_id, h.chunk.section_id) for h in hits])

    def test_no_match_and_weak_generic_matches_return_no_evidence(self):
        for query, language in (("When is the next lunar eclipse?", "en"), ("员工带薪年假如何计算？", "cn"),
                                ("travel expense reimbursement policy", "en"), ("how should I", "en")):
            with self.subTest(query=query):
                self.assertEqual(self.index.search(query, language=language), [])

    def test_duplicate_excerpts_are_removed_before_the_top_k_cutoff(self):
        hit = self.index.search("contract overlap", language="en", top_k=1)[0].chunk
        duplicate = replace(hit, document_id="KB-99", source_file="duplicate.en.md")
        index = KnowledgeIndex((duplicate, hit))
        results = index.search("contract overlap", language="en", top_k=5)
        self.assertEqual([h.chunk.document_id for h in results], [hit.document_id])

    def test_invalid_documents_and_search_parameters_are_rejected(self):
        with workspace_temp() as temp:
            directory = Path(temp)
            path = directory / "malformed.md"
            path.write_text("# Simulation\n## 1. Invalid\nInstructions\n", encoding="utf-8")
            with self.assertRaises(KnowledgeBaseError):
                KnowledgeIndex.load(directory)
            sample = (self.directory / "02-contract-pricing.en.md").read_text(encoding="utf-8")
            path.write_text(sample.replace("## 2.", "## 1."), encoding="utf-8")
            with self.assertRaises(KnowledgeBaseError):
                KnowledgeIndex.load(directory)
        for query, language, top_k in (("  ", "en", 3), ("x" * 321, "en", 3), ("a\0b", "en", 3),
                                        ("contract overlap", "fr", 3), ("contract overlap", "en", True),
                                        ("contract overlap", "en", 6)):
            with self.subTest(language=language, top_k=top_k), self.assertRaises(KnowledgeBaseError):
                self.index.search(query, language=language, top_k=top_k)
