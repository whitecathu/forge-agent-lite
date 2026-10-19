# 架构、状态与接口

## 最小运行时

`forge/runtime.py` 定义 LangGraph 状态节点与模型适配器；`forge/tools.py` 实现工具参数校验、工作区边界、文件更新和容器验证；API 与 CLI 使用相同的 Runtime。

节点为 route、plan、model、tools、verify、finish。route 保存状态并检查取消标记。plan 生成计划后进入 awaiting_approval；显式启动后才进入模型/工具循环。模型无更多工具调用时进入 verify。验证成功进入 succeeded；失败最多触发两轮修复；资源不可用进入 blocked。

`calls` 包含规划请求，默认上限 20。模型使用工具调用 schema，工具结果包含 succeeded/failed/blocked、summary 和 data。当前没有并行工具执行：顺序执行简化回放与状态推理。工具内容与模型文本只作为数据展示，不作为新的宿主权限。

## 持久化与恢复

每个 run 一个 LangGraph SQLite 检查点文件，另有 runs.sqlite 保存面向 UI 的状态快照、事件与调用日志。检查点是恢复时的计算状态来源；runs 表用于列表与终态。API 重启将未完成运行标为 interrupted，用户选择恢复后继续。

工具调用以 run_id + tool_call_id 作为日志键。先记录 started，再执行，最后记录 done 与结果。done 调用直接返回已存结果；如果崩溃发生在 started 与 done 之间，结果不明，禁止自动再次产生副作用。调用日志解决的是重放风险，不等同于跨进程事务。

任务 worktree 基于源仓库 HEAD，文件写入使用期望 SHA256，避免覆盖并发修改。源码工具拒绝越界、链接、Git 元数据和常见密钥路径。只在原始可信仓库上使用，Git 配置/过滤器仍属于宿主信任边界。

## 验证与隔离

测试用 docker run 的固定参数列表执行，不经过 shell。禁网、只读根文件系统、只读源码挂载、非 root 用户、移除 capabilities；/tmp 使用有大小上限的 tmpfs。默认 256 MB、1 CPU、64 进程、60 秒。超时通过 cidfile 定位并移除容器。

只有 pytest 退出码 0 判定通过。Docker 不可用/镜像缺失/超时标记 blocked；pytest 失败或没有测试均不算通过。没有安装项目依赖的默认镜像只能测试纯 Python 示例；依赖应在运行前构建入镜像。

## API

| 接口 | 行为 |
|---|---|
| `GET /api/health` | 模式与健康状态 |
| `POST /api/demo-repository` | 创建原创 calculator 示例仓库 |
| `GET/POST /api/runs` | 列表 / 创建任务并生成计划 |
| `GET /api/runs/{id}` | 任务快照，不暴露完整模型消息 |
| `POST /api/runs/{id}/start` | 确认计划后执行 |
| `POST /api/runs/{id}/cancel` | 协作式取消 |
| `POST /api/runs/{id}/resume` | 恢复 interrupted 任务 |
| `GET /api/runs/{id}/events?after=0` | 递增事件序号的 SSE 流 |
| `GET /api/runs/{id}/artifacts` | Diff、验证结果、用量与终止原因 |

本地 API 检查 Host 和 Origin，前端纯文本展示模型输出。不提供账户鉴权，不应代理到公网。单进程内防重复执行；多进程调度、跨进程租约与强制中断模型请求不是当前能力。

参考：[LangGraph StateGraph.compile](https://reference.langchain.com/python/langgraph/graph/state/StateGraph/compile)。
