# Issue43 · 工具参数 JSON 有限纠正

本轮只处理 #43，基线 PR48 `4bf13e31f402d35cb273f58e5c8f383eb799ce6d`。隔离分支 `codex/tool-json-correction`，工作树 `A:/audit-agent-json`。按既定顺序承接；未推进 #44 多轮抽取或 #45 引文改造。原报价上下文失败和 PR39 JSON 失败仍保留。

## 实现及工程证据

OpenAI 兼容适配器保留破损参数原文和具体 JSON 行列错误，采购 loop 将其作为未执行的工具错误返回模型，不尝试自动修补 JSON。每次审查最多允许两次纠正；第三份破损参数终止，所有调用仍计入原六轮预算。跨文字结束后的继续调用共用同一纠正上限。成功提交立即结束，不重放之前成功的工具。未启用纠正的通用 loop 保持整批参数先校验、默认流式失败后非流式回退。

失败任务在现有 `review_jobs.result` 中保留本地工具 trace、原始破损参数、反馈和轮次；后续接口异常仍保留这些诊断，`error` 保留实际异常类别，不保存 provider 响应体或凭证。成功和耗尽均通过 intake→worker→detail/SQLite 边界验证。负责人建议继续使用前序 PR47 后端生成的业务建议，原模型草稿另存。

实现 `406e732`；独立审查修复 `5bf7062`；最终产品 `f0494913e60af8a718c00224d133873dd6ce7fa7`。最初六项测试失败，其中首例测试设置需先完成旧 pending job，另五项直接暴露原解析/诊断缺口；修正设置后首例验证历史8席阶段成功纠正。最终新增12项回归，覆盖两次纠正、跨外层循环耗尽、轮次耗尽、最后一轮有效提交、同批工具、后续接口失败、通用副作用和流式回退。相关82 passed，Ruff/diffcheck通过。完整gate与最终独立审查收尾另追加。

独立 Standards/Spec 发现并修复：默认调用整批校验前执行副作用、已成功提交被后续破损调用覆盖、后续接口错误丢诊断、默认流式回退行为改变。完整gate另发现两项旧测试要求用满预算；有效提交现为终态，改为断言 `min(budget,3)`，继续保留实际状态与总额断言。

## 历史破损参数确定性回放

fixture逐字提取自 `scenarios-20261117-extra/latest-of-two-changes-trial-1/stage-2/wire-responses.json`，首个错误为 `Expecting ',' delimiter: line 1 column 93 (char 92)`。完整原参数包含金额缺引号、跨来源拼接、杂入推理等问题；本轮只解决 JSON 纠正入口。更正参数由脚本明确提供，不能算模型自主纠正。

| 回放 | 基线 | 候选 | 说明 |
|---|---|---|---|
| 精确破损参数后提供完整有效8席参数 | failed / JSONDecodeError，2次请求 | completed，3次请求，11520元 | 新代码保留1份原始错误并返回反馈，旧代码到解析即停 |
| 连续破损参数 | failed，2次请求，无trace | failed / ToolArgumentsExhausted，4次请求，3份错误入trace | 两次纠正机会，第三份不再调用模型；末次反馈仅保存，未声称模型已收到 |
| 正常8席提交 | completed，3次请求 | completed，2次请求 | 新代码有效提交后直接结束 |

回放在 `5bf7062` 执行；之后 `f049491` 仅补通用流式回退及测试，采购非流式路径未改变。旧、新耗尽回放中数据库均已有11520元，这是入库时的规则计算，**审查任务仍failed**，不算通过。零审批决定/通知尝试。证据 `optimization-json-replay-{baseline,v1}-20261120/{corrected,exhausted,normal-control}/result.json`；`optimization-json-tools-20261120/replay.py` 只使用脚本响应，无网络。

## 真实模型：资源阻塞，尚未验收

原题/extra-v1评分（含既有“出图/用于出图”同义规则）、制度、glm-4.5-air、默认温度、6轮/8192tokens不变；系统提示词SHA256两组均 `bbb48fa40f30a112fa7f254faf5df6ffb2812cd23b6168b96fe9c5fc6663cd23`。任务为旧连续5→8→6席及正常月付对照，各3次；每个独立trial一个隔离SQLite，三阶段按原脚本顺序更新。共用原eval运行锁串行执行。

