# 采购建议与业务状态一致

2026-11-20，[Issue41](https://github.com/qiqiqia777/audit-agent/issues/41)，对应[优化方案](procurement-agent-optimization-plan.md)第二轮。现有报价上下文修复及PR40独立交付；本轮仅处理保存建议和提交回执与业务结果一致，不修复JSON或改变评分。

## 实际改动

原submit_review先计算业务结果，却直接保存模型提交的自由文本摘要；10个月按季计费时，业务已待澄清，负责人仍会看到“材料完整”。新版本使用同一份后端报告生成保存的model_summary，包含实际待澄清/待负责人审批状态、已知总额或待确认总额、所有实际questions及人工审批/发信边界。submit_review返回JSON中的status、estimated_total_cny、questions、summary也来自该报告。

原模型文本另存model_draft_summary，首次参数和完整工具轨迹保留。负责人详情仍读取review.model_summary，新记录标题为“材料核验建议”；没有新字段的旧记录保留“模型审查建议”标题和原内容，不批量改写历史记录。不把后端生成的正确提醒说成模型自主学会识别边界。

## 版本和固定条件

- origin/main为9907c642；叠加基线6cc6203f9db6243113d7dee50f47d9ef3f0f3ff8（PR40后端上下文修复）。隔离工作树A:/audit-agent-suggestions，分支codex/review-business-suggestions；即时基线另用A:/audit-agent-suggestions-baseline。
- 候选运行时代码9a9a3f0。随后27ccd0e只合入PR40已交付验证文档；产品代码与已审查/运行版本相同。
- 复用scenarios-20261117-extra原季度/不足整季度两题及其extra-v1评分、既有用途同义口径；每题各3次、独立SQLite。原session严格检查额外保存，不覆盖原分。
- glm-4.5-air、既有GLM配置、演示采购制度v1.0、6轮、8192tokens、服务商默认温度。提示词、制度、任务、审批/发信权限、JSON解析和范围校验均未改。
- 先检查现有运行已结束，再通过原工作树共用optimization-running.lock串行运行即时基线6次及候选6次，无重复调用。两组实际system hash同为bbb48fa40f30a112fa7f254faf5df6ffb2812cd23b6168b96fe9c5fc6663cd23，计划保存制度/题目/runner/源码hash。

## 逐题对照

完整产品任务包括有效审查、业务终态及负责人保存建议。原模型草稿另判，不把两者合并宣称模型准确率。

| 场景 | 11月17日历史业务/完整 | 本轮即时基线业务/完整 | 候选业务/完整 | 候选原模型草稿及业务 |
|---|---|---|---|---|
| 12个月整季度 | 2/3、2/3 | 3/3、3/3 | 3/3、3/3 | 2/3 |
| 10个月不足整季度 | 3/3、0/3 | 3/3、0/3 | 3/3、3/3 | 0/3 |

即时基线与候选首提材料/逐字引文均6/6正确，均无有效提交前错误反馈。按完整产品任务，基线首次正确3/6、反馈后正确0/6、最终失败3/6；候选首次正确6/6、反馈后正确0/6、最终失败0/6。这里的“首次正确”包含后端生成展示建议，不能当成原模型草稿正确。

三次不足整季度均保留billing_period=quarterly、总额null、needs_clarification，仅一个billing_period问题。实际保存建议均为：“待澄清。预计总额待确认。期限不足整计费周期，请确认实际收费口径。审批和发信仍须负责人确认。”

三次正常对照均2400.00元、ready_for_review、无questions。保存建议均为：“材料核验完成，待负责人审批。预计总额 2400.00 元。审批和发信仍须负责人确认。”

候选quarterly Trial1原模型误称缺具体软件名；partial-quarter三次原稿均未要求确认不足整季收费，Trial2/3还误称材料完整。四次草稿失败全部保留。候选原草稿及业务合计2/6，展示建议及业务6/6；改善来自后端一致性约束。历史提示词不同，主对照用本轮相同提示词的即时基线，不把历史2/3与候选3/3当成单项改动的因果证据。

## 工程、数据库与展示核验

公开intake→worker→detail及HTTP测试先2失败，复现错误摘要直接展示；实现后相关44项通过。Ruff、runtime skills、diffcheck通过；全量gate357 passed、11既有live skipped。默认Anthropic无key，通用judge跳过；以上GLM实验独立显式运行。

固定9a9a3f0独立Standards/Spec均无可操作发现。新增测试核对完整公开链路、回执与保存结果相等、10个月批准被拒、12个月不新增追问和详情HTTP展示。新旧两组12/12只读SQLite材料/审查/任务状态与observed一致，候选6/6回执与保存结果一致；均无审批决定、结果通知或补件发送尝试。HTTP验证不等于浏览器、用户或专家验收，本轮未做真实收发。

即时基线24次客户端调用，输入34658、输出7502tokens；候选24次，输入35440、输出7270；本轮48次、输入70098、输出14772。费用及SDK内部重试未知。各三次仅描述本组，不推断线上总体准确率。

## 本地完整证据与后续

证据在A:/audit-agent-eval/data/procurement-acceptance/，原scenarios-20261117与-extra保持原样：

- optimization-suggestions-baseline-20261120：即时基线plan/results，每题独立SQLite及stage-1调用/解析前响应/observed/job/verdict。
- optimization-suggestions-v1-20261120：同样的候选原始证据，以及assessed-results.json、summary.json和report.md；report逐次列出首次参数/引文、错误反馈、有效回执、实际终态和保存建议。
- optimization-suggestions-tools-20261120：run.py复用原runner，共用独占锁、防覆盖；assess.py只读SQLite和原始轨迹；semantic-labels.json为助手逐条阅读后的判断；report.py只生成报告，无额外模型调用。

后续按用户授权已创建#42金额格式、#43JSON有限纠正、#44多轮材料、#45引文质量、#46评分校准；父#32/#34/#35/#36保留。本轮只做#41，不因为本组展示一致性通过就合并未验收父PR或宣称所有优化完成。PR叠加PR40并保留draft；最终发布SHA、独立文档复核和最新CI在交付记录核对。
