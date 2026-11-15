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
首次空目录中 A 为软件 #2，B 为设备 #1，#5/#6 为额外软件候选。
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
保持 #17/#4 开放、PR 为 draft；人工 QA 尚未反馈，不声称全部验收完成。
