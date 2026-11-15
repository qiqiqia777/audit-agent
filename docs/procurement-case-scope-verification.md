# 双部门案例与本次缺项检查（#15）

日期：2026-11-15。基线 f7459bbe4aaf6776632f9340db072a4e6077c2ea，分支 codex/case-scope-acceptance。
父任务 #3，依据 D13、D18、D19。本轮仅补独立演示样例与验收证据，未改审批、权限或模型规则。

## 已验证：HTTP 与本地规则演示

新增虚构的「演示软件」申请：5 席、12 个月、每席每月 120 元，明确缺业务用途。
同部门已有同款软件已批准历史「设计部历史出图」，另一部门有「销售部专用历史」。
新用例先因缺少该演示场景失败，再补入最小样例后通过。

test_same_software_history_keeps_current_purpose_required_and_department_private 通过公开 HTTP 和存储接口验证：

- 设计部当前申请显示本部门办结案例及可打开的原记录，不显示销售部案例。
- 即使历史获批，本次仍显示「请补充业务用途」，批准按钮禁用；直接 POST 返回 409。
- 申请没有生成决定，本地演示收件箱为空。
- 切换销售部后，列表没有设计部当前申请；直接打开当前与历史详情均 404，跨部门批准 POST 也 404。

样例仍采用独立演示数据库和本地收件箱。它不是新增真实模型调用或真实邮件投递证据；
既有真实模型/邮箱结果见 procurement-model-verification.md。

自动化结果：演示 HTTP 文件 2 项通过；全量 release gate 为 277 passed、11 skipped；
Ruff 与运行时 skill validator 通过。11 项跳过为既有真实模型用例，当前未配置活动提供商密钥；
judge 同样跳过，不能把 gate open 写成真实模型验收完成。

## 浏览器：受控演示证据已齐

早期内置浏览器首次创建标签页超时。恢复 inventory 后尝试使用现有 Edge 窗口，工具明确报告：
无法充分确定当前 Windows 浏览器 URL 以执行策略，并停止本轮 Computer Use。
当轮停止 UI 操作，没有将 HTTP 结果当作浏览器通过。

2026-11-15 追加验证时，官方 IAB 已可用，页面显示完整回环 URL。
复用原分支与基线，使用本工作树新建的 .venv（Python 3.12），核对解释器及模块导入均来自
`A:\audit-agent-case`。没有恢复此前停止的 Windows Edge 操作，也没有绕过 URL 识别策略。
在独立目录运行以下命令，通知只进入 SQLite 演示收件箱：

```powershell
.\.venv\Scripts\python.exe scripts/procurement_demo.py --directory data/procurement-acceptance/case-browser-20261115 --port 18115
```

实际浏览器登录、点击与导航如下，截图均为整页 JPEG，只含虚构资料及公开演示密码：

| 操作 | 实际观察与截图 |
| --- | --- |
| design / demo-only 登录，打开 #2 | 同款「演示软件」缺用途；已明确 per_seat，预计 7200.00 元，但仍提示「请补充业务用途」，批准禁用。同部门摘要显示软件订阅、设计部历史出图、1200.00 元、批准及 #5 链接，不含销售部历史。[缺项和历史同屏](case-browser-20261115/01-purpose-still-required.jpg) |
| 点击摘要中的 #5 | 原记录可打开，显示同款软件、设计部历史出图、1200.00 元及 demo-fixture 批准。[授权历史](case-browser-20261115/02-authorized-history.jpg) |
| 打开本部门演示收件箱 | 为 []；本轮没有批准或确认补件发送。[空收件箱](case-browser-20261115/03-design-empty-outbox.jpg) |
| 切换 sales / demo-only 登录 | 列表只有销售部 #4，没有设计部当前 #2 或历史 #5。[销售部列表](case-browser-20261115/04-sales-list.jpg) |
| 用销售部会话访问先前已打开的 #2 地址 | 显示 404 Not Found。[当前申请拒绝](case-browser-20261115/05-current-denied.jpg) |
| 用销售部会话访问先前已打开的 #5 地址 | 显示 404 Not Found。[历史原记录拒绝](case-browser-20261115/06-history-denied.jpg) |
| 从销售部列表打开本部门 #4 | 可读销售部专用历史、2400.00 元；没有设计部案例摘要或原记录链接。[销售部自身历史](case-browser-20261115/07-sales-own-history.jpg) |

禁用按钮没有通过修改 DOM 强行点击；缺项直接 POST 的 409、跨部门审批 POST 的 404、
决定未产生及收件箱为空由原有公开 HTTP 回归重新验证，区别于上表浏览器实际操作。
本轮先复跑演示文件 2 passed；完整 gate 再跑为 277 passed、11 live skipped，
Ruff 和运行时 skill 校验通过；anthropic 无活动 key，judge skipped。
上述自动化走查不新增真实模型或真实邮件投递，不等同于用户人工 QA；用户反馈见下节。

手动复演可在新目录运行 python -m scripts.procurement_demo --directory data/procurement-acceptance/case-check-new --port 8093，
打开 http://127.0.0.1:8093/ ，用 design / demo-only 登录。
在申请列表逐一打开，找到缺业务用途但费用口径明确的「演示软件」（初次新建目录通常为 #2）。
确认缺项、禁用的批准按钮、本部门历史链接和原记录；切换 sales / demo-only，核对列表及直接访问拒绝。
每轮用新目录以保留已有证据，不清空运行数据。

## 用户人工 QA：通过（2026-11-15）

用户在本机演示服务 `http://127.0.0.1:18115/` 自行检查后分两次确认：

- 设计部当前 #2 提示补业务用途、批准按钮不可点击；同部门历史摘要显示
  「设计部历史出图 · 1200.00 元 · 批准」，点击编号能打开历史原记录。用户反馈「是的符合」。
- 切换 sales 后列表只有销售部 #4，不含设计部 #2/#5；直接访问设计部当前 #2 和历史 #5
  地址均显示 404。用户反馈「是的」。

这些反馈仅确认上述页面行为，不代表用户验证了直接 POST、真实模型或真实邮件。
直接 POST 拒绝和无决定/通知由已记录的 HTTP 回归覆盖。#15 的约定验收项及人工 QA 已齐，
可在最终审查与最新 CI 通过后通过原 PR #21 合入闭环；父 #3/#4 仍等待其他子任务。
