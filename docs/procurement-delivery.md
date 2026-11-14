# 采购审批助手：产品范围、三周计划与验收

本文以公开 Issue #1–#4 为交付范围。制度为自编演示制度，不代表真实公司的采购政策。

## 产品职责

事件驱动邮箱主工程负责邮件入站、身份与部门名册、登录页面、申请版本与状态、负责人决定、通知记录和投递。Audit Agent 提供只读材料检查和制度依据，供主工程调用；不发送邮件，不批准申请，不创建另一套调度器。

`minihermes.ops.procurement.review_equipment(application)` 接收字典：

| 字段 | 约定 |
| --- | --- |
| `item` / `purpose` / `spec` | 非空字符串：采购对象、业务用途、规格 |
| `quantity` | 正整数，不接受布尔值、浮点数或数字字符串 |
| `amount` | 人民币正金额，优先传十进制字符串，最多两位小数；也支持整数及 Decimal，不接受浮点数 |
| `price_basis` | `unit` 为单件价，`total` 为整批总价；未知时留空，必须补件 |

返回 `materials` 材料摘要、`estimated_total_cny` 精确到分的总额（数值或口径不全时为 `None`）、`questions` 逐项补件问题，以及 `policy_version` 和 `clauses` 原文。每个问题通过 `clause` 引用条款编号。`ready_for_review` 仅代表材料可交负责人审批，`needs_clarification` 表示须补件。两种结果都不是审批决定。演示制度 v1.0 的 EQ-1 覆盖对象、用途、规格和数量，EQ-2 覆盖费用及报价口径；条文随结果返回，可按版本和编号回查。

## 分阶段交付与验收

| 阶段 | 交付与验收 | 跟踪 |
| --- | --- | --- |
| 第一周：材料检查 | 完整、缺项、无效数值、含糊报价有确定性测试；提供制度版本与条文、可复演调用 | [#1](https://github.com/qiqiqia777/audit-agent/issues/1) |
| 第一周：邮箱集成 | 虚构员工通过真实测试邮箱提交设备申请；负责人页面查看材料与依据、预览后点击批准并通知；员工实际收件；保留脱敏入站、申请、决定、投递证据；跨部门查看和审批均拒绝 | [#2](https://github.com/qiqiqia777/audit-agent/issues/2) |
| 第二周：软件订阅 | 5 席一年、120 元/月先澄清口径，单席月价为 7200 元、全部席位月价为 1440 元；改为 8 席后单席月价为 11520 元，展示差异，旧版本不得决定或通知；同部门同类已办结案例含原申请号，历史获批不能免除缺项，员工仅见本人当前申请，跨部门摘要和原记录不可访问 | [#3](https://github.com/qiqiqia777/audit-agent/issues/3) |
| 第三周：可靠性与交付 | A 等补件时 B 可办结，重启回复接回 A；重复邮件幂等，歧义归属人工选择前不修改候选；补件成功发出才计时（默认 48 小时、演示 1 分钟），每轮最多一条待确认催办草稿，回复后撤销且旧草稿不可发送；明确拒收与投递结果待核实分别记录，保留决定并按人工核实结果补发；交付页面、部署/架构说明、测试报告与复演步骤 | [#4](https://github.com/qiqiqia777/audit-agent/issues/4) |

## 本阶段复演

在仓库根目录安装开发环境后执行：

```sh
python -m pip install -e '.[dev]'
python -X utf8 -m pytest -q evals/deterministic/test_procurement.py
python -m ruff check --config pyproject.toml minihermes evals
python -X utf8 scripts/validate_skills.py
python -X utf8 -m pytest -q evals/deterministic
```

调用示例见 README。完整设备申请（2 台、单价 1200.55 元）返回 `ready_for_review` 和 `2401.10`；将 `price_basis` 改为 `total` 返回 `1200.55`；删掉口径则返回 `needs_clarification`、EQ-2 补件问题且总额为空；空字典返回六项补件问题。

本阶段仅验证结构化输入的离线检查。真实邮箱入站、负责人页面与决定、通知实际送达、部门隔离、软件订阅、恢复与投递故障均待相应集成阶段验证。#1 关闭不代表这些场景已经验收。报告须分开记录真实投递、模拟故障与未验证项。
