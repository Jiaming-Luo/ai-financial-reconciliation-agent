"""Bilingual, evidence-scoped hypotheses for the advisory analysis layer."""

from dataclasses import dataclass

from .anomaly_detector import RECOMMENDED_ACTIONS


INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


@dataclass(frozen=True)
class Hypothesis:
    cause_code: str
    en_description: str
    cn_description: str
    applicable_anomaly_types: tuple[str, ...]
    required_evidence: tuple[tuple[str, int], ...] = ()
    review_required: bool = True

    def describe(self, language: str) -> str:
        if self.cause_code == INSUFFICIENT_EVIDENCE:
            return self.en_description if language == "en" else self.cn_description
        if language == "en":
            return f"A possible cause is {self.en_description}. Further verification is required."
        return f"可能原因：{self.cn_description}。具体原因仍需人工核实。"


CATALOG = {
    entry.cause_code: entry for entry in (
        Hypothesis("REPORTING_DELAY", "a delay in reporting payment records", "付款记录报送延迟",
                   ("MISSING_PAYMENT",), (("service_record", 1),)),
        Hypothesis("DATA_ENTRY_ERROR", "an error during source data entry", "源数据录入错误",
                   ("INVALID_DATA",), (("invalid_source_record", 1),)),
        Hypothesis("INCORRECT_CONTRACT_PRICE", "use of a different contract price in the reported amount",
                   "报送金额使用了不同的合同价格", ("PRICE_MISMATCH",),
                   (("service_record", 1), ("matched_contract", 1))),
        Hypothesis("MISSING_CONTRACT_RECORD", "an applicable contract omitted from the supplied records",
                   "提交的源记录遗漏了适用合同", ("MISSING_CONTRACT",), (("service_record", 1),)),
        Hypothesis("CONTRACT_VERSION_CONFLICT", "an unresolved contract revision with overlapping effective dates",
                   "合同修订未协调生效区间", ("CONTRACT_OVERLAP",), (("contract_candidate", 2),)),
        Hypothesis("DUPLICATE_IMPORT", "repeated ingestion of the same payment record", "同一付款记录被重复导入",
                   ("DUPLICATE_PAYMENT",), (("exact_duplicate_payment", 1),)),
        Hypothesis("INCORRECT_SETTLEMENT_PERIOD", "assignment of a payment to the wrong settlement period",
                   "付款被归入错误的结算期间", ("UNDERPAYMENT", "OVERPAYMENT", "UNMATCHED_PAYMENT"),
                   (("payment_record", 1),)),
        Hypothesis("PARTIAL_PAYMENT", "an installment remittance", "该笔到账属于分期付款",
                   ("UNDERPAYMENT",), (("payment_record", 1),)),
        Hypothesis("PAYMENT_ALLOCATION_ERROR", "a mismatch in how the remittance was allocated to the settlement group",
                   "付款分配与该结算组不一致", ("UNDERPAYMENT", "OVERPAYMENT", "UNMATCHED_PAYMENT"),
                   (("payment_record", 1),)),
        Hypothesis(INSUFFICIENT_EVIDENCE, "The available evidence is insufficient to infer a cause. Further verification is required.",
                   "现有证据不足以推断原因，仍需人工核实。", tuple(RECOMMENDED_ACTIONS)),
    )
}


def catalog_options(catalog: dict, anomaly_type: str, evidence: dict[str, list[str]]) -> dict:
    """Project catalog entries with sufficient evidence into model options."""
    options = {}
    for code, entry in catalog.items():
        if anomaly_type not in entry.applicable_anomaly_types:
            continue
        requirements = [
            {"evidence_kind": kind, "minimum": count, "references": evidence.get(kind, [])}
            for kind, count in entry.required_evidence
        ]
        if all(len(rule["references"]) >= rule["minimum"] for rule in requirements):
            options[code] = {"description": entry.en_description, "required_evidence": requirements}
    return options


def eligible_hypotheses(anomaly_type: str, evidence: dict[str, list[str]]) -> dict:
    return catalog_options(CATALOG, anomaly_type, evidence)
