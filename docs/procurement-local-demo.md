# 本地运行设备采购审批

在 audit-agent 仓库根目录使用 Python 3.12 安装项目。安装包同时包含邮箱流程和 MiniHermes 材料检查。

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e '.[dev]'
.\.venv\Scripts\python -m pytest -q evals/deterministic/test_equipment_intake.py evals/deterministic/test_procurement_web.py
```

在本地创建名册文件，路径放在仓库外。将员工地址替换为允许测试的邮箱。名册的 managers 键为登录账号，department 与员工所在部门匹配。

```json
{
  "staff": {"employee@example.test": "设计部"},
  "managers": {"design-lead": {"department": "设计部", "password_hash": "替换为生成的哈希"}}
}
```

用以下命令为演示负责人生成密码哈希。输入时不会回显密码。

```powershell
.\.venv\Scripts\python -c "from getpass import getpass; from werkzeug.security import generate_password_hash; print(generate_password_hash(getpass()))"
```

在本地环境文件配置 IMAP_HOST、IMAP_USER、IMAP_PASSWORD、SMTP_HOST 和 SEND_WHITELIST。
DATA_DIR设为独立数据目录的绝对路径，三个进程使用同一个DATA_DIR和同一份名册。
IMAP_FOLDER默认INBOX，隔离复演可指定已创建的专用文件夹；POLL_INTERVAL_SECONDS默认60且须大于0。
SMTP_USER/SMTP_PASSWORD默认复用IMAP账号/密码，默认IMAP_PORT=993、SMTP_PORT=465。
演示可让登记的员工地址与测试邮箱相同，SEND_WHITELIST只列授权测试地址。凭据不提交仓库。
分别在两个终端运行收信服务和负责人页面。

```powershell
.\.venv\Scripts\python -m email_agent.procurement_mailbox --roster C:\demo\roster.json --env-file .env
.\.venv\Scripts\python -m email_agent.procurement_web --roster C:\demo\roster.json --env-file .env
```

打开 http://127.0.0.1:8091/ 。服务启动后，从登记的测试邮箱发送主题以「设备采购申请」开头的邮件。正文示例：

```text
采购对象：显示器
业务用途：设计校色
规格：27 英寸
数量：2
报价：1200.55
费用口径：单价
```

负责人登录后可核对预计总额 2401.10 元和演示制度条款，预览通知，然后点击批准或驳回。数据库在 DATA_DIR/procurement/applications.sqlite。送达验收需要在收件箱核对唯一申请标记和决定正文。

## 模型审查

另开终端运行 `python -m email_agent.procurement_worker --env-file .env`。
配置 MINIHERMES_PROVIDER 及对应提供商密钥。若使用邮箱工程的 GLM_API_KEY、GLM_BASE_URL、GLM_MODEL，命令添加 --glm-compat。
模型循环复用 MiniHermes 的现有适配。

收信服务先保存原邮件并生成审查任务。模型服务异步领取，页面显示状态、建议、逐字段原文和制度依据。
本版本审查成功后才允许审批和发送补件；模型完成会更新材料版本，负责人需核对新版。
失败任务显示错误类别，修复配置后启动服务时添加 --retry-failed。进程锁限制同一目录一个模型服务，重启后可恢复运行中的任务。
旧记录如果没有原邮件，需先按申请编号补充材料，再生成可审查的新版。

## 等待与催办

PROCUREMENT_WAIT_SECONDS 默认 172800（48 小时），演示设为 60。补件请求确认发送成功后开始计时。
采购收信进程内每秒检查已到期的等待，生成一条待确认催办草稿，负责人打开页面后确认发送。
检查本身不发邮件，也不需要负责人保持页面打开；重启后沿用数据库保存的截止时间。
运行 --once 时，完成一次收信后也检查一次到期等待。

员工回复先提交到数据库时，本轮等待结束，未发草稿撤销。后续收到相同邮件不会再改动版本。
如果回复没有新增可识别材料，也会结束原等待并重新检查材料；仍有缺项时，形成新一轮待确认补件请求。
如果负责人已经先领取了发送任务，随后才接收到员工回复，保留该次可能在途的发送记录，同时结束原等待。
这两种顺序以数据库事务提交和发送领取为界；系统不能撤回已经交给邮件服务器的邮件。
审批完成后，本申请的未发草稿取消，历史补件、截止时间和等待结束标记继续保留。

运行虚构自然语言样例的真实模型验收可使用
`python scripts/verify_procurement_model.py --env-file .env --glm-compat --output data/procurement-acceptance/model-natural-language.json`。
该脚本不发送邮件，脱敏结果只记录模型名、审查状态、金额及引用编号。

## 通知恢复

审批决定先保存，随后记录一次独立的发送尝试。发送前已保存邮件编号，用它在邮箱或服务器记录中核对投递。审批决定保留原负责人及决定时间。

- 服务器明确拒收或发件配置被拒绝时，页面显示通知发送失败，保留该次记录。负责人核对页面上的同一份通知后点击「确认补发通知」，新增发送尝试。
- 连接中断或进程退出后发送结果不明时，页面显示发送结果待核实。负责人先核对收件箱和服务器记录，填写核实依据，并选择已送达或未送达。确认未送达后才出现补发入口。
- 若在决定保存后、发信认领前进程退出，页面保留待发送通知，可以确认继续发送。重复提交旧页面不能重复领取同一次发送。

通知恢复已有离线回归、实际IAB浏览器与用户核心页面QA，并在受控注入故障后核对六项真实SMTP/IMAP恢复；
详见[恢复报告](procurement-send-recovery-verification.md)。故障为适配层注入，不代表服务商实际故障。
用户已接受：缺历史等待时长且已送达的旧补件记录保留待核实、不自动催办、不重发；不要用当前配置猜历史截止。

## 安装包与重启复演

开发方式采用上面的editable安装。也可构建wheel，在另一全新环境安装；以下为PowerShell命令，
路径由使用者选定，不覆盖原运行数据：

```powershell
.\.venv\Scripts\python -m pip wheel --no-deps --wheel-dir dist .
python -m venv .venv-package
.\.venv-package\Scripts\python -m pip install 'dist/mini_hermes-0.1.0-py3-none-any.whl[dev]'
.\.venv-package\Scripts\python -m pip check
.\.venv-package\Scripts\procurement-inbox --roster C:\demo\roster.json --env-file C:\demo\procurement.env
# 在其他终端以同一配置分别启动：
.\.venv-package\Scripts\procurement-review --env-file C:\demo\procurement.env --glm-compat
.\.venv-package\Scripts\procurement-web --roster C:\demo\roster.json --env-file C:\demo\procurement.env
```

使用`--glm-compat`时必须在本地配置GLM_API_KEY、GLM_BASE_URL、GLM_MODEL；其他提供商按“模型审查”节配置并省略该参数。
验证包导入时从源码目录外运行，打印模块`__file__`应位于新环境site-packages。
生产三个入口与规则/本地收件箱演示入口分开，后者不会连接真实邮箱。

重启时先停止本次运行的三个服务，保留DATA_DIR，重新执行相同命令；Web重启后重新登录。
库初始化会幂等补齐旧表结构，模型工作进程会重新排队running任务；failed任务须先解决错误再显式`--retry-failed`。
不要删除数据库、游标或运行目录。核对原申请编号、材料版本、决定、通知尝试、补件sent_at/due_at均保留；
未知发送结果按“通知恢复”节先核实，不直接重复批准或发送。

本机Windows/Python3.12的实际安装、真实链路与受控旧库迁移结果见[最终报告](procurement-final-acceptance.md)。
报告区分wheel进程重启、历史迁移回归和#17真实60秒链路，不声称执行过生产旧库升级。
