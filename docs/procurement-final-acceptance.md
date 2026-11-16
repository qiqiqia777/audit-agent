# 采购审批助手最终交付验收

核对日期：2026-11-16。对应 [#19](https://github.com/qiqiqia777/audit-agent/issues/19)、
父 [#3](https://github.com/qiqiqia777/audit-agent/issues/3) / [#4](https://github.com/qiqiqia777/audit-agent/issues/4)。
范围依据 [PRD v1.0](08-procurement-approval-requirements.md)、[术语表](../GLOSSARY.md) 与
[职责 ADR](adr/0001-procurement-workflow-ownership.md)。制度为自编演示制度；交付面向本机求职展示和个人使用。

## 交付版本与安装

复用 `A:\audit-agent-install`、`codex/issue-19-install`、原 PR #22。
原 baseline 为 `f7459bbe4aaf6776632f9340db072a4e6077c2ea`，集成 main
`25e02b6a5b64e3989e185aa1cb609d834dc8830d`，安装取证源码为合并提交
`843e9aa168607cbfaf2978f8afa62b6f8cc1fd00`。本票只补文档、安装与证据，没有新增产品、依赖、验证脚本、CI 或权限变更。

2026-11-15 的 [首次干净检出调查](procurement-install-verification.md)保留；本次在集成版本上
新建第二个完整虚拟环境，从 wheel 安装运行及 dev 依赖，未复用 editable 的 site-packages。
wheel SHA256 为 `152af21d91c58a14c1af02cd2426afcbc6e0385815a7bcb8e0959400051ddfe2`。
包含 `email_agent` 的 Store、邮箱、审查、Web 模块及 `minihermes/ops/procurement_policy.json`。
三个 console entry points 均能执行 `--help`；`pip check` 无依赖冲突。
实际导入路径经断言位于新 venv 的 `Lib/site-packages`，运行目录在独立数据目录，不从源码目录偷取模块。

安装及公开复演命令见[本地部署](procurement-local-demo.md)。原始探针、日志、名册、回执和数据库保留于
本机 `data/procurement-acceptance/install-20261116/`，账号、密钥、真实邮件编号不上传。
本轮真实安装链路：虚构设备申请经真实 SMTP 自发自收，原消息复制到本次独立 IMAP 文件夹后，
由已安装的 `procurement-inbox` 实际入库；`procurement-review --glm-compat --once` 调用真实 GLM，
完成材料审查并得到100.00元。已安装的 `procurement-web` 实际监听回环端口，HTTP登录/预览/确认批准后，
通知状态sent，真实IMAP核对原Message-ID或X-Audit-Message-ID、发件人、完整主题及完整正文，
仅匹配1条结果邮件；只读复核没有重发。没有新增浏览器或人工QA。

终止本轮邮箱/Web进程后，在同一DATA_DIR启动两个新进程：真实申请仍approved/sent、仅1条通知尝试、
IMAP游标不变。另用公开Store API构造一条模拟已成功发送、等待3600秒的软件补件记录，
两进程重启后整条记录（含sent_at=1794821866.3670015、due_at=1794825466.3670015）完全不变。
该等待记录没有实际SMTP；真实60秒等待与回复证据沿用#17，不混淆两者。
结束后本轮所有子进程均停止，数据和原消息保留。[脱敏安装摘要](install-20261116-summary.json)。

## 六段现场流程与证据

这些结果由分阶段真实链路、实际浏览器、用户 QA 和受控回归共同覆盖；没有声称六段在同一份数据库里一次连续跑完。
各报告中的申请编号仅在各自独立数据目录有效，不可跨现场拼成同一申请。

| PRD 段 | 预期与实际 | 可核验依据及边界 |
| --- | --- | --- |
| 1：软件缺报价口径、条款和部门历史 | 120元/月先补口径；同款历史已批仍不得豁免本次用途；摘要带原申请号，其他部门不可见 | [#15](procurement-case-scope-verification.md) 的 HTTP、7 张 IAB 截图及用户 QA；[#16](procurement-software-browser-verification.md) 的未知报价预览；[真实模型/邮件往返](procurement-model-verification.md)。历史样例是虚构受控数据 |
| 2：确认补件、A 等待时 B 办结、重启 | 实际补件 SMTP/IMAP；B 决定发生在 A 的60秒截止前，结果实际收到；同目录主进程重启保留原 sent_at/due_at | [#17 报告](procurement-wait-browser-verification.md)与[真实摘要](runtime-browser-20261115/mailbox-main-success-20261116.json)。本次真实主进程重启发生在截止后；截止前重启和页面状态另由既有 IAB/用户 QA、受控回归覆盖 |
| 3：到期单份催办、回复7200、撤销及幂等 | 真实60秒维护线程只生成一份草稿；真实回复接回 A、模型得7200；同 Message-ID 实际 IMAP 重放不改申请，旧催办 HTTP 409 且0新增 SMTP | 同 #17 报告/摘要；催办未实际外发，撤销和旧表单由 HTTP 及既有浏览器证据覆盖。并发先后顺序是受控测试，不宣称任意网络竞态均实测 |
| 4：改8席、旧页拒绝、新版通知 | 5→8席，7200→11520；旧版没有决定或外发，新版批准且真实收到结果 | [真实软件往返](procurement-model-verification.md)为模型/IMAP/SMTP/HTTP；[#16](procurement-software-browser-verification.md)为实际双标签页与用户 QA；[最终三表达](software-model-20261115/bounded-final.json)单独验证1440/1440/7200。原金额错误及修复阶段失败全部保留 |
| 5：归属歧义 | 选择前候选不改；负责人选定后只更新该申请 | [#17](procurement-wait-browser-verification.md) 的候选截图和用户 QA；[跨部门有效CSRF回归](../evals/deterministic/test_procurement_demo.py)。本段是受控入站与浏览器，不冒充真实歧义邮件投递 |
| 6：另一部门直接访问和审批 | 本部门可读，另一部门当前申请/历史详情404，审批拒绝；邮件只含本人当前申请 | [#15](procurement-case-scope-verification.md) 的IAB/用户 QA及HTTP拒绝；[Web回归](../evals/deterministic/test_procurement_web.py)比对准确通知正文及收件人，验证预览不发信、重复批准不再发 |

## D1–D21 对照

| 决策 | 交付或记录 | 依据 |
| --- | --- | --- |
| D1 内部使用 | 本机登录与部门名册 | [部署](procurement-local-demo.md)、[Web](../email_agent/procurement_web.py) |
| D2 个人使用/求职展示 | 双部门虚构演示、单个授权自发自收测试邮箱；未作多人正式服务承诺 | [演示入口/清单](procurement-manual-checklist.md)、本报告范围 |
| D3 三周目标 | 完整功能与交付物按原三周计划组织；不将自动化耗时算成人工投入 | [计划](procurement-implementation-plan.md) |
| D4 历史技术支持方案 | 已由 D7 采购场景取代，不再作为未完成需求 | [PRD](08-procurement-approval-requirements.md) |
| D5 页面、链路、可靠性和文档 | 待办、依据、草稿、决定、历史和发送记录；真实往返/重启/幂等；部署、架构、分层测试与复演步骤 | 六段表、[架构](procurement-architecture.md)、本报告和部署 |
| D6 84小时预算 | 保留每天4小时、每周28小时计划；没有记录实际人工工时达成 | PRD与计划；这是预算约束，不是测试结果 |
| D7 两类采购、到结果留痕 | 设备和软件共用邮箱状态、审批与发送记录 | [Store](../email_agent/procurement.py)、真实模型/邮件报告 |
| D8 邮件提交与会话补件 | 真实入站、补件请求及原会话回复接回 | 软件往返与 #17 报告 |
| D9 单级人工决定 | 模型仅提交建议，登录负责人作决定 | [模型工具](../minihermes/ops/procurement_review.py)、[Web](../email_agent/procurement_web.py) |
| D10 字段及费用 | 两类材料缺项、报价先澄清；7200/1440/11520；校验金额与原文数值 | [设备规则](../evals/deterministic/test_procurement.py)、[软件规则](../evals/deterministic/test_subscription.py)、[#16](procurement-software-browser-verification.md)、[数值回归](../evals/deterministic/test_procurement_amount_evidence.py) |
| D11 草稿与发送授权 | 预览不外发；负责人确认补件或决定并通知 | [Web回归](../evals/deterministic/test_procurement_web.py)、#16/#17 的浏览器/真实邮件证据 |
| D12 版本绑定 | 旧页409，无决定/通知；新页差异可见后决定 | #16 与六段第4段 |
| D13 制度与历史 | 演示制度v1.0、条款原文；本次缺项不受历史获批豁免 | [制度JSON](../minihermes/ops/procurement_policy.json)、#15 |
| D14 并行/重启续办 | A等补件时B办结，同目录重启，回复接回A | #17；重启时机见六段表，不隐去到期后重启边界 |
| D15 成功发送起算与撤销 | 默认172800秒，演示60秒；持久化原截止、唯一草稿、回复撤销和旧草稿拒绝 | #17、[补件回归](../evals/deterministic/test_procurement_followups.py)、[运行回归](../evals/deterministic/test_procurement_runtime.py) |
| D16 决定与通知分离 | 失败/未知/核实/补发保留原决定；六项真实SMTP/IMAP恢复，故障为适配层注入 | [#18](procurement-send-recovery-verification.md)、[六项摘要](recovery-browser-20261115/live-mail-summary.json)、通知/恢复回归 |
| D17 关联和候选 | 按会话/编号核对发件人；候选人工选定 | [补件回归](../evals/deterministic/test_procurement_followups.py)、#17 候选IAB/用户QA |
| D18 授权案例/本人通知 | 同部门同类已办结案例含类别/用途/金额/结论/原号；员工通知只含当前申请 | #15、[result_notice](../email_agent/procurement.py)、Web回归的完整收件人/正文断言 |
| D19 身份和部门 | 邮箱名册、密码哈希、服务端部门过滤、跨部门详情/审批拒绝 | #15/#17/#18、Web回归 |
| D20 职责与事件续办 | email_agent负责邮箱/状态/决定/投递，MiniHermes负责制度/案例/模型建议；没有第二套邮件调度器 | [ADR](adr/0001-procurement-workflow-ownership.md)、[架构](procurement-architecture.md) |
| D21 交付与证据区分 | 真实邮箱收信/补件/通知、受控异常分别记录；首次失败、修复与重验均保留 | 各分项报告、六段表和下节 |

## 验证、用户反馈及已接受边界

- 本轮集成源码的 Ruff（含邮箱和表达验收脚本）、两个运行时 skill 校验通过；五个开发 skill 的
  frontmatter 和工作流入口单独核对，未通过合并 PR #20 来改变流程权限。
- 历史决定迁移、旧补件迁移、缺历史时长不猜值、双角色并发迁移四项：4 passed。
  它们是构造旧库的回归，不声称迁移了真实生产旧库。
- 完整 `python -m minihermes.ops.release_gate`：315 passed、11既有live skipped，
  默认anthropic无活动key，judge skipped。显式GLM/真实邮件验收与这些跳过项分开记录。
- 用户已确认 #15 双部门案例、#16 两种报价/8席/旧页、#17 等待重启/候选/撤销、#18 四项核心恢复页面；
  反馈分别保存在分项报告。本轮没有新增浏览器或人工 QA，不把 HTTP 当浏览器，也不将反馈扩到未操作路径。
- 用户2026-11-16明确接受：缺历史等待时长且已送达的旧记录保留待核实、不自动催办、不重发。
  不猜历史截止、不补造迁移数据；详见 #18 报告。正常新发送仍按实际成功时刻计时。
- 自发自收测试没有证明跨服务商/多人生产环境；故障注入不证明服务商实际拒收；模型固定样例通过不保证任意表达稳定。
  暂无生产可用性、跨平台兼容、真实服务商故障或任意网络竞态的声明。

最终审查、发布 head 和最新 CI 由唯一关联 PR #22 记录。只有本票全部验收、独立双轴审查、
最新head检查通过并合入后才关闭 #19；父 #3/#4 再按各自原始条件核实，不能仅凭 PR 已打开判完成。
