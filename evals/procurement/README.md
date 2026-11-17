# 采购评测首条任务

需求入口：[父票 #32](https://github.com/qiqiqia777/audit-agent/issues/32)、[当前 #33](https://github.com/qiqiqia777/audit-agent/issues/33)。后续报价/多轮/重复Trial和独立τ²-bench分别在 #34–#37。

在仓库根目录运行（已安装项目开发依赖）：

```powershell
python -m evals.procurement.runner --output data/procurement-acceptance/eval-offline-001
python -m evals.procurement.runner --live --env-file '路径/.env' --output data/procurement-acceptance/eval-live-001
```

默认模式使用固定ScriptedClient，不联网。`--live`显式读取现有邮箱工程兼容的 `GLM_API_KEY / GLM_BASE_URL / GLM_MODEL`，调用真实采购worker；只发送Task中的虚构材料。无需真实邮箱配置，不接SMTP/IMAP。输出目录必须不存在，失败运行保留，重跑换目录。

`software-per-seat.json`固定输入和工程预期：5席、12月、每席每月120元。它与离线脚本的答案分别维护，尚待用户人工核对。全部13个必需检查通过才成功，包括字段、精确金额、原文证据、已完成模型审查、待负责人审批、零决定/零发送尝试。Grader不评价建议文案质量；一个Task一次Trial不能推断统计准确率或公开Benchmark分数。

输出包含：

- `summary.md` / `results.jsonl`：人读汇总、机器判定，失败退出码1。
- `trial-1/task.json` / `observed.json` / `application.sqlite`：固定输入与真实业务终态。
- `trial-1/calls.json`：每次模型请求的系统提示、工具定义、参数、原始响应和工具反馈；异常只记类别。
- `trial-1/job.json` / `result.json`：worker结果、Trace、逐项实际/预期及相对证据引用。

报告记录Task/Grader版本、Task摘要、源码SHA及dirty标记、模式/模型和制度版本、调用数及耗时。Token/费用暂为null；服务商SDK内部重试未单独计数，不将调用数当作网络尝试次数。失败时Trace可能为空，以calls.json与数据库错误类别定位，不把基础设施错误自动归因模型。

校准与回归：`python -m pytest evals/deterministic/test_procurement_benchmark.py -q`。当前仅覆盖正确终态、错误/缺失金额、错误席位、缺原文证据、模型/数据库异常与CLI报告/防覆盖；尚无人工标注集、误判率、保留测试集或多Trial稳定性结论。

模型调用异常在 `worker_error` 记录；Store/worker外层或取证失败在 `harness_error` 记录，只保存类别，均返回失败并保留可写的报告。若输出目录本身不可创建/写入，则无法保证落盘，直接非零退出；参数或配置无效也在运行前拒绝，不计成已执行Task。

开发遵循 [仓库流程](../../docs/development-workflow.md)，独立工作树与codex/分支、先失败测试、离线gate、独立Standards/Spec审查、PR最新CI。人工核对和合并状态记录在Issue/PR，现有automation不变。
