# 干净安装与 wheel 调查（2026-11-15）

Refs [#19](https://github.com/qiqiqia777/audit-agent/issues/19)、父 [#4](https://github.com/qiqiqia777/audit-agent/issues/4)，同时涉及父 #3 的最终证据汇总。
本记录只完成 #19 允许提前开展的安装调查，不是最终交付报告；#15–#18 和人工 QA 仍待完成。
未改变产品行为、依赖声明、CI、测试门槛或合并规则。

## 基线与隔离

- 独立 worktree：`A:\audit-agent-install`，分支 `codex/issue-19-install`。
- 实际核对 origin：`https://github.com/qiqiqia777/audit-agent.git`。
- 从最新 `origin/main` 创建，基线 `f7459bbe4aaf6776632f9340db072a4e6077c2ea`。
- Windows、Python 3.12.10；新建 `.venv`，没有复用其他检出的解释器或环境。
- 本机材料、临时名册、wheel 解包安装及数据库均在被忽略的
  `data/procurement-acceptance/install-20261115/`；构建产物在 `dist/`。
  没有复制真实凭据、运行资料或修改其他工作树的未提交文件。

## 已运行命令与结果

在该检出根目录运行（PowerShell，以下 Python 均来自新环境，构建 wheel 的命令除外）：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e '.[dev]'
.\.venv\Scripts\python.exe -m pip check
python -m pip wheel --no-deps --wheel-dir dist .
.\.venv\Scripts\python.exe -m pip install --no-deps --target data/procurement-acceptance/install-20261115/wheel-site dist/mini_hermes-0.1.0-py3-none-any.whl
$env:PYTHONUTF8='1'
$env:MINIHERMES_HOME='A:\audit-agent-install\data\procurement-acceptance\install-20261115\gate-home'
.\.venv\Scripts\python.exe -m ruff check --config pyproject.toml minihermes evals email_agent scripts/procurement_demo.py
.\.venv\Scripts\python.exe scripts/validate_skills.py
.\.venv\Scripts\python.exe -m minihermes.ops.release_gate
.\.venv\Scripts\python.exe -m pytest -q evals/deterministic/test_procurement_notifications.py::test_previous_decisions_migrate_idempotently evals/deterministic/test_procurement_notifications.py::test_concurrent_claim_and_restart_after_decision evals/deterministic/test_procurement_runtime.py
```

安装成功，`pip check` 无依赖冲突。Ruff 和两个运行时 skill 校验通过；release gate 的全量离线回归
为 **276 passed、11 skipped**。11 项为需要真实模型密钥的既有用例；活动提供商为 anthropic，
无 API key，judge 明确跳过。没有将 gate 的成功解释为真实模型或业务验收通过。
单独复跑的旧数据迁移、决定后重启恢复及运行维护测试为 **10 passed**。

安装时主要依赖版本：anthropic 2.8.0、openai 3.51.0、Flask 3.1.3、imap-tools 1.16.0、
pytest 9.2.0、Ruff 0.17.5。版本来自本轮全新解析，不构成锁版本或跨平台兼容保证。

开发 skill 尚位于未合入的 PR #20。另行核对了该分支五个 SKILL.md 的 name/description
frontmatter 和工作流文档入口；运行时 validator 不覆盖它们。实现、审查和 ship 文档已实际读取，
没有声称调用客户端不存在的斜杠工具，也没有为执行本轮工作合并流程规则。

## wheel 内容及运行检查

产物 `mini_hermes-0.1.0-py3-none-any.whl`，SHA256：
`8b43ebeb20b03b209cb0c9ea42dda0b1988ad008bddb2383d03700f3b4c3382e`。
通过 ZipFile 检查确有 `email_agent/procurement.py`、`procurement_mailbox.py`、
`procurement_web.py` 和 `minihermes/ops/procurement_policy.json`。
entry_points.txt 包含 procurement-inbox、procurement-review、procurement-web 三个采购入口。

wheel 使用 `pip --target` 安装到独立目录，复用上述干净环境的依赖。以 `python -I -X utf8`
启动隔离子进程，在 sys.path 首位显式加入该 wheel-site 的绝对路径；检查 procurement 模块和制度
模块的 `__file__` 均在 wheel-site 下，而非源码目录。制度 JSON 可读取。
这不是第二个完全独立的 wheel 虚拟环境，也未把 editable 安装的导入结果冒充 wheel 结果。

| 检查 | 实际结果与边界 |
| --- | --- |
| 三个采购模块的 main --help | 全部返回 0；证明 wheel 中命令目标可以导入，不表示模型或邮箱链路已运行 |
| 邮箱 main --once | 移除子进程 IMAP/SMTP 环境配置，指定空 env 文件和虚构名册，返回 2 并提示缺少 IMAP；没有发起真实收信 |
| Web main | 使用仅含虚构员工和哈希密码的名册、独立 DATA_DIR、随机空闲回环端口；实际子进程启动后 GET /login 返回 200，并创建 applications.sqlite |
| Web 进程重启 | 终止本轮启动的子进程后，用同一 DATA_DIR 和端口再次启动；GET /login 再次 200，数据库仍存在；结束后停止本轮进程 |

Web 检查只使用 urllib 的 HTTP 请求，没有浏览器操作，也未登录或执行采购决定。
第一次临时检查脚本在解码子进程输出时遇到 Windows 默认编码错误；为子进程明确加
`-X utf8` 后重跑上述邮箱/Web 检查成功，未改产品代码。

## 未满足项与后续解除条件

- #19 第一项仍未全部满足：本轮未配置真实邮箱、运行真实收信或模型工作进程；
  Web 空库重启不等于有等待申请的服务重启验收。旧数据迁移和恢复由上述既有离线用例复跑覆盖，
  不是本轮真实部署迁移现场证据。
- wheel 邮箱模块与制度数据调查已通过；本轮未发现需要产品修复的打包缺口。
- #15–#18 的浏览器、模型表达、完整运行入口/重启和发送恢复证据仍由各子任务验收。
  主检出另有针对旧 main 的未提交浏览器报告，未纳入或改写本轮交付，不能覆盖 #21 的新增缺用途样例。
- 本轮没有新增真实模型、真实 IMAP/SMTP、浏览器或人工 QA 证据。
- 最终报告须待前四票齐全，再逐项覆盖 PRD 六段流程和 D1–D21；本记录不将其标为已完成。
  #19、父 #3/#4 保持开放，PR 保持 draft，不使用 Closes。
