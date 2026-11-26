# 九类异常分类及处理规范

Document ID: KB-04
Version: 1.0
Language: cn
Scope: 模拟医院检测费用对账原型
Status: SIMULATION

> 模拟业务规范，仅用于项目演示。本文不代表实际企业制度、监管要求或行业法律规定。

## 1. 收款及差额异常

MISSING_PAYMENT 表示可计算结算组缺少收款。UNDERPAYMENT 表示已有有效收款且应收大于实付。OVERPAYMENT 表示实付超过应收。UNMATCHED_PAYMENT 表示有有效付款但无业务行。

Review guidance: 核查原始付款凭证与结算归属，将拟处理意见提交复核。

## 2. 定价异常

PRICE_MISMATCH 表示申报金额与唯一有效合同计费不一致。合同计费金额仍可使用，异常仍需复核。MISSING_CONTRACT 表示无有效合同。CONTRACT_OVERLAP 表示同一业务日期存在多个有效版本。未解决的定价问题会挂起结算。

Review guidance: 对照源记录数量、申报金额与候选合同，保留复核证据。

## 3. 重复记录与无效数据

DUPLICATE_PAYMENT 标记重复付款参考号。有效且相同的副本仅计一次，冲突副本或无效副本保持未解决。INVALID_DATA 包括非法日期、无效值及计费单位冲突。问题妨碍可靠结算时将结算挂起。

Review guidance: 保留受影响的源记录及各项独立异常标记，供人工复核。