| 题目/阶段 | 旧历史完成/业务通过 | 即时基线完成/业务通过 | 候选完成/业务通过 |
|---|---|---|---|
| 连续修改整题（三阶段全部通过） | 2/3 | 0/3；9阶段均RateLimitError | 尚无完整trial；只尝试trial1第一阶段 |
| 初始5席阶段 | 3/3 | 0/3，均接口失败 | 0/1尝试；其余2未运行 |
| 8席阶段 | 2/3 | 0/3，均接口失败 | 未运行0/3计划 |
| 最终6席阶段 | 3/3 | 0/3，均接口失败 | 未运行0/3计划 |
| 正常月付对照 | 3/3 | 0/3，均接口失败 | 未运行0/3计划 |

基线源码4bf13e3共12阶段均RateLimitError，无有效模型响应。候选源码5bf7062首阶段同样失败，捕获HTTP429、错误码1113：**“余额不足或无可用资源包,请充值。”**，停止后续11阶段。基线未捕获错误正文，只确认相同配置下RateLimitError；候选明示资源不足，不能断言每份基线错误正文相同。基线运行器未提前终止，候选运行器增加资源错误即停；任务与评分不改，脚本hash分别保存plan。

13次可见SDK请求、0次有效模型响应；SDK内部HTTP重试次数/费用未知，不能凭缺usage宣称费用为零。所有首次提交、首次工具反馈、有效提交、保存模型建议均无；首次正确/反馈纠正/最终模型能力失败为不可评估0/0，另计基础设施失败13/13。不能把本轮0完成解释成新代码模型能力退化。历史trial1中8席失败、最终6席成功继续保留，未用终态覆盖中间失败。

13/13阶段只读核对 job、materials/review（中间版本用revisions）与文件一致。零决定和通知尝试。没有本轮已保存模型建议。未做真实邮件、浏览器、人工审批、用户专家语义验收。工程通过与真实Agent能力验收分开；Issue43的真实验收项保持未完成。

## 证据与恢复入口

完整原始calls、wire、observed、job、verdict、每次SQLite在：

- `data/procurement-acceptance/optimization-json-baseline-20261120`：计划12/12阶段尝试；6个trial记录。
- `data/procurement-acceptance/optimization-json-v1-20261120`：计划12，尝试1，未运行11；部分trial带interrupted标记；summary/assessed-results由只读脚本生成。
- `data/procurement-acceptance/optimization-json-tools-20261120/{run.py,replay.py,assess.py}`：现有runner封装、回放和只读核验。

当前阻塞为既有GLM账户资源。恢复后先读共用锁/进程及PR最新版本，复用本子任务，新建实验版本目录重新做完整配对；不覆盖本轮失败、旧数据或重复成功试次。继续固定原配置，不擅自换模型、充值或调整预算。草稿PR交付，未合并、未关闭父票、未暂停定时任务。其余优化尚未完成。

## 最终工程复核 · 2026-11-20 17:46 +08:00

完整 release gate：374 passed、11既有live skipped；默认Anthropic无key，通用judge跳过。Ruff、运行时skills校验、diffcheck通过。独立Standards/Spec已复核最终产品f049491，无剩余代码问题，各复跑JSON/金额证据40项通过。真实模型仍为13阶段服务失败、候选11阶段未跑；不作能力比较。代码可审阅，验收项保持开放。

## 2026-11-20 用户授权改用DeepSeek后的续办

用户明确要求“换成deepseek的api吧”并填写本地配置，选择deepseek-v4-flash。上文GLM资源阻塞是历史结果，已另建DeepSeek即时基线/候选配对完成本子任务真实场景验收：连续5→8→6席及月付对照各3次，两组各12/12阶段业务与保存建议通过，候选首次12/12、反馈纠正0/12、最终失败0/12。本组没有JSON错误，不宣称真实纠正或成功率提升（基线亦12/12）。原GLM服务失败/11阶段未跑、历史JSON失败及脚本回放均保留。详细条件、逐阶段数据库/建议、调用统计和限制见[DeepSeek续办报告](procurement-json-deepseek-verification.md)。
