# 金额格式与纠正反馈 · Issue42 验证报告

金额schema增加纯数字字符串示例，后端分别指出格式错误与原文数值不符。原文引文和Decimal金额核验保留。该改动让错误参数获得明确操作提示；本组真实基线也全部通过，不能据此宣称通过率提升。

## 版本与条件

- 即时基线：b7571a380b558185f24b2351ff41849915a68a9d（PR47代码）；候选：1f9381c586c46739620884669d516b13d17a37bb。隔离工作树A:/audit-agent-amount-baseline与A:/audit-agent-amount。只改amount schema/格式校验/错误反馈及回归。
- glm-4.5-air，既有GLM配置；6轮、8192 tokens、默认温度、同一演示制度v1.0。季度原题取extra-v1，月付对照取scenario-v1，两组均用现有extra-v1检查（包含既有出图/用于出图同义规则），逐次独立SQLite。共享运行锁、串行，无覆盖或挑选重跑。
- 系统提示词未变；工具schema变化是本轮干预。实际hash及工具定义保存在每轮calls.json；未改JSON恢复、审批或发信授权。

## 逐题对照

| 题目 | 历史业务 | 即时基线业务/完整 | 候选业务/完整 | 候选首次正确 | 反馈后正确 | 最终失败 |
|---|---|---|---|---|---|---|
| 12个月季度 | 2/3 | 3/3、3/3 | 3/3、3/3 | 3/3 | 0/3 | 0/3 |
| 12个月月付 | 3/3 | 3/3、3/3 | 3/3、3/3 | 2/3 | 1/3 | 0/3 |

完整=业务检查与实际保存建议符合场景；首次/反馈后/最终失败互斥，以首个有效submit之前的错误为准。后端生成的保存建议已在PR47实现，本轮不把它算作模型草稿能力提升。历史题组提示词不同，仅作历史参考；本轮因果对照采用即时基线。每题三次只描述本组。

两组首次材料字段均6/6；首次材料+逐字引文基线6/6、候选5/6。候选首次产品正确5/6、反馈纠正1/6、最终失败0/6。月付Trial3把price_basis引文中的“设计”漏掉，旧有逐字核验反馈price_basis的原文依据无法核对；改为“每席位每月120元”后完成。全部首次amount均为字符串120，无金额反馈，不能声称新金额反馈在真实运行中促成纠正。候选季度Trial3草稿另要求软件品牌型号，基线月付Trial1及季度Trial2草稿也新增建议；实际保存建议由PR47后端生成，无这些追问，草稿问题原样保留，不归因于本轮金额修改。

## 旧失败参数回放

历史quarterly Trial3的5次submit依次为amount="每席位每季度120元"两次、"120元"三次，审查failed/ValueError，无本轮已保存建议。全部原始字段、引文、反馈和失败数据库保留在scenarios-20261117-extra/quarterly-trial-3，未覆盖。

新旧后端均拒绝5/5，脚本改为"120"后均completed/2400.00/无问题5/5。旧反馈为amount必须与原文报价数值一致；新反馈明确纯数字字符串、最多两位小数、不含单位/逗号、不用JSON数值，并要求evidence.amount保留逐字原文。这5份含重复参数，不当作5个独立场景；脚本纠正不计真实模型纠正。详见optimization-amount-replay-{baseline,v1}-20261120，每份保留calls/SQLite/original/corrected/feedback/record。

## 原参数与实际结果（逐次）

### baseline/quarterly/1

- 首次submit：`{"materials": {"item": "设计软件", "purpose": "用于出图", "seats": 5, "months": 12, "amount": "120", "billing_period": "quarterly", "price_basis": "per_seat"}, "evidence": {"item": "设计软件", "purpose": "用于出图", "seats": "5个席位", "months": "12个月", "amount": "每席位每季度120元", "billing_period": "每季度", "price_basis": "每席位"}, "clause_ids": ["SW-1", "SW-2"], "case_ids": [], "summary": "申请订阅设计软件用于出图，需要5个席位，订阅12个月，每席位每季度120元。申请已明确说明采购对象、业务用途、席位数和订阅期限，并明确报价金额、计费周期及报价覆盖单席，符合SW-1和SW-2条款要求。"}`
- 有效提交前反馈：`[]`
- 业务及审查：completed，ready_for_review，总额2400.00，questions=[]；分类first_correct。
- 实际保存建议：材料核验完成，待负责人审批。预计总额 2400.00 元。审批和发信仍须负责人确认。
- 原模型草稿（单列保留，本轮不重评分）：申请订阅设计软件用于出图，需要5个席位，订阅12个月，每席位每季度120元。申请已明确说明采购对象、业务用途、席位数和订阅期限，并明确报价金额、计费周期及报价覆盖单席，符合SW-1和SW-2条款要求。
- 证据：A:\audit-agent-eval\data\procurement-acceptance\optimization-amount-baseline-20261120\quarterly-trial-1\stage-1

