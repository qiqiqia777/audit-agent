# 报价歧义提取指令：两版真实模型实验

2026-11-19；第一子任务仅修改 `minihermes/ops/procurement_review.py` 的提取提示词。需求来自 [优化方案](procurement-agent-optimization-plan.md)，沿用 #34 报价/缺项事项上下文及本轮本地交接；没有新增评测模块 Issue。

## 结果及交付状态

| 场景 | 原整题 | 提示词 v1 | 提示词 v2 | v2 首提正确且未获错误反馈 | v2 反馈后成功 | v2 最终失败 |
|---|---|---|---|---|---|---|
| 歧义报价 | 0/3 | 1/3 | 3/3 | 3/3 | 0/3 | 0/3 |
| 明确每席月价 | 3/3 | 3/3 | 3/3 | 3/3 | 0/3 | 0/3 |
| 明确全部席位月价 | 3/3 | 2/3 | 2/3 | 2/3 | 0/3 | 1/3 |

v2 歧义三次均在首次提交省略 `price_basis` 及其证据，保留金额120、monthly、5席、12个月、对象及用途；保存总额为空，状态 `needs_clarification`，只追问报价覆盖范围。明确单席三次7200，明确全部席位成功的两次1440且无新增追问。表中正确包含材料、逐字引文、业务检查及保存建议语义；语义由助手复核，尚无独立业务专家标签。

**整体验收尚未通过：v2 是8/9，明确全部席位仍未达到3/3。保持草稿，不合并，不关闭相关事项，不开始后端引文校验。** 只描述这组小样本，不能推出总体准确率或生产稳定性。

## 固定条件与源码

- 基线 `7a1ba1360a15efc0055efb704c8f4fab3e5874c0`，来自未合并的 [草稿PR38](https://github.com/qiqiqia777/audit-agent/pull/38)。当前改动叠加该分支；不重复提交评测模块。
- v1 `9e61c1e44a572e3114ec3c0f41027476e17154f8`；v2 `da4797069a7fa0b93952e9d32f06a3fda0e40d51`。只有提取提示词改变，工具/后端/制度/模型/参数未变。
- glm-4.5-air，既有 GLM 兼容配置，演示采购制度v1.0；原三题各3次，每次独立SQLite，max_iterations=6、max_tokens=8192、服务商默认温度。员工脚本不变，无真实邮件/决定/发信。
- 复用基线 `scenarios-20261117/session.py` 的 `run_stage`。原严格评分保留；前后统一用基线已经采用的 `scenario-v1-semantic-purpose-v2`（出图/用于出图）重评，不改变其他判定。建议语义另记，不覆盖原整题分数。
- 每版 `plan.json` 保存源码、题目/评分版本及制度、提示词文件、原runner和评分器哈希；独占锁避免并发，拒绝覆盖已有版本。基线/失败轨迹未更改。

## 失败参数及归因

v1 歧义Trial1首次提交 `amount="120元/月"`，漏 `billing_period`；摘要还追问已明确的计费周期。工具连续返回金额数值校验错误，最终材料空、7个问题、审查failed。Trial2同类失败；Trial3在引文反馈后成功。v1明确全部席位Trial2出现JSONDecodeError，完整9次只通过6次。

v2补充不同金额/席位的示例，明确金额为纯数字字符串、元/月映射monthly、未知范围从材料及证据同时省略。歧义三次首提及引文均正确，没有错误反馈。

v2明确全部席位Trial2首提材料字段正确，但 `evidence.billing_period="monthly"` 不在员工原文；两次引文错误反馈后，第6次客户端响应的 `submit_review` 参数含破损的 `clause_ids` 数组/对象，解析报 `Expecting ',' delimiter`。最终只剩入站阶段提取的amount/monthly/all_seats，审查failed、总额空、没有已保存的本轮建议。**不因数据库已有部分金额而计成功，不以重跑替换失败。** 原因可定位为引文提交及JSON解析恢复链路，不能据此断言服务商、模型或传输责任。

## 证据入口

完整证据保留在独立工作树 `A:/audit-agent-eval/data/procurement-acceptance/`（gitignored）：

- `scenarios-20261117/` 及 `scenarios-20261117-extra/`：原始基线，未覆盖。
- `optimization-prompt-v1-20261119/`：9次，`report.md`、`semantic-review.md`、`baseline-diagnostics.json`、`assessed-baseline.json`、`assessed-results.json`。
- `optimization-prompt-v2-20261119/`：同上9次；另有 `invalid-tool-arguments.json`，包含两版解析前失败参数。
- 每题目录有独立 `application.sqlite`；`stage-1/` 保存 `calls.json`、`wire-responses.json`、`job.json`、`observed.json`、`verdict.json`、`diagnostic.json`，分别定位首次提交、引文、每次反馈及终态。
- `optimization-progress.md`：本轮追踪、阻塞及恢复入口。原报告部分文字与当前结构化基线不一致，本轮按九份保存数据提取，原报告不覆写。

两版各9/9数据库只读核对与observed材料/审查一致；负责人当前详情模板读取 `review.model_summary`，每题报告展示该实际保存原文。失败时无本轮保存建议。未把源码核对称为浏览器验收。

v1可见模型调用44，输入token66937、输出14480；v2调用43，输入60277、输出9943。费用及SDK内部网络重试未知。

本地复核（在仓库根目录、设PYTHONPATH为本工作树）：

```powershell
& A:/audit-agent-list/.venv/Scripts/python.exe data/procurement-acceptance/optimization-prompt-v1-20261119/summarize.py
& A:/audit-agent-list/.venv/Scripts/python.exe data/procurement-acceptance/optimization-prompt-v1-20261119/summarize.py data/procurement-acceptance/optimization-prompt-v2-20261119
```

以上命令只读已有轨迹和SQLite并生成派生报告，不调用模型。另开模型实验必须使用新版本目录，不重新运行旧版run.py覆盖数据。

## 工程检查及审查边界

- 针对性：`test_procurement_model_review.py` + `test_procurement_amount_evidence.py`，32 passed。
- v1/v2分别全量release gate：324 passed、11既有live skipped；默认Anthropic无key，通用judge跳过。它与本轮真实GLM场景分开计证。
- Ruff（minihermes/evals/email_agent/scripts/procurement_demo.py）、runtime skills及diffcheck通过。提示词效果由真实场景比较验证，未加只能断言提示词文字的测试。
- 独立Standards审查产品v1/v2均无发现。独立Spec识别v1歧义失败；v2歧义改善，仍保留正常对照解析失败。最终文档/提交复审及远端最新CI在交付记录中核实，不把工程绿灯当Agent验收通过。

恢复时先读优化进度、运行锁和当前进程。第一子任务未整体验收；后续提示词实验须另记版本，解析恢复属于方案后续独立改动。后端引文校验需用旧失败参数回放并再跑相同九次，不能混入本轮提示词成绩。
