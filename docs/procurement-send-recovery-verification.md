# 补件和结果通知的发送恢复

2026-11-15，Refs [#18](https://github.com/qiqiqia777/audit-agent/issues/18)、父 #4。
本轮确认并修复补件请求及催办发送失败后没有恢复入口的缺口，保存实际浏览器走查。
真实模型、真实邮箱和用户人工 QA 本轮均未新增；PR 和任务仍保留待验收。

## 基线、来源与隔离

独立 `A:\audit-agent-recovery`，`codex/issue-18-recovery`，origin 已核对为 qiqiqia777/audit-agent，
基线 `f7459bbe4aaf6776632f9340db072a4e6077c2ea`。解释器和导入来自本工作树的新 `.venv`。
主检出的 `email_agent/procurement.py` 原有恢复草稿被复用为 Store 层起点，非本轮从零编写；
仅复制到独立工作树后补齐页面、回归、旧 Message-ID 关联及保护，未修改原现场。
原文件复制前后及本轮浏览器结束时 SHA256 均为
`0ce883c1043ef20d3efe64658e335e7c7bf006743937545b6ccd2fec32846fb7`。
原浏览器材料、其他任务工作树均未带入提交。

提交前主分支合入 #15 后，同步了 `d4c34f641487e70220db71d89b628ab45fef5a74`；
原开发基线不变，集成基线另行记录为 d4c34f6。上游的用途缺项样例、原回归和人工 QA 文档均原样保留。

## 确认的缺口及修复

先复跑既有通知/runtime 用例 **14 passed**。新增 HTTP 回归后 **6 failed**：
明确拒收后没有补发入口，结果未知后没有核实入口，也没有逐次补件发送记录。
修复后新增文件的 **13 项**全部通过，覆盖请求/催办两种类型、两种故障、
核实已送达使用实际发送时刻、重复领取和旧记录迁移。

- 补件每次发送保存收件人、原正文、版本关联、发送人、Message-ID、记录时间、回执和核实依据。
- 明确失败可在看到原收件人和正文后补发；结果未知必须先填写依据，确认未送达后才允许补发。
- 已送达的补件须填写实际发出时间（本机时间），按原发送时保存的等待时长计算截止，不能从核实时刻重新延长。
- 按发送记录编号领取重试，一份表单只允许一个并发领取；旧版本或已结束等待不能再发送。
  Web 完成回调绑定本次 attempt_id；旧回调不能覆盖核实结果或新尝试。
  兼容旧调用只允许首个尝试省略编号，多次尝试后省略编号会拒绝。
  另先复现回复后旧核实表单仍能提交（302），再修复为 409，历史核实记录不被旧表单改写。
- 旧尝试的 Message-ID 仍用于原会话关联和自发邮件去重；不因重试覆盖当前编号而丢失历史锚点。
- 独立 Spec 审查发现：首次网络发送尚未返回时也可核实未送达并重试。补件和结果通知
  两条 HTTP 并发回归先各自失败，再用同数据库、同发送对象的 OS 文件互斥保护领取/网络发送/结果保存，
  核实入口也检查同一互斥。另一标签页在发送期间只能得到 409，不产生第二次投递。
  Windows 使用 msvcrt，其他平台使用 fcntl；不新增依赖，不在网络等待期间占用 SQLite 写事务。
  新增真实子进程回归：子进程持有互斥时核实被拒，终止该进程且没有完成回调后，
  OS 释放互斥，可重新核实中断结果。锁文件保留在数据库旁 `.delivery-locks/`，不得在运行中删除它们。
- 旧记录迁移幂等，已有发送与截止不变。没有保存等待时长的旧失败/未知记录不猜成 48 小时：
  可核实未送达后按当前配置补发；如确认早已送达，保留待核实，暂不推算原截止。这是明确保留的旧数据限制。

审批结果通知沿用原决定与独立发送记录。页面另补显示内容版本及发送人；补发不会重做审批。

## 浏览器复演

使用 IAB，所有资料为虚构采购、规则检查和本地 SQLite 收件箱。不会执行 SMTP/IMAP。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e '.[dev]'
.\.venv\Scripts\python.exe -X utf8 -m scripts.procurement_demo --port 18118 --directory data/procurement-acceptance/recovery-browser-20261115
```

从 `http://127.0.0.1:18118/login` 登录，design / sales，公开演示密码 demo-only。
本节截图在同步 #15 前的本轮提交 42adebc 上完成，编号 #2/#5/#6 分别是演示软件/项目甲/项目乙。
同步后全新目录会额外插入用途缺项的 #2，因此这三个对象分别变成 #3/#6/#7；
复演时按采购对象核对编号，使用相应新编号填写表单，不能把截图中的编号当成固定协议。
复演新一轮请使用新目录；不要删除既有资料。本轮只停止了核对属于上述命令的监听进程。
第一次旧登录表单提交出现 403，重新获取登录表单后通过；选项控件改用浏览器观察到的 combobox 角色定位。
这些工具/会话恢复不计为产品修复或通过证据。

| 场景 | 实际浏览器操作及结果 | 截图 |
| --- | --- | --- |
| 补件明确拒收 | #2 软件切“明确拒收”，发送补件后显示失败、版本 1、发送人/目标/正文/Message-ID，出现原内容补发预览 | [01](recovery-browser-20261115/01-followup-refused.jpg) |
| 补件单独补发 | 切成功后确认补发 #2，两次尝试保留，第二次已发送，申请仍未决定 | [02](recovery-browser-20261115/02-followup-retried.jpg) |
| 补件结果未知 | #5 切“连接中断”，发送后没有直接补发按钮，显示核实依据和实际发送时间入口 | [03](recovery-browser-20261115/03-followup-unknown.jpg) |
| 补件核实与恢复 | 填写受控断连后本地收件箱无消息的依据，确认未送达，出现预览；切成功补发，保留核实人 design 与依据 | [04](recovery-browser-20261115/04-followup-verified.jpg)、[05](recovery-browser-20261115/05-followup-recovered.jpg) |
| 审批结果拒收 | #1 设备批准后模拟拒收，已批准与失败并列；切成功单独补发，两次记录保留，原决定人与时刻不变 | [06](recovery-browser-20261115/06-result-refused.jpg)、[07](recovery-browser-20261115/07-result-retried.jpg) |
| 审批结果未知 | #6 先补齐单席报价，再批准并模拟断连；核实依据后确认未送达，切成功补发，原批准与核实记录保留 | [08](recovery-browser-20261115/08-result-unknown.jpg)、[09](recovery-browser-20261115/09-result-verified-retried.jpg) |
| 部门拒绝 | 切 sales 登录，仅有销售部列表；直接打开 design 的 #5 得到 404 | [10](recovery-browser-20261115/10-foreign-rejected.jpg) |

[脱敏数据库摘要](recovery-browser-20261115/state-evidence.json)仅含这组虚构资料，
四次成功本地投递按顺序归属 #2/#5/#1/#6，失败和模拟断连不产生本地收件箱记录。
催办恢复、重复操作、有效 CSRF 的跨部门拒绝、旧版本拒绝和迟到回调由 HTTP/公开 Store 回归覆盖，
本轮浏览器没有逐个复演这些提交；不将它们写成浏览器通过。

## 验证与剩余项

```powershell
$env:PYTHONUTF8='1'
$env:MINIHERMES_HOME='A:\audit-agent-recovery\data\procurement-acceptance\recovery-gate-home'
.\.venv\Scripts\python.exe -m ruff check --config pyproject.toml minihermes evals email_agent scripts/procurement_demo.py
.\.venv\Scripts\python.exe scripts/validate_skills.py
.\.venv\Scripts\python.exe -m minihermes.ops.release_gate
```

同步上游前离线回归 289 passed；同步后最终 Ruff 与两个运行时 skill 校验通过，
全量离线回归 **290 passed、11 skipped**（包含上游 #15 新增回归）。
11 项为既有 live 用例；活动 anthropic 无 API key，judge skipped。
开发 skill frontmatter 与流程入口另行核对通过；运行时 validator 不覆盖它们。

真实模型/API key 不在本轮配置，live/judge 跳过应与离线结果分开记录。
旧记录未知时长且已送达的恢复限制、真实邮箱/模型和用户人工 QA 仍未验收；保持 #18、父 #4 开放。
未修改依赖、CI、验证门槛、合并规则或权限，没有合并流程 PR #20。
