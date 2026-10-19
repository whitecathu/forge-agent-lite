# 简历项目描述

### Forge Agent Lite｜可审计轻量编码 Agent｜独立开源项目

**技术栈：** Python、LangGraph、Function Calling、FastAPI、SQLite、Vue 3、Docker、Git worktree。

- 设计计划确认、工具调用、测试验证与有限修复的状态流程，实现 CLI/Web 共用运行时，并通过 SSE 展示执行事件与交付证据。
- 封装 6 类结构化工具，加入工作区路径限制和 SHA256 写入前置校验；使用独立 Git worktree 承载改动，保留可审查 Diff。
- 结合 SQLite 检查点与工具调用日志实现协作式暂停、恢复及完成结果复用，设置最多 20 次模型调用和 2 轮失败修复，明确区分失败、受阻和成功。
- 在禁网、只读挂载、限资源 Docker 容器中运行 pytest，构建 12 个 Python 编码任务及独立验收测试，避免将模拟流程当作真实模型完成率。

**开源地址：** https://github.com/whitecathu/forge-agent-lite

真实模型任务完成率和费用待配置 API 后实测。投递前应能解释上述实现及其限制，不把它描述为已有生产用户的企业平台。