### baseline/normal-per-seat/1

- 首次submit：`{"materials": {"item": "设计软件", "purpose": "出图", "seats": 5, "months": 12, "amount": "120", "billing_period": "monthly", "price_basis": "per_seat"}, "evidence": {"item": "申请订阅设计软件用于出图", "purpose": "用于出图", "seats": "需要5个席位", "months": "订阅12个月", "amount": "每席位每月120元", "billing_period": "每月", "price_basis": "每席位每月120元"}, "clause_ids": ["SW-1", "SW-2"], "case_ids": [], "summary": "申请基本符合制度要求，已包含采购对象（设计软件）、业务用途（出图）、席位数（5个）、订阅期限（12个月）、报价金额（120元）、计费周期（月付）和报价覆盖范围（每席位）。建议补充具体的设计软件名称以确保采购准确性。"}`
- 有效提交前反馈：`[]`
- 业务及审查：completed，ready_for_review，总额7200.00，questions=[]；分类first_correct。
- 实际保存建议：材料核验完成，待负责人审批。预计总额 7200.00 元。审批和发信仍须负责人确认。
- 原模型草稿（单列保留，本轮不重评分）：申请基本符合制度要求，已包含采购对象（设计软件）、业务用途（出图）、席位数（5个）、订阅期限（12个月）、报价金额（120元）、计费周期（月付）和报价覆盖范围（每席位）。建议补充具体的设计软件名称以确保采购准确性。
- 证据：A:\audit-agent-eval\data\procurement-acceptance\optimization-amount-baseline-20261120\normal-per-seat-trial-1\stage-1

### baseline/quarterly/2

- 首次submit：`{"materials": {"item": "设计软件", "purpose": "用于出图", "seats": 5, "months": 12, "amount": "120", "billing_period": "quarterly", "price_basis": "per_seat"}, "evidence": {"item": "设计软件", "purpose": "用于出图", "seats": "5个席位", "months": "12个月", "amount": "每席位每季度120元", "billing_period": "每季度", "price_basis": "每席位"}, "clause_ids": ["SW-1", "SW-2"], "case_ids": [], "summary": "申请已包含软件采购的基本要素：设计软件、5席位、12个月订阅期限、每席位每季度120元报价。业务用途描述为\"用于出图\"但较为简略，建议补充具体业务场景说明。报价覆盖范围明确为每席位，计费周期为季度，符合SW-2条款要求。"}`
- 有效提交前反馈：`[]`
- 业务及审查：completed，ready_for_review，总额2400.00，questions=[]；分类first_correct。
- 实际保存建议：材料核验完成，待负责人审批。预计总额 2400.00 元。审批和发信仍须负责人确认。
- 原模型草稿（单列保留，本轮不重评分）：申请已包含软件采购的基本要素：设计软件、5席位、12个月订阅期限、每席位每季度120元报价。业务用途描述为"用于出图"但较为简略，建议补充具体业务场景说明。报价覆盖范围明确为每席位，计费周期为季度，符合SW-2条款要求。
- 证据：A:\audit-agent-eval\data\procurement-acceptance\optimization-amount-baseline-20261120\quarterly-trial-2\stage-1

### baseline/normal-per-seat/2

