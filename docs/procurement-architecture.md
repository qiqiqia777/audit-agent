# 采购审批助手架构

本项目在同一安装包中包含 email_agent 和 minihermes。产品需求以 [v1.0](08-procurement-approval-requirements.md) 为准。

## 运行进程与职责

| 入口 | 实际组件 | 职责 |
| --- | --- | --- |
| procurement-inbox | ProcurementInbox、ImapPoller、maintain_followups | 接收入站事件、匹配申请与员工、事务保存原文与版本、检查补件等待到期 |
| procurement-review | work_once、review_request、run_loop、ToolRegistry | 独立领取持久化审查任务，读取制度和授权案例，执行模型审查并校验提交 |
| procurement-web | create_app、ProcurementStore、smtp_delivery | 负责人登录、部门范围检查、预览、决定、确认发送和核实发送结果 |

三个进程使用同一个 DATA_DIR/procurement/applications.sqlite。模型网络调用在 SQLite 写事务外执行。
模型服务使用进程文件锁限制同一数据目录的并发领取者，重启后重新排队中断任务。
邮箱维护线程只创建催办草稿，所有外发均经页面确认。产品采购流程使用事件类型、IMAP 适配与显式 SQLite 状态转移。

## 数据与可核对记录

| 表 | 保存内容与约束 |
| --- | --- |
| applications | 所属部门、员工、当前材料与版本、类别、审批决定与决定人/时间、通知状态 |
| original_mail | Message-ID 或 UID 对应的入站原文，重复键保持原记录 |
| incoming_changes | 补件原文、解析补丁、候选申请、最终分配目标 |
| revisions | 每次被替换的材料与审查快照，申请与版本联合唯一 |
| review_jobs | 申请版本绑定的审查状态、错误类别、模型结果和工具轨迹 |
| followups | 每轮补件/催办草稿、发送状态、编号、发送与到期时间、等待结束标记 |
| outbound_aliases | 服务商实际邮件编号与原申请的对应关系 |
| notification_attempts | 每次结果通知的内容、收件人、认领状态、邮件编号、回执及人工核实依据 |

员工由名册邮箱识别，负责人由登录身份映射到部门。详情、审批、补件归属和案例查询都使用后端部门约束。
模型工具没有部门或任意申请编号参数，仅接收后端已授权的快照。
模型可以提交材料及引用，不能执行批准、改权限或发信。

## 一次申请如何推进

1. ImapPoller 将邮件转换为 Event，ProcurementInbox 在游标推进前调用 intake 保存申请。重放同一 Message-ID 不新建记录。
2. intake 保存原文和确定性字段，创建绑定当前版本的 review_jobs。补件按会话或编号核对员工，歧义先保留候选。
3. work_once 领取任务。review_request 向模型提供 read_request、read_policy、search_cases、submit_review。
4. submit_review 校验字段、原文片段、制度及案例编号；confirmed_materials 阻止模型回退后端已核对的最新字段。规则函数重算金额。
5. finish_review 检查版本仍一致才保存；结果更新申请版本，旧页面表单失效。过时结果标为 superseded。
6. 负责人查看新版后决定。决定先保存，结果通知另行认领。失败或未知状态不会修改原审批决定。

审批提交、入站修改、补件归属和发送领取使用 BEGIN IMMEDIATE 串行化写操作。
模型审查结果产生的中间版本会留存，页面差异优先与上次已完成审查比较。

## 等待与恢复

补件请求明确发送成功后保存 sent_at 和 due_at。维护线程每秒检查到期且尚未结束的当前版本等待，
通过联合唯一约束只生成一份待确认催办。closed_at 保存等待结束，不覆盖原截止时间。
回复先提交时旧草稿撤销；发送先领取时保留可能在途的发送及其结果，随后结束等待。
这一区分以本地已接收事件的事务顺序为准，不声称知道尚未同步到本地的服务器来信。

结果通知在网络调用前保存独立尝试和邮件编号。明确失败允许预览后补发，未知结果需要人工核实依据。
发送已接受但 QUIT 时断连，不能把已完成的 DATA 提交当成未发送。无法判断投递时保持待核实。
当前通知流程不会用重新批准来代替补发。

## 配置和部署范围

当前支持在本机运行，Web 绑定 127.0.0.1。名册在仓库外维护，密码用 Werkzeug 哈希，凭据仅进入本地环境。
制度 JSON 随 wheel 分发，真实模型脚本只使用虚构采购资料。发件白名单继续由代码检查。
详细命令见 [本地部署](procurement-local-demo.md)。

浏览器走查、完整现场验收及剩余异常恢复见 [验收状态](procurement-acceptance-status.md)，不以架构描述替代验证结果。
