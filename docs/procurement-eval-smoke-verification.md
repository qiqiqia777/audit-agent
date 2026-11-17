# #33 采购评测首条贯通验证

日期：2026-11-17。父需求 [#32](https://github.com/qiqiqia777/audit-agent/issues/32)，当前任务 [#33](https://github.com/qiqiqia777/audit-agent/issues/33)。

## 实现与范围

独立工作树 `A:/audit-agent-eval`，分支 `codex/procurement-eval-smoke`，基线 `9907c64281b8b757c08bd82b31920a4e4da96bb1`。既有UI工作树及两个未跟踪文档未修改。

新增 `evals/procurement/runner.py`、固定Task、操作说明及确定性回归。运行现有Store/worker，无产品后端、审批/发送权限或新依赖变更。入口为 [采购评测说明](../evals/procurement/README.md)。

## 先失败、后实现

新增公开模块/CLI测试首次因 `ModuleNotFoundError: evals.procurement` 失败。首次实现又发现请求消息内的模型对象无法JSON序列化，导致worker失败；补齐序列化后通过。失败资料仍保留在本地 `data/procurement-acceptance/eval-debug-1`。

最初新增8项回归通过；独立审查后补至9项：成功执行worker、错误/NaN/缺失金额、错误席位/缺证据、模型失败、CLI失败非零报告、正常报告及禁止覆盖、数据库故障报告。Grader的正确轨迹与Task预期分别维护，尚不是用户标注集。

## 真实模型与离线证据

以下两次在干净提交 `186c00572111a54138282478831224b25af36386` 上执行；结果记录 `source.dirty=false`。其后增加了基础设施异常捕获及回归测试，最终代码只做了离线复演；该次真实模型证据对应此明确提交。

| 模式 | 样本 | 结果 | 检查 | 模型调用 | 耗时 |
| --- | --- | --- | --- | --- | --- |
| 离线ScriptedClient | 1 Task × 1 Trial | 1/1 | 13/13 | 见机器结果 | 见机器结果 |
| 真实模型glm-4.5-air | 1 Task × 1 Trial | 1/1 | 13/13 | 5 | 16.002秒 |

真实模型通过既有GLM兼容配置运行，不输出/提交凭据。输入为固定虚构申请：设计软件用于出图，5席、12月、每席每月120元。实际材料与工程预期一致，原价120，总额7200.00；审查completed、业务ready_for_review、decision=null、结果及补件发送尝试合计0。调用数是客户端create次数，服务商SDK内部重试未计数；Token/费用未采集。

本地完整结果（gitignored，保留原始失败和成功）：

- `A:/audit-agent-eval/data/procurement-acceptance/eval-offline-20261117-clean/summary.md`
- `A:/audit-agent-eval/data/procurement-acceptance/eval-live-20261117-clean/summary.md`
- 同目录 `results.jsonl`，以及 `trial-1/task.json`、`observed.json`、`application.sqlite`、`calls.json`、`job.json`、`result.json`。

每次新目录/新DB，报告逐项有实际值、预期值及相对证据指针。`calls.json`保存全部模型请求、响应和可见工具反馈；未仅保留最终成功。早期开发阶段的离线/真实模型通过样例分别保留在 `eval-offline-20261117-1` / `eval-live-20261117-1`，其源码标记dirty，不混作干净提交的运行。

## 本地工程检查

使用既有 `A:/audit-agent-list/.venv/Scripts/python.exe`，工作目录为本独立工作树：

- `-m pytest evals/deterministic/test_procurement_model_review.py -q`：基线9 passed。
- `-m pytest evals/deterministic/test_procurement_benchmark.py -q`：最终新增9 passed。
- `-m ruff check --config pyproject.toml minihermes evals email_agent scripts/procurement_demo.py`：通过。
- `scripts/validate_skills.py`：2个运行时skill通过；仓库开发入口未修改。
- `-m minihermes.ops.release_gate`：初次323 passed；审查修复后324 passed / 11既有live skipped；默认Anthropic无key，通用judge skipped。
- `git diff 9907c642...HEAD --check`：通过。

## 验收边界

这是一个采购自建Task的冒烟验证，不是统计准确率、稳定性或公开τ²-bench成绩。首票不包含40条样本、多Trial对比、提示注入专项或已校准文本judge；后续归属 #34–#37。

本轮未接SMTP/IMAP、没有浏览器页面改动；真实邮件/浏览器均不属于本票证据。Task和报告尚待用户人工核对，未声称人工QA完成。PR保持可审阅状态，独立审查与最新CI在Issue/PR补充，父票保持开放；未改automation。

## 独立审查修复与最终复演

Standards在初次范围无可操作发现。Spec发现一项P2：worker外层数据库/取证错误直接抛出，缺结构化失败报告。用公开CLI加sqlite3.OperationalError注入先复现失败，再修复为harness_error类别、可用证据、失败JSONL/Markdown及退出1；不记录异常正文。Windows测试读取报告时出现GBK解码失败，显式UTF-8后9项定向测试通过。输出目录自身无法写入时不能保证报告，边界已在README说明。

修复后干净代码提交 `f6fba937e1d34dc343cd2f57e746b8e1b36b30f5` 离线复演13/13通过，证据 `A:/audit-agent-eval/data/procurement-acceptance/eval-offline-20261117-final/`。真实模型证据仍明确属于上述 `186c005`，不把未重跑的最终异常处理包装冒充真实模型复验。最终完整双轴复审及CI结果以PR/Issue为准。