- 首次submit：`{"materials": {"item": "设计软件", "purpose": "出图", "amount": "120", "billing_period": "monthly", "price_basis": "per_seat", "seats": 5, "months": 12}, "evidence": {"item": "申请订阅设计软件用于出图", "purpose": "申请订阅设计软件用于出图", "amount": "每席位每月120元", "billing_period": "每席位每月120元", "price_basis": "每席位每月120元", "seats": "需要5个席位", "months": "订阅12个月"}, "clause_ids": ["SW-1", "SW-2"], "case_ids": [], "summary": "本次申请采购设计软件用于出图业务，申请5个席位，订阅12个月。报价为每席位每月120元，计费周期为月付，报价覆盖单席位。申请材料完整，符合SW-1和SW-2条款要求：明确说明了采购对象、业务用途、席位数和订阅期限，同时明确了报价金额、计费周期及报价覆盖范围。"}`
- 有效提交前反馈：`[]`
- 业务及审查：completed，ready_for_review，总额7200.00，questions=[]；分类first_correct。
- 实际保存建议：材料核验完成，待负责人审批。预计总额 7200.00 元。审批和发信仍须负责人确认。
- 原模型草稿（单列保留，本轮不重评分）：本次申请采购设计软件用于出图业务，申请5个席位，订阅12个月。报价为每席位每月120元，计费周期为月付，报价覆盖单席位。申请材料完整，符合SW-1和SW-2条款要求：明确说明了采购对象、业务用途、席位数和订阅期限，同时明确了报价金额、计费周期及报价覆盖范围。
- 证据：A:\audit-agent-eval\data\procurement-acceptance\optimization-amount-baseline-20261120\normal-per-seat-trial-2\stage-1

### baseline/quarterly/3

- 首次submit：`{"materials": {"item": "设计软件", "purpose": "用于出图", "seats": 5, "months": 12, "amount": "120", "billing_period": "quarterly", "price_basis": "per_seat"}, "evidence": {"item": "申请订阅设计软件用于出图", "purpose": "用于出图", "seats": "需要5个席位", "months": "订阅12个月", "amount": "每席位每季度120元", "billing_period": "每季度", "price_basis": "每席位"}, "clause_ids": ["SW-1", "SW-2"], "case_ids": [], "summary": "采购申请符合制度要求：已明确说明采购对象（设计软件）、业务用途（用于出图）、席位数（5）、订阅期限（12个月）、报价金额（120元）、计费周期（季度）及报价覆盖范围（每席位）。所有必需字段完整，符合SW-1和SW-2条款要求。"}`
- 有效提交前反馈：`[]`
- 业务及审查：completed，ready_for_review，总额2400.00，questions=[]；分类first_correct。
- 实际保存建议：材料核验完成，待负责人审批。预计总额 2400.00 元。审批和发信仍须负责人确认。
- 原模型草稿（单列保留，本轮不重评分）：采购申请符合制度要求：已明确说明采购对象（设计软件）、业务用途（用于出图）、席位数（5）、订阅期限（12个月）、报价金额（120元）、计费周期（季度）及报价覆盖范围（每席位）。所有必需字段完整，符合SW-1和SW-2条款要求。
- 证据：A:\audit-agent-eval\data\procurement-acceptance\optimization-amount-baseline-20261120\quarterly-trial-3\stage-1

### baseline/normal-per-seat/3

- 首次submit：`{"materials": {"item": "设计软件", "purpose": "用于出图", "amount": "120", "billing_period": "monthly", "price_basis": "per_seat", "seats": 5, "months": 12}, "evidence": {"item": "设计软件", "purpose": "用于出图", "amount": "每席位每月120元", "billing_period": "每月", "price_basis": "每席位每月120元", "seats": "需要5个席位", "months": "订阅12个月"}, "clause_ids": ["SW-1", "SW-2"], "case_ids": [], "summary": "申请订阅设计软件用于出图，需要5个席位，订阅12个月，每席位每月120元。已明确采购对象、业务用途、席位数、订阅期限、报价金额、计费周期及报价覆盖范围。"}`
- 有效提交前反馈：`[]`
- 业务及审查：completed，ready_for_review，总额7200.00，questions=[]；分类first_correct。
- 实际保存建议：材料核验完成，待负责人审批。预计总额 7200.00 元。审批和发信仍须负责人确认。
- 原模型草稿（单列保留，本轮不重评分）：申请订阅设计软件用于出图，需要5个席位，订阅12个月，每席位每月120元。已明确采购对象、业务用途、席位数、订阅期限、报价金额、计费周期及报价覆盖范围。
- 证据：A:\audit-agent-eval\data\procurement-acceptance\optimization-amount-baseline-20261120\normal-per-seat-trial-3\stage-1

### candidate/quarterly/1

