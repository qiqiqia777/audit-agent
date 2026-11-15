# 软件报价与旧标签页：浏览器验收

2026-11-15，Refs [#16](https://github.com/qiqiqia777/audit-agent/issues/16)、父 #3。
本轮交付浏览器操作与截图，未修改产品代码。真实模型表达补证、人工 QA 尚未完成，Issue 保持开放。

## 环境与复演

独立 worktree `A:\audit-agent-software`，origin 为 qiqiqia777/audit-agent，
分支 `codex/issue-16-browser`，基线 `f7459bbe4aaf6776632f9340db072a4e6077c2ea`。
Python 3.12 新建 `.venv` 并安装 `.[dev]`；已核对解释器和 email_agent 导入路径均在本检出。
使用 Codex 内置浏览器（IAB）实际登录、点击和填表；浏览器页面明确显示 URL。
没有操作之前因 URL 识别停止的 Windows Chrome，也未使用 HTTP 脚本代替本轮浏览器交互。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e '.[dev]'
$env:PYTHONUTF8='1'
.\.venv\Scripts\python.exe scripts/procurement_demo.py --port 18116 --directory data/procurement-acceptance/software-browser-20261115
```

所有资料虚构，规则检查，通知仅保存到 SQLite 本地演示收件箱。账号 design / sales，
密码 demo-only（公开演示账号）；本轮登录 design。浏览器共享登录会话，分别保留旧申请页、新申请页和收件箱三个标签页。
首次空目录的申请 #2 为演示软件、#5 为项目甲软件，均为 5 席、12 个月、120 元/月且口径未明。
复演请使用新的独立目录；本轮结束状态中 #2 已批准，不能把同一目录当作全新场景。

## 逐步骤实际结果

| 步骤 | 操作和观察 | 证据 |
| --- | --- | --- |
| 1 | 登录后打开 #2，版本 1，总额待核实，页面显示报价口径补件问题及待确认草稿，批准禁用；另一标签页收件箱为 [] | [初始页面](software-browser-20261115/01-unknown-basis.jpg)、[空收件箱](software-browser-20261115/02-outbox-before.jpg)；初始截图为视口，口径问题及禁用状态另由浏览器可访问性树核对 |
| 2 | 点击“发送补件请求”，显示已发送；刷新收件箱只有一条 #2 的报价口径补件请求，没有批准结果通知 | 步骤 5 的收件箱截图保留该唯一补件请求 |
| 3 | 指定编号 2，提交虚构回复“每席位每月120元”，版本 2 显示 per_seat、7200.00 元，批准可用；保留此标签页 | [7200 元](software-browser-20261115/03-single-seat-7200.jpg) |
| 4 | 新标签页打开同一 #2，指定编号 2 回复“改成8席”，版本 3 显示 11520.00 元；材料差异显示 5→8、7200.00→11520.00 | [新版金额差异](software-browser-20261115/04-eight-seats-diff.jpg) |
| 5 | 在未刷新的版本 2 旧标签页点击“批准并通知”，出现“申请已更新或已决定，请查看最新记录”；刷新收件箱仍只有补件请求，没有结果通知。新版标签页重新加载后仍未决定、批准按钮仍可用 | [旧版拒绝](software-browser-20261115/05-stale-rejected.jpg)、[旧版提交后的收件箱](software-browser-20261115/06-outbox-after-stale.jpg) |
| 6 | 在刷新后的版本 3 点击批准，页面显示 design 批准、已发送和一条结果发送记录；收件箱从一条补件请求增加为两条，仅新增一条 #2 批准结果 | [新版批准](software-browser-20261115/07-current-approved.jpg)、[最终收件箱](software-browser-20261115/10-final-outbox.jpg) |
| 7 | 从部门列表打开 #5，指定编号 5 回复“全部席位每月120元”，版本更新但仍提示口径待核实、批准禁用；未得到 1440 元 | [未识别表达](software-browser-20261115/08-unmatched-expression.jpg) |
| 8 | 在 #5 再回复“全部席位合计每月120元”，版本 3 显示 all_seats、1440.00 元，旧补件草稿撤销；本轮未批准 #5 | [1440 元](software-browser-20261115/09-all-seats-1440.jpg) |

步骤 7 是本轮实际发现的规则演示表达限制，不能省略后只宣称任意自然语言均通过。
源码 parse_materials 的自由文本规则当前要求“全部席位合计每月”；本轮没有调用模型，
因此不能据此判断真实模型能否理解省略“合计”的表达，也没有为通过验收扩展产品解析规则。

## 验证及边界

- 先复跑既有 `python -m pytest -q evals/deterministic/test_procurement_demo.py`：1 passed。
- Ruff（minihermes、evals、email_agent、scripts/procurement_demo.py）和运行时 skill validator 通过。
- `python -m minihermes.ops.release_gate`：276 passed、11 既有 live skipped；
  anthropic 无活动 key，judge skipped。MINIHERMES_HOME 指向本轮独立数据目录。
- 浏览器截图为 JPEG：03–10 为整页截图。只含虚构资料及公开演示密码，无真实凭据和员工信息。
- 保留既有 [真实模型与邮箱阶段报告](procurement-model-verification.md)，其中单席 7200 元、
  8 席 11520 元、旧表单拒绝及真实结果收件的历史证据未被改写。
- 本轮没有新增真实模型、IMAP/SMTP 或用户人工 QA。#16 的真实模型全部席位口径及表达变化仍需补证；
  本机没有为此配置新的模型环境，不能用本地规则的 1440 元替代真实模型结论。
- 该浏览器入口绕过生产模型审查，仅证明受控演示页面的交互；没有将它当作整个生产链路的验收。
  #16、父 #3/#4 保持开放，PR 保留 draft，Refs 而非 Closes。
