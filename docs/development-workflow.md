# 开发与验收流程

本仓库的流程入口是 CLAUDE.md；本文件定义步骤，仓库内 .claude/skills 提供执行入口。
GitHub tracker 为 qiqiqia777/audit-agent。需求依据为采购 PRD、GLOSSARY.md 和职责 ADR；
当前验收证据以 procurement-acceptance-status.md 为索引，历史记录不代表最新实现已通过。

## 执行顺序

1. **需求**：需求新增或实质改变时读取 to-spec。已有 PRD/Issue 直接复用，只有范围或测试边界尚未获授权时才澄清。
2. **拆分**：读取 to-tickets，只拆尚未满足的行为与验收证据。每票列父 Issue、验收项、阻塞关系和证据类型。
   已批准的拆分直接发布；新拆分先确认。GitHub 支持时建立原生子 Issue/阻塞关系，否则明确记录链接及限制。
   父 Issue 保留，所有验收项满足后才关闭。项目暂不强制尚未配置的 triage 标签。
3. **实现**：读取 implement，一轮只领取一个无阻塞子任务。从最新 origin/main 建 codex/ 分支，记录基线 SHA。
   先复跑已有行为，只修复已确认缺口；行为变更先写失败测试，再最小实现。测试使用已有 HTTP 或公开模块边界。
   单纯验收已有行为无需制造产品改动。材料与运行数据使用独立目录。
4. **验证**：运行相关测试、Ruff、全量离线回归及 release gate。Windows 可用同等 Python 命令，记录跳过原因。
   离线、真实模型、真实邮件、浏览器分别留证；模拟发送和规则演示不能充当真实模型或邮件验收。
5. **审查**：按基线到 HEAD 的 diff，在独立上下文执行 Standards/Spec 双轴 code-review。
   标准来自 CLAUDE.md、CONTRIBUTING.md；Spec 来自当前子 Issue。修复有效问题，重跑受影响验证，必要时复审。
6. **交付**：读取 ship，推开发分支、创建 PR，并核对 PR 最新 SHA 的 CI；CI、权限和合并规则变更留用户审阅。
   常规业务 PR 仅在已有合并授权、审查和全部验收齐全且最新 CI 成功时合并，否则保留可审阅 PR。
7. **完成**：更新证据索引与子任务状态。浏览器不可用时记录阻塞；HTTP 通过不能关闭要求浏览器的任务。
   人工 QA 尚未反馈时明确标记；父 #3/#4 按各自全部条件完成后关闭。

## 可复现的 skill 入口

在仓库 .claude/skills 下读取 to-spec、to-tickets、implement、code-review、ship 的 SKILL.md。
支持斜杠命令的客户端可以直接调用；其他客户端按文档执行，报告实际读取和执行的步骤。
这些文件随仓库版本控制，不依赖开发者个人全局目录。它们是开发流程，不是 MiniHermes 运行时的 skills/。

## PR 的证据字段

- Ticket/需求：子任务与父 Issue，当前范围和实际行为。
- Baseline/Head：实现起点和已审查提交；追加提交后说明是否影响审查范围。
- Review：Standards/Spec 结果、有效问题及修复情况。
- Validation：命令与结果；分别列离线、真实模型、真实邮件、浏览器、人工 QA。
- Remaining：未验证项和限制，不把缺证据的任务写为完成。

本地常用等价命令为 python -m ruff check --config pyproject.toml minihermes evals email_agent scripts/procurement_demo.py、
python scripts/validate_skills.py、python -m minihermes.ops.release_gate。
现有 CI 检查运行时 skills/、Ruff 和离线测试，不包含浏览器或真实邮箱；开发 skill 需另核对 frontmatter 和文档链接。