- 首次submit：`{"materials": {"item": "设计软件", "purpose": "出图", "seats": 5, "months": 12, "billing_period": "quarterly", "amount": "120", "price_basis": "per_seat"}, "evidence": {"item": "设计软件", "purpose": "出图", "seats": "5个席位", "months": "12个月", "billing_period": "每季度", "amount": "每席位每季度120元", "price_basis": "每席位"}, "clause_ids": ["SW-1", "SW-2"], "case_ids": [], "summary": "软件采购申请完整：设计软件用于出图，5个席位，12个月订阅，每席位每季度120元。符合SW-1和SW-2条款要求。"}`
- 有效提交前反馈：`[]`
- 业务及审查：completed，ready_for_review，总额2400.00，questions=[]；分类first_correct。
- 实际保存建议：材料核验完成，待负责人审批。预计总额 2400.00 元。审批和发信仍须负责人确认。
- 原模型草稿（单列保留，本轮不重评分）：软件采购申请完整：设计软件用于出图，5个席位，12个月订阅，每席位每季度120元。符合SW-1和SW-2条款要求。
- 证据：A:\audit-agent-eval\data\procurement-acceptance\optimization-amount-v1-20261120\quarterly-trial-1\stage-1

### candidate/normal-per-seat/1

- 首次submit：`{"materials": {"item": "设计软件", "purpose": "出图", "seats": 5, "months": 12, "amount": "120", "billing_period": "monthly", "price_basis": "per_seat"}, "evidence": {"item": "申请订阅设计软件用于出图，需要5个席位，订阅12个月，每席位每月120元。", "purpose": "申请订阅设计软件用于出图，需要5个席位，订阅12个月，每席位每月120元。", "seats": "申请订阅设计软件用于出图，需要5个席位，订阅12个月，每席位每月120元。", "months": "申请订阅设计软件用于出图，需要5个席位，订阅12个月，每席位每月120元。", "amount": "申请订阅设计软件用于出图，需要5个席位，订阅12个月，每席位每月120元。", "billing_period": "申请订阅设计软件用于出图，需要5个席位，订阅12个月，每席位每月120元。", "price_basis": "申请订阅设计软件用于出图，需要5个席位，订阅12个月，每席位每月120元。"}, "clause_ids": ["SW-1", "SW-2"], "case_ids": [], "summary": "采购申请材料完整，包含设计软件用于出图的业务用途，5个席位，12个月订阅期限，每席位每月120元的报价，月付计费，报价覆盖范围为每席。符合SW-1和SW-2条款要求。"}`
- 有效提交前反馈：`[]`
- 业务及审查：completed，ready_for_review，总额7200.00，questions=[]；分类first_correct。
- 实际保存建议：材料核验完成，待负责人审批。预计总额 7200.00 元。审批和发信仍须负责人确认。
- 原模型草稿（单列保留，本轮不重评分）：采购申请材料完整，包含设计软件用于出图的业务用途，5个席位，12个月订阅期限，每席位每月120元的报价，月付计费，报价覆盖范围为每席。符合SW-1和SW-2条款要求。
- 证据：A:\audit-agent-eval\data\procurement-acceptance\optimization-amount-v1-20261120\normal-per-seat-trial-1\stage-1

### candidate/quarterly/2

- 首次submit：`{"materials": {"item": "设计软件", "purpose": "出图", "seats": 5, "months": 12, "amount": "120", "billing_period": "quarterly", "price_basis": "per_seat"}, "evidence": {"item": "设计软件", "purpose": "出图", "seats": "5个席位", "months": "12个月", "amount": "每席位每季度120元", "billing_period": "每季度", "price_basis": "每席位"}, "clause_ids": ["SW-1", "SW-2"], "case_ids": [], "summary": "采购申请符合制度要求：设计软件用于出图，5个席位，12个月订阅期，每席位每季度120元。已明确报价覆盖单席，满足SW-1和SW-2条款要求。"}`
- 有效提交前反馈：`[]`
- 业务及审查：completed，ready_for_review，总额2400.00，questions=[]；分类first_correct。
- 实际保存建议：材料核验完成，待负责人审批。预计总额 2400.00 元。审批和发信仍须负责人确认。
- 原模型草稿（单列保留，本轮不重评分）：采购申请符合制度要求：设计软件用于出图，5个席位，12个月订阅期，每席位每季度120元。已明确报价覆盖单席，满足SW-1和SW-2条款要求。
- 证据：A:\audit-agent-eval\data\procurement-acceptance\optimization-amount-v1-20261120\quarterly-trial-2\stage-1

