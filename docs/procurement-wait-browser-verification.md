# 等待、重启、催办与候选分配验收

2026-11-15（Asia/Shanghai），Refs [#17](https://github.com/qiqiqia777/audit-agent/issues/17)、父 #4。
本轮复演现有行为，新增跨部门分配 HTTP 回归和浏览器证据，没有修改产品行为。
证据来自虚构资料、规则检查、本地演示收件箱；没有新增真实模型或真实 IMAP/SMTP 证据。

## 环境与复演

独立检出 `A:\audit-agent-runtime`，origin 已核对为 qiqiqia777/audit-agent，
分支 `codex/issue-17-runtime`，基线 `f7459bbe4aaf6776632f9340db072a4e6077c2ea`。
新建 Python 3.12 虚拟环境，已核对解释器和 email_agent、scripts 导入均来自本检出。
实际使用 IAB 浏览器登录、点击及填表，页面 URL 可识别；没有重试之前停止的 Windows Chrome 操作。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e '.[dev]'
.\.venv\Scripts\python.exe -X utf8 -m scripts.procurement_demo --port 18117 --directory data/procurement-acceptance/runtime-browser-20261115
```

打开 `http://127.0.0.1:18117/login`。公开虚构账号 design / sales，密码均为 demo-only。
下述截图捕获于集成 #15 前的原 head 112a486：当时 A 为软件 #2、B 为设备 #1，额外候选为 #5/#6。
当前集成后的全新空目录中，缺用途申请占用 #2；应选择报价口径未知的软件 #3 作为 A、设备 #1 作为 B，
额外软件候选为 #6/#7（销售部历史 #4、设计部历史 #5）。复演回复/催办时使用当前申请编号，
不要照抄历史截图的 #2；归属不明候选还可能包含缺用途 #2，按页面实际候选核对。
重启使用同一命令与目录，保留数据库；开始另一轮请指定全新独立目录，不清理已有资料。
本轮进程均已停止。重启使旧登录会话失效，重新登录后继续查看原申请。

## 逐步实际结果

| 步骤 | 浏览器操作及核对 | 证据 |
| --- | --- | --- |
| 1 | design 打开 A，点击发送补件请求；页面显示已发送，本地收件箱增加一封补件 | [已发补件](runtime-browser-20261115/01-request-sent.jpg) |
| 2 | A 等待期间打开 B，批准并通知；B 已批准且通知已发送，收件箱第二封只含 B 的结果 | [B 办结](runtime-browser-20261115/02-parallel-device-approved.jpg)、[收件箱](runtime-browser-20261115/03-outbox.jpg) |
| 3 | 停止本轮端口所属演示进程，以相同目录和命令重启。只读 SQLite 快照核对 A 的原发送时间和截止完全不变；重新登录看到原补件与到期催办 | [重启后](runtime-browser-20261115/04-after-restart.jpg)、[状态摘要](runtime-browser-20261115/state-evidence.json) |
| 4 | A 发送成功至截止为真实经过的 60 秒；两次刷新后只有一份待确认催办。保留该旧标签页 | [一份催办](runtime-browser-20261115/05-one-reminder.jpg) |
| 5 | 另一标签页填写编号 2，提交“每席位每月120元”；A 变为版本 2、7200 元，旧催办已撤销 | [回复接回 A](runtime-browser-20261115/06-reply-cancelled.jpg) |
| 6 | 回旧标签页点击确认发送催办，得到 409“草稿已撤销、已发送或申请已更新”；收件箱仍只有步骤 1/2 的两封 | [旧催办拒绝](runtime-browser-20261115/07-stale-reminder-rejected.jpg) |
| 7 | 从公开 Store 入口重放步骤 5 相同 Message-ID、发件人、正文及申请号的事件，A 的完整 detail 不变，版本仍为 2、邮件历史仍两封。此步骤是受控模块验证，不是浏览器或真实邮件重放 | [状态摘要](runtime-browser-20261115/state-evidence.json) |
| 8 | 另在 #5 发送补件后离开详情页；只读 SQL 观察到维护线程在 60 秒截止后生成一份草稿，没有再次访问详情页来触发生成 | 同上 without_page_refresh，原 sent_at=1794727433.4465744，due_at=1794727493.4465744；观察于 1794727512.059305 |
| 9 | 在部门列表留空编号、提交“改成9席”，出现 #2/#5/#6 候选。选择前只读快照显示所有申请材料/金额/版本不变 | [候选列表](runtime-browser-20261115/08-ambiguous-candidates.jpg) |
| 10 | 另一标签页切换 sales，只看到销售部 #3，没有设计部候选；在保留的设计部候选页提交分配，403，记录不变 | [销售部列表](runtime-browser-20261115/09-sales-no-candidates.jpg)、[旧会话拒绝](runtime-browser-20261115/10-cross-session-assignment-rejected.jpg) |
| 11 | 切回 design，选“归入申请 #5”；候选待办消失，#5 变为版本 2、9 席，#2/#6 仍为 5 席，其他申请完整行不变 | [分配后列表](runtime-browser-20261115/11-assigned-inbox.jpg)、[所选记录](runtime-browser-20261115/12-selected-only.jpg)、状态摘要 |

步骤 3 的 A 原 `sent_at=1794727303.7662349`、`due_at=1794727363.7662349`；
步骤 2 的 B 决定时刻为 15:21:52 CST，仍早于 A 截止 15:22:43 CST。
时间戳使用 Unix 秒；页面的原始决定字符串使用 UTC，本段换算为本地时间。
步骤 8 运行的是演示 main，它调用与采购邮箱 main 相同的 maintain_followups；
没有把它写成真实采购邮箱轮询进程或真实收信已经验收。

步骤 10 的浏览器 403 由切换账号后的旧 CSRF 触发，单独不能证明部门分配查询的授权检查。
新增 `test_other_department_cannot_assign_pending_change_with_valid_csrf` 使用 sales 的有效 CSRF
提交设计部 change key 和候选编号，返回 404，所有原申请及待分配事件均不变。
该 HTTP 回归与浏览器走查分别留证。

## 验证与限制

实现前既有 runtime/demo 回归 9 passed；新增跨部门回归后 demo 文件 2 passed。
最终 Ruff、运行时 skill validator 和 release gate 的命令如下：

```powershell
$env:PYTHONUTF8='1'
$env:MINIHERMES_HOME='A:\audit-agent-runtime\data\procurement-acceptance\runtime-gate-home'
.\.venv\Scripts\python.exe -m ruff check --config pyproject.toml minihermes evals email_agent scripts/procurement_demo.py
.\.venv\Scripts\python.exe scripts/validate_skills.py
.\.venv\Scripts\python.exe -m minihermes.ops.release_gate
```

Ruff 和两个运行时 skill 校验通过；最终离线回归 **277 passed、11 skipped**。
11 项为既有真实模型用例；anthropic 无活动 key，judge 明确 skipped。
另行核对 PR #20 的开发 skill frontmatter 与入口，未合并流程/权限规则。

截图与脱敏状态摘要随文档提交。原始快照和临时观察/重放脚本只在本机被忽略的数据目录。
临时观察脚本第一次因假定 SQL 返回顺序而断言失败，改按 kind 核对后通过；产品代码未改。
回复/发送并发的两种先后顺序沿用 test_procurement_runtime.py 中受控事件回归。

本轮没有发现产品缺陷，不为验收制造行为改动。真实模型、真实邮箱、真实采购邮箱入口的
完整重启/续办及人工 QA 仍未补齐；本记录不替代父 #4 的真实测试邮箱现场条件。
该段为最初开发阶段快照；后续人工 QA 已收到，见下节。真实邮箱入口仍须单独核实。

## 用户页面 QA 补录

2026-11-15 16:20–16:33 CST，用户在独立 `runtime-user-qa-20261115-1600` / 18117
逐步确认以下场景。该场景 A 为 #6、B 为 #1，与前面助手截图编号分开：

- A 等补件时 B 可批准；同目录重启后重新登录保留原补件，两次刷新只有一份催办。
- 新标签页回复单席月价120元后显示7200元、催办撤销；旧标签页发送被拒绝，无新增催办邮件。
- 歧义候选 #2/#5/#6 选择前均5席；sales 只见销售部 #3，无设计部候选，旧设计表单分配被拒绝。
  design 刷新后选 #5，仅 #5 变9席，#2/#6 仍5席。

用户重复点击“改成9席”生成两个不同 Message-ID 的虚构事件，最终 #5 v3。
这不能当作相同 Message-ID 的幂等验证；演示按钮无防重复提交，原现场未清理。
只读原 SQLite/JSON 佐证重启前后等待快照相等：A 原 sent_at=1794730542.2157278、
due_at=1794730602.2157278；唯一 reminder 为 cancelled/未发送，A/B 本地 outbox 各一条。
用户页面确认来自当日会话，本轮未要求重做，没有将本地收件箱解释为真实 SMTP。

## 真实采购邮箱入口：本轮失败证据与依赖

继续复用原分支及 baseline f7459bbe；集成 main d4c34f641487e70220db71d89b628ab45fef5a74。
共享索引和 demo 回归发生冲突，保留 #15 缺用途/案例隔离与 #17 有效 sales CSRF 两项测试。
本轮实际读取并执行工作流检出的 implement、code-review、ship 文档，没有声称存在原生斜杠工具，
没有合入待用户审阅的流程 PR #20。

使用已授权自发自收账号，独立目录 `data/procurement-acceptance/runtime-live-20261115`，
测试文件夹 `audit-agent-17-a1d9f317dcac`，名册只有该测试账号。真实 SMTP 发送两封虚构申请；
只将匹配本轮唯一主题、发件人和正文标记的服务器收件复制到测试文件夹，保留 INBOX 原信。
随后由未替换网络客户端的真实 `email_agent.procurement_mailbox` main 在该文件夹轮询入库，
不是 ImapPoller._emit_email 手工注入，也不是演示 main。私下复用授权配置，不输出凭据。

```powershell
# 在本工作树、全新独立目录，配置仅为本次进程设置：
# DATA_DIR=<独立目录>，IMAP_FOLDER=<本轮测试文件夹>，POLL_INTERVAL_SECONDS=2
.\.venv\Scripts\python.exe -m email_agent.procurement_mailbox --env-file <已授权配置> --roster <本轮名册>
```

软件 A #1、设备 B #2 均真实入库，IMAP 游标推进至2。实际 glm-4.5-air 审查 B completed，
A failed/ValueError，在发送补件之前失败，未进入重启或60秒等待。A 输入包含5席、12个月、
120元及未知报价覆盖范围；期限使用“期限（月）”写法，不能据此假定确定性解析已识别。
原失败数据保留，不重新抽样挑选成功结果。另进行一次只读快照诊断，不写回审查结果、不计作验收重试：
模型依次读申请、制度、案例，第四次仅文字结束，没有 submit_review；仍 ValueError。
诊断中的文字对期限判断也有矛盾，不能当成有效结构化建议。

[脱敏失败摘要](runtime-browser-20261115/mailbox-main-failure.json) 随报告公开；完整虚构邮件、
逐次模型响应、名册、SQLite 仅留忽略目录。没有真实补件或结果通知外发。
本次进程已停止，测试文件夹及两封样例保留，无删除或移动原邮件；现有用户 QA 服务不变。

PR #23 已实现此类文字/空响应在原轮数预算内反馈后继续结构化提交的修复，并带有先红回归和真实表达证据。
该 PR 因新增验收脚本，按自动化授权明确留用户审阅，尚未合入 main。
本轮不复制一份修复到 #17 或合入该 PR 绕过审阅。真实链路在此依赖处停止，#17/PR #24 保持开放/draft。
解除条件：用户审阅合入 #23 后，将其主分支修复集成原 #17 分支，保留本次失败，重新验证真实补件、
同目录进程重启、原截止、60秒单份催办、真实回复接回及重复邮件；不要求重做已确认的页面 QA。

集成后相关 runtime/demo 11 passed；全量 release gate 278 passed、11既有 live skipped，
默认 anthropic 无活动 key，judge skipped。Ruff 与2个运行时 skill validator通过；
开发 skill frontmatter/入口另核对。解释器和 email_agent 导入均来自本工作树。
没有产品代码、依赖、CI、验证脚本或门槛变更，本轮只同步现有回归、用户 QA 和真实失败证据。
