# 采购验收任务拆分历史

本文件保留2026-11-15基于main f7459bb形成的原始拆分，表中的阻塞列表示当时的依赖。
截至2026-11-16，#15–#19及父#3/#4均已实际交付并关闭，PR21/23/24/25/22均已合并。
当前结果见[验收索引](procurement-acceptance-status.md)和[最终交付报告](procurement-final-acceptance.md)；这些历史任务不再作为待开发入口。

| 子任务 | 父 Issue | 交付 | 阻塞 |
| --- | --- | --- | --- |
| [#15](https://github.com/qiqiqia777/audit-agent/issues/15) | #3 | 双部门案例与本次缺用途，HTTP + 浏览器 | 无 |
| [#16](https://github.com/qiqiqia777/audit-agent/issues/16) | #3 | 软件两种报价、补件与旧标签页，浏览器及模型表达补证 | 无 |
| [#17](https://github.com/qiqiqia777/audit-agent/issues/17) | #4 | A/B 续办、重启、60 秒催办撤销、候选分配现场证据 | 无 |
| [#18](https://github.com/qiqiqia777/audit-agent/issues/18) | #4 | 通知与补件发送故障、核实及补发页面；仅修复复现缺口 | 无 |
| [#19](https://github.com/qiqiqia777/audit-agent/issues/19) | #4 | 干净安装、打包、PRD 全项报告与最终人工 QA | #15–#18 |

Issue正文及实际合并状态是任务状态的权威来源。拆分时连接器没有原生子Issue/阻塞关系工具，CLI未登录；
当时父子及阻塞关系以正文链接表达，没有创建GitHub原生关系。
原工作树codex/followup-recovery的无关未提交修改仍须保留；#18已通过独立分支/PR25完成，不重复实施。