### candidate/normal-per-seat/2

- 首次submit：`{"materials": {"item": "设计软件", "purpose": "出图", "seats": 5, "months": 12, "amount": "120", "billing_period": "monthly", "price_basis": "per_seat"}, "evidence": {"item": "申请订阅设计软件", "purpose": "用于出图", "seats": "需要5个席位", "months": "订阅12个月", "amount": "每席位每月120元", "billing_period": "每月", "price_basis": "每席位"}, "clause_ids": ["SW-1", "SW-2"], "case_ids": [], "summary": "申请订阅设计软件用于出图，需要5个席位，订阅12个月，每席位每月120元。该申请符合制度SW-1和SW-2要求，完整说明了采购对象、业务用途、席位数、订阅期限、报价金额、计费周期及价格覆盖范围（per_seat）。"}`
- 有效提交前反馈：`[]`
- 业务及审查：completed，ready_for_review，总额7200.00，questions=[]；分类first_correct。
- 实际保存建议：材料核验完成，待负责人审批。预计总额 7200.00 元。审批和发信仍须负责人确认。
- 原模型草稿（单列保留，本轮不重评分）：申请订阅设计软件用于出图，需要5个席位，订阅12个月，每席位每月120元。该申请符合制度SW-1和SW-2要求，完整说明了采购对象、业务用途、席位数、订阅期限、报价金额、计费周期及价格覆盖范围（per_seat）。
- 证据：A:\audit-agent-eval\data\procurement-acceptance\optimization-amount-v1-20261120\normal-per-seat-trial-2\stage-1

### candidate/quarterly/3

- 首次submit：`{"materials": {"item": "设计软件", "purpose": "用于出图", "seats": 5, "months": 12, "billing_period": "quarterly", "price_basis": "per_seat", "amount": "120"}, "evidence": {"item": "设计软件", "purpose": "用于出图", "seats": "5个席位", "months": "12个月", "billing_period": "每季度", "price_basis": "每席位", "amount": "120元"}, "clause_ids": ["SW-1", "SW-2"], "case_ids": [], "summary": "申请订阅设计软件用于出图，需要5个席位，订阅12个月，每席位每季度120元。申请已明确说明业务用途（出图）、席位数（5个）、订阅期限（12个月）、报价金额（120元）、计费周期（季度）及价格覆盖范围（每席位），符合制度SW-1和SW-2要求。但采购对象仅为\"设计软件\"，未提供具体软件名称，建议确认具体软件品牌和型号。"}`
- 有效提交前反馈：`[]`
- 业务及审查：completed，ready_for_review，总额2400.00，questions=[]；分类first_correct。
- 实际保存建议：材料核验完成，待负责人审批。预计总额 2400.00 元。审批和发信仍须负责人确认。
- 原模型草稿（单列保留，本轮不重评分）：申请订阅设计软件用于出图，需要5个席位，订阅12个月，每席位每季度120元。申请已明确说明业务用途（出图）、席位数（5个）、订阅期限（12个月）、报价金额（120元）、计费周期（季度）及价格覆盖范围（每席位），符合制度SW-1和SW-2要求。但采购对象仅为"设计软件"，未提供具体软件名称，建议确认具体软件品牌和型号。
- 证据：A:\audit-agent-eval\data\procurement-acceptance\optimization-amount-v1-20261120\quarterly-trial-3\stage-1

### candidate/normal-per-seat/3

