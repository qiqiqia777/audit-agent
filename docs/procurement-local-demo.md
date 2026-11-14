# 本地运行设备采购审批

在 audit-agent 仓库根目录使用 Python 3.12 安装项目。安装包同时包含邮箱流程和 MiniHermes 材料检查。

```powershell
uv venv --python 3.12
uv pip install -e '.[dev]'
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

在本地环境文件配置 IMAP_HOST、IMAP_USER、IMAP_PASSWORD、SMTP_HOST 和 SEND_WHITELIST。演示可让登记的员工地址与测试邮箱相同。为两条命令指定相同的 DATA_DIR 和名册。分别在两个终端运行收信服务和负责人页面。

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
