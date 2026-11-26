"""Evidence-scoped manual review actions for bilingual advisory reports."""

from dataclasses import dataclass

from .anomaly_detector import RECOMMENDED_ACTIONS
from .hypothesis_catalog import catalog_options


REQUEST_ADDITIONAL_EVIDENCE = "REQUEST_ADDITIONAL_EVIDENCE"
PAYMENT_FINDINGS = ("UNDERPAYMENT", "OVERPAYMENT", "UNMATCHED_PAYMENT")


@dataclass(frozen=True)
class ReviewAction:
    action_code: str
    en_description: str
    cn_description: str
    applicable_anomaly_types: tuple[str, ...]
    required_evidence: tuple[tuple[str, int], ...] = ()
    review_required: bool = True

    def describe(self, language: str) -> str:
        return self.en_description if language == "en" else self.cn_description


ACTION_CATALOG = {
    entry.action_code: entry for entry in (
        ReviewAction("CHECK_PAYMENT_REGISTER", "Compare the service records with the payment register.",
                     "对照业务记录和付款登记。", ("MISSING_PAYMENT",), (("service_record", 1),)),
        ReviewAction("VERIFY_PAYMENT_RECORDS", "Compare the related payment with its original receipt.",
                     "将相关付款与原始收款凭据核对。", PAYMENT_FINDINGS, (("payment_record", 1),)),
        ReviewAction("REVIEW_CONTRACT_EFFECTIVE_DATE", "Review the service date against the applicable contract dates.",
                     "核对业务日期与适用合同的生效区间。", ("MISSING_CONTRACT",), (("service_record", 1),)),
        ReviewAction("COMPARE_CONTRACT_VERSIONS", "Compare the effective dates and ask the contract owner to identify the applicable version.",
                     "比对合同生效区间，并请合同负责人核实适用版本。", ("CONTRACT_OVERLAP",), (("contract_candidate", 2),)),
        ReviewAction("CHECK_DUPLICATE_IMPORT", "Check the original receipt and import history for a duplicate import.",
                     "核查原始收款凭据和导入历史，确认是否重复导入。", ("DUPLICATE_PAYMENT",),
                     (("exact_duplicate_payment", 1),)),
        ReviewAction("VERIFY_DUPLICATE_REFERENCE", "Compare records that share a payment reference with their original receipt.",
                     "逐项核对共用付款参考号的记录及其原始收款凭据。", ("DUPLICATE_PAYMENT",), (("payment_record", 1),)),
        ReviewAction("CONFIRM_BILLING_QUANTITY", "Check the recorded quantity and billing unit against the matching contract.",
                     "对照匹配合同核查报送数量和计费单位。", ("PRICE_MISMATCH",),
                     (("service_record", 1), ("matched_contract", 1))),
        ReviewAction("REVIEW_SETTLEMENT_PERIOD", "Compare the payment's settlement period with the supporting evidence.",
                     "对照凭据核查付款归属的结算期间。", PAYMENT_FINDINGS, (("payment_record", 1),)),
        ReviewAction("VALIDATE_SOURCE_FIELDS", "Trace the invalid field to the original source and ask its owner to verify it.",
                     "追溯无效字段的来源，并请数据负责人核实。", ("INVALID_DATA",), (("invalid_source_record", 1),)),
        ReviewAction(REQUEST_ADDITIONAL_EVIDENCE, "Request additional evidence from the relevant record owner before deciding.",
                     "请相关记录负责人补充证据后再作判断。", tuple(RECOMMENDED_ACTIONS)),
    )
}


def eligible_actions(anomaly_type: str, evidence: dict[str, list[str]]) -> dict:
    return catalog_options(ACTION_CATALOG, anomaly_type, evidence)