- 首次submit：`{"materials": {"item": "设计软件", "purpose": "出图", "seats": 5, "months": 12, "amount": "120", "billing_period": "monthly", "price_basis": "per_seat"}, "evidence": {"item": "申请订阅设计软件用于出图，需要5个席位，订阅12个月，每席位每月120元。", "purpose": "申请订阅设计软件用于出图，需要5个席位，订阅12个月，每席位每月120元。", "seats": "申请订阅设计软件用于出图，需要5个席位，订阅12个月，每席位每月120元。", "months": "申请订阅设计软件用于出图，需要5个席位，订阅12个月，每席位每月120元。", "amount": "申请订阅设计软件用于出图，需要5个席位，订阅12个月，每席位每月120元。", "billing_period": "申请订阅设计软件用于出图，需要5个席位，订阅12个月，每席位每月120元。", "price_basis": "申请订阅软件用于出图，需要5个席位，订阅12个月，每席位每月120元。"}, "clause_ids": ["SW-1", "SW-2"], "case_ids": [], "summary": "申请订阅设计软件用于出图，需要5个席位，订阅12个月，每席位每月120元。申请材料包含采购对象、业务用途、席位数、订阅期限、报价金额、计费周期及报价覆盖范围，符合采购制度要求。"}`
- 有效提交前反馈：`[{"tool": "submit_review", "args": {"materials": {"item": "设计软件", "purpose": "出图", "seats": 5, "months": 12, "amount": "120", "billing_period": "monthly", "price_basis": "per_seat"}, "evidence": {"item": "申请订阅设计软件用于出图，需要5个席位，订阅12个月，每席位每月120元。", "purpose": "申请订阅设计软件用于出图，需要5个席位，订阅12个月，每席位每月120元。", "seats": "申请订阅设计软件用于出图，需要5个席位，订阅12个月，每席位每月120元。", "months": "申请订阅设计软件用于出图，需要5个席位，订阅12个月，每席位每月120元。", "amount": "申请订阅设计软件用于出图，需要5个席位，订阅12个月，每席位每月120元。", "billing_period": "申请订阅设计软件用于出图，需要5个席位，订阅12个月，每席位每月120元。", "price_basis": "申请订阅软件用于出图，需要5个席位，订阅12个月，每席位每月120元。"}, "clause_ids": ["SW-1", "SW-2"], "case_ids": [], "summary": "申请订阅设计软件用于出图，需要5个席位，订阅12个月，每席位每月120元。申请材料包含采购对象、业务用途、席位数、订阅期限、报价金额、计费周期及报价覆盖范围，符合采购制度要求。"}, "output": "Error running submit_review: price_basis 的原文依据无法核对"}]`
- 业务及审查：completed，ready_for_review，总额7200.00，questions=[]；分类feedback_corrected。
- 实际保存建议：材料核验完成，待负责人审批。预计总额 7200.00 元。审批和发信仍须负责人确认。
- 原模型草稿（单列保留，本轮不重评分）：申请订阅设计软件用于出图，需要5个席位，订阅12个月，每席位每月120元。申请材料包含采购对象、业务用途、席位数、订阅期限、报价金额、计费周期及报价覆盖范围，符合采购制度要求。
- 证据：A:\audit-agent-eval\data\procurement-acceptance\optimization-amount-v1-20261120\normal-per-seat-trial-3\stage-1

## 数据库与工程检查

12/12只读SQLite材料、review、model_review终态与证据文件一致；12/12工具JSON回执与实际保存的status/total/questions/summary一致，零决定及通知尝试。逐条明细在assessed-results.json。负责人读取review.model_summary；未用失败草稿代替保存建议。

新增公开intake→worker回归初始5failed/23passed，改动后相关39passed；独立Standards复跑amount28passed。全gate362passed/11既有live skipped；默认Anthropic无key，通用judge跳过。Ruff/runtime skills/diffcheck通过。默认系统python缺anthropic，改用既有A:/audit-agent/.venv/Scripts/python.exe验证，未新增依赖。Standards/Spec已审查固定实现diff，最终报告审查和最新发布CI见交付记录。

离线回放、真实模型、页面/邮件分别界定：本轮无浏览器、真实收发、人工审批或用户/专家验收。JSON数值曾被str隐式接受，现按既有string schema拒绝，调用方需发送字符串。原报价格式/数值验证未放宽。

## 调用与剩余工作

- baseline：25可见调用，输入36280 / 输出7110tokens；system hash=bbb48fa40f30a112fa7f254faf5df6ffb2812cd23b6168b96fe9c5fc6663cd23。
- candidate：25可见调用，输入38818 / 输出7724tokens；system hash=bbb48fa40f30a112fa7f254faf5df6ffb2812cd23b6168b96fe9c5fc6663cd23。
- 费用及SDK内部重试未知。原始results.jsonl、calls、wire、job、observed、verdict及数据库全部保留。
- 本轮无最终失败，但保留上述首次引文错误及草稿多问问题；旧JSON/报价上下文等失败不改分、不关闭。后续#43参数JSON有限纠正为独立任务，本轮不实施。PR叠加PR47，父PR尚未全部验收，保持草稿、不合并、不暂停自动化。
