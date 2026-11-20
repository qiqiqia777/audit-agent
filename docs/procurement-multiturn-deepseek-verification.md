# 多轮材料提取：DeepSeek 既有行为验收（#44）

本轮只验收 #44，父 #35/#32；未修改产品代码、提示词、制度、工具 schema 或评分规则。实现基线与运行版本为 PR49 head `dc75582baf1abd47afc6f1a19e0bd18713cd4e76`（产品 f049491）。按用户最新队列叠加 PR49，保留其未合并依赖；未从 main 丢弃前序已验收功能。

## 结果

| 场景 | 2026-11-17 原始 GLM 整题 | 本轮 DeepSeek 整题 | 阶段与终态 |
|---|---|---|---|
| 缺用途 | 2/3 | 3/3 | 3/3 completed，仅 purpose 问题；7200 元 |
| 补充期限 | 1/3 | 3/3 | 初始仅 months 问题、总额空 3/3；补充12个月后清除问题、7200元 3/3 |
| 正常月付对照 | 1/3（原始严格分） | 3/3 | 3/3 completed、7200元、无问题 |
| 连续5→8→6席 | 2/3 | 复用 #43 DeepSeek 候选 3/3 | 5、8、6席各3/3 completed；7200/11520/8640元，无问题 |

历史列是原始未重评分数，含旧严格同义判定，模型及代码均不同，不能据此归因代码改善。本轮 extra-v1 接受“出图/用于出图”，原始严格 checks 单独保留。没有重跑或覆盖旧轨迹。连续席位复用上一轮同产品、模型、制度、提示词及预算的九个阶段，没有重复付费运行；其来源本地 d29f6f7 与当前运行版本的产品/loop/adapter 文件一致，可由两个 plan 的哈希核对。

本轮新增9个独立trial、12个阶段：业务12/12，保存建议12/12，首次正确12/12、反馈后纠正0/12、最终失败0/12；首提字段及逐字引文12/12。12/12只读SQLite当前/中间revision、review_jobs与导出一致，12/12提交回执与保存建议一致。零审批决定、零通知或补件发送尝试。未复现需要修改的产品缺口，因此不制造代码改动，也没有本轮修复或准确率提升声明。助手逐一阅读12份原稿及保存建议，按“只问实际缺项、无状态冲突”的有限标准均通过；不等于用户/专家标注。

本轮24次可见模型调用，输入36197、输出6788 tokens；SDK内部重试、金额费用未知。配置 deepseek-v4-flash，响应 model=deepseek-flash。6轮/8192 tokens、默认温度，原制度与任务、extra-v1 评分；system SHA256 `bbb48fa40f30a112fa7f254faf5df6ffb2812cd23b6168b96fe9c5fc6663cd23` 与前轮一致。本地凭证只确认存在，不记录密钥。

## 代表性轨迹

缺用途 trial1 首提保留 item=设计软件、seats=5、months=12、amount=120、billing_period=monthly、price_basis=per_seat，省略 purpose。没有工具拒绝；保存建议为“待澄清。预计总额 7200.00 元。请补充业务用途。审批和发信仍须负责人确认。”

补充期限 trial1 首轮省略 months，保留其他已知字段；保存“待澄清。预计总额待确认。请提供正整数订阅月数。审批和发信仍须负责人确认。”第二轮从员工“补充：订阅12个月。”提取 months=12，保留旧来源字段，任务 completed，保存“材料核验完成，待负责人审批。预计总额 7200.00 元。审批和发信仍须负责人确认。”首次参数与全部 evidence、trace、原稿均见 assessed-results.json。

没有新的失败样本。历史 GLM 服务失败、JSON失败及候选未运行标签仍保留，详见前轮报告，不计作本轮成功。

## 证据与复现

本地根 `A:/audit-agent-eval/data/procurement-acceptance/`：

- `optimization-multiturn-deepseek-v1-20261120`：plan.json、results.jsonl、9份独立SQLite和12阶段calls/wire/job/observed/verdict/original-session-checks。
- `optimization-multiturn-deepseek-tools-20261120`：run.py（从现有DeepSeek入口仅更换任务列表、计划分母及说明）、assess.py、semantic-labels.json、summary.json、assessed-results.json、独立审查记录。
- 复用 `optimization-json-deepseek-v1-20261120/latest-of-two-changes-trial-{1,2,3}`；参见 [#43 DeepSeek报告](procurement-json-deepseek-verification.md)。
- 历史 `scenarios-20261117` 和 `scenarios-20261117-extra` 原文件不变。

复现需新 output 目录，禁止覆盖：`A:/audit-agent/.venv/Scripts/python.exe A:/audit-agent-eval/data/procurement-acceptance/optimization-multiturn-deepseek-tools-20261120/run.py --repo A:/audit-agent-multiturn --output <新绝对目录> --expected-model deepseek-v4-flash`。入口使用共用排他锁；鉴权/资源错误停止整批。员工回复由原场景脚本驱动，未发真实邮件。

## 工程与交付

本轮实际重跑 release_gate：374 passed、11既有live skipped；默认Anthropic未配key，通用judge跳过。Ruff及runtime skills校验通过。产品未变，无新增单元测试。Standards/Spec独立审查与最新head CI在交付后追加。

无浏览器验收、真实发信、人工审批或用户/专家语义验收。#44指定场景证据齐备；PR保持草稿跟踪父依赖，不关闭父票、不合并、不暂停自动化。下一轮 #45 引文质量，之后 #46 评分校准；本轮不领取第二项。
