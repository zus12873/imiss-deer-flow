# DeerFlow 源码使用文档

> 配套交付:`deerflow-feat-unified-retrieval-protocol-2026-05-23.tar.gz`(82 MB)
> 阅读顺序:本文 → `HANDOVER.md`(环境/启动) → 各模块代码

---

## 一、项目定位

**DeerFlow** 是基于 **LangGraph** 的多 Agent 研究/分析框架,主体功能:

- **lead_agent** 主导:接到用户问题 → 规划 → 调度子 Agent / 工具 → 写报告
- **子 Agent 体系**:每个能力(researcher / coder / writer / network-traffic-analyzer 等)用独立 subagent,带 sandbox 隔离
- **工具体系**:web_search / web_fetch / image_search / file:read/write / bash 等,可在 `config.yaml` 增减
- **检索体系**:每个数据领域提供 skill(RAG),输出统一 SkillResult(本分支新增协议)
- **IM 通道**:可挂飞书 / Slack / Telegram,问答走 LangGraph thread
- **前端**:Next.js 15,提供对话 UI、artifact 浏览、流式响应

---

## 二、整体架构

```
                       ┌────────────────────────────────────────────┐
                       │  Frontend (Next.js 15, port 3000)          │
                       │  ├ app/  对话 UI / artifact 视图           │
                       │  └ server/  BFF (调 Gateway / LangGraph)   │
                       └─────────────────┬──────────────────────────┘
                                         │ HTTP/SSE
                       ┌─────────────────┴──────────────────────────┐
                       │  Gateway (FastAPI uvicorn, port 8001)      │
                       │  /api/models   /api/memory   /api/threads  │
                       │  /health       /api/run-events  etc.       │
                       │  backend/app/gateway/                      │
                       └─────────────────┬──────────────────────────┘
                                         │
        ┌────────────────────────────────┴───────────────────────────┐
        │  LangGraph Server (port 2024)                              │
        │  入口 graph: lead_agent (`deerflow.agents:make_lead_agent`)│
        │  ┌──────── Middlewares stack ──────────────┐              │
        │  │ clarification → uploads → view_image →  │              │
        │  │ thread_data → memory → todo → title →   │              │
        │  │ loop_detection → dangling_tool_call →   │              │
        │  │ tool_error_handling → subagent_limit →  │              │
        │  │ run_history                             │              │
        │  └─────────────────────────────────────────┘              │
        │  ┌──────── Subagents (sandbox isolated) ───┐              │
        │  │ general-purpose / researcher / coder /  │              │
        │  │ writer / network-traffic-analyzer / ... │              │
        │  └─────────────────────────────────────────┘              │
        │  ┌──────── Tools (sandboxed bash + web) ───┐              │
        │  │ web_search / web_fetch / image_search / │              │
        │  │ ls / read_file / write_file / bash      │              │
        │  └─────────────────────────────────────────┘              │
        │  Checkpointer: sqlite (checkpoints.db)                    │
        └────────────────────────────────────────────────────────────┘
                                         │ uses
                                         ▼
        ┌────────────────────────────────────────────────────────────┐
        │  LLM Backend (CodexProxy)                                  │
        │  http://172.23.125.173:8080/v1/chat/completions            │
        │  model: gpt-5.5                                            │
        └────────────────────────────────────────────────────────────┘
```

可选挂接:`backend/app/channels/`(feishu/slack/telegram),直接调 LangGraph 2024。

---

## 三、源码目录全景

### 3.1 顶层

```
imiss-deer-flow/
├── HANDOVER.md                 迁移交接(读这个 + 装环境)
├── USAGE.md                    本文(源码与扩展指南)
├── task.md                     统一检索协议设计 spec
├── README.md                   上游 DeerFlow 简介
├── Makefile                    所有运行 / 构建命令
├── config.example.yaml         配置模板(默认 qwen)
├── config.yaml                 实际配置(被 .gitignore;含 CodexProxy)
├── .env                        密钥(被 .gitignore)
├── docker-compose*.yml         docker 部署
├── docker/                     docker 镜像构建脚本
├── nginx/                      统一入口反代配置
├── scripts/
│   ├── dev-no-nginx.sh         make dev-no-nginx 的实际脚本
│   └── update-docker-ports.sh  改 docker 端口同步脚本
├── datasets/                   示例数据(网络流量样本等)
├── docs/
│   ├── superpowers/plans/      落地计划(含本次完成报告)
│   └── ...
├── skills/                     检索 skill 与协议库(详见 §4)
├── backend/                    Python 后端(详见 §3.2)
└── frontend/                   Next.js 前端(详见 §3.3)
```

### 3.2 后端 `backend/`

```
backend/
├── pyproject.toml              uv 项目,workspace 含 packages/harness
├── uv.lock                     依赖锁
├── langgraph.json              langgraph dev 入口配置(graph + checkpointer)
├── README.md                   后端说明
├── app/                        可执行应用层
│   ├── gateway/                FastAPI 网关 (8001)
│   │   ├── app.py              ASGI 应用
│   │   ├── config.py           Gateway 配置
│   │   ├── path_utils.py       config.yaml 寻路
│   │   └── routers/            /api/models /memory /threads /health 等
│   └── channels/               IM 通道(独立进程)
│       ├── service.py          channel 启动入口
│       ├── manager.py          多通道生命周期
│       ├── message_bus.py      消息总线
│       ├── base.py             通道抽象
│       ├── feishu.py           飞书 long-poll
│       ├── slack.py            Slack Socket Mode
│       ├── telegram.py         Telegram polling
│       └── store.py            通道状态持久化
└── packages/harness/deerflow/  核心 deerflow 包 (workspace member)
    ├── client.py               DeerFlowClient(嵌入式 SDK,本地复用 graph)
    ├── monitoring.py           Prometheus 等指标钩子
    ├── config/                 config.yaml 加载与 schema
    ├── models/                 LLM 模型注册 / 适配 / patch
    │   └── patched_deepseek.py 给 DeepSeek 系打 thinking 兼容补丁
    ├── agents/                 Agent 核心
    │   ├── __init__.py         make_lead_agent (= LangGraph dev 入口)
    │   ├── lead_agent/         lead_agent 主图实现
    │   ├── memory/             跨会话记忆
    │   ├── thread_state.py     线程状态读写
    │   ├── checkpointer/       SQLite / Postgres checkpointer 工厂
    │   └── middlewares/        13 个中间件(详见 §5.2)
    ├── subagents/              子 Agent 注册与调度
    ├── tools/                  内置工具(builtins 含网络流量分析等)
    ├── sandbox/                沙箱抽象与本地实现
    │   ├── sandbox.py          Sandbox 抽象
    │   ├── sandbox_provider.py 工厂
    │   ├── local/              LocalSandboxProvider(默认,宿主直跑)
    │   ├── middleware.py       工具调用 → sandbox 桥接
    │   ├── tools.py            ls / read_file / write_file / str_replace / bash
    │   └── exceptions.py
    ├── skills/                 skill 注册与路由
    ├── community/              第三方集成
    │   ├── tavily/             web_search
    │   ├── jina_ai/            web_fetch
    │   ├── infoquest/          备用 web_search/fetch
    │   ├── image_search/       DuckDuckGo 图搜
    │   ├── firecrawl/          firecrawl 爬虫
    │   └── aio_sandbox/        Docker / Apple Container 沙箱
    ├── mcp/                    MCP 协议适配(给上游 MCP 工具用)
    ├── reflection/             自反思 / planner reflection
    └── utils/                  通用工具
```

### 3.3 前端 `frontend/`

```
frontend/
├── package.json                pnpm 项目,Next.js 15
├── pnpm-lock.yaml
├── next.config.js
├── Dockerfile
├── public/                     静态资源
└── src/
    ├── app/                    Next.js App Router(对话页 / 上传 / artifact)
    ├── components/             UI 组件(message bubble / tool result / 等)
    ├── core/                   领域核心(thread / message 模型)
    ├── server/                 BFF 层(server actions → Gateway/LangGraph)
    ├── hooks/                  React hooks
    ├── lib/                    工具函数
    ├── styles/                 Tailwind
    ├── typings/                TS 类型定义
    └── env.js                  env 变量校验(t3-env 风格)
```

### 3.4 Skills `skills/`

```
skills/
├── _shared/                    跨 skill 共享库
│   └── retrieval_protocol/     【本分支新增】统一检索协议实现
│       ├── schema.py           data_type 登记表 + features registry
│       ├── envelope.py         Input Envelope 构造器
│       ├── evidence.py         evidence_unit / wrapper / SkillResult 构造器
│       ├── validate.py         融合前 10 条校验规则
│       ├── adapters.py         citybench/network-traffic/road-traffic/policy 映射
│       ├── tests/              6 个 unittest 文件,共 128 用例
│       └── README.md           协议库快速上手
├── custom/                     私有 skill
│   └── network-traffic-analysis/  网络流量分析 RAG
│       ├── SKILL.md            skill 元数据(被 lead_agent 读)
│       ├── scripts/
│       │   └── rag_search.py   支持 --format text|json|skillresult
│       └── data/
└── public/                     公共 skill(开放使用)
```

---

## 四、关键概念

### 4.1 LangGraph + Middleware 模式

DeerFlow 在 LangGraph 之上加了一层**中间件栈**(类似 Django middleware):每个中间件实现 `before_agent` / `after_agent` 钩子,在主 Agent 调 LLM 前后注入逻辑。

**入口**:`backend/langgraph.json` → `deerflow.agents:make_lead_agent`(返回编译后的 LangGraph)。

**13 个中间件**(`backend/packages/harness/deerflow/agents/middlewares/`):

| 文件 | 职责 |
|---|---|
| `thread_data_middleware.py` | 写入 `runtime.context.thread_id` 等,**最先执行,后续中间件依赖** |
| `clarification_middleware.py` | 触发 plan 模式时的反问澄清 |
| `uploads_middleware.py` | 处理用户上传的文件附件 |
| `view_image_middleware.py` | 多模态:把图片塞进 vision-capable 模型的 input |
| `memory_middleware.py` | 注入 `memory.json` 内事实到 system prompt |
| `todo_middleware.py` | TodoWrite/TodoUpdate 工具调度 |
| `title_middleware.py` | 自动给对话生成标题(`config.yaml: title.enabled`) |
| `loop_detection_middleware.py` | 检测 Agent 死循环并打断 |
| `dangling_tool_call_middleware.py` | 处理工具调用挂起 |
| `tool_error_handling_middleware.py` | 工具异常 → 反馈给 Agent 而非崩 |
| `subagent_limit_middleware.py` | 限制 subagent 嵌套深度 |
| `run_history_middleware.py` | 写运行历史 / 事件日志(供 `/api/run-events` 消费) |

**调用 LangGraph 必传 context**:见 HANDOVER §5.2,因为 `thread_data_middleware` 第 74 行强依赖。

### 4.2 Subagent 体系

`backend/packages/harness/deerflow/subagents/` 注册各类专业子 Agent。Lead Agent 通过工具调用方式调度子 Agent,每个子 Agent 跑在独立 sandbox 实例里,有独立超时(`config.yaml: subagents.timeout_seconds`,默认 900s)。

**用法**:在 system prompt 里告诉 lead_agent "用 X 来做 Y",lead_agent 会通过 `dispatch_agent` 类工具调用对应 subagent。

### 4.3 Tools

**两层**:
- **内置工具**(`deerflow/tools/builtins/`):平台预置,如网络流量分析、文件读写
- **社区工具**(`deerflow/community/*/tools.py`):第三方集成,如 tavily/jina

**注册方式**(`config.yaml`):
```yaml
tools:
  - name: web_search           # 工具调用名
    group: web                 # 归类(便于权限切片)
    use: deerflow.community.tavily.tools:web_search_tool   # Python 路径
    max_results: 5             # 工具特化参数
```

### 4.4 Sandbox

工具执行隔离层。**三种 Provider**:

| Provider | 位置 | 行为 |
|---|---|---|
| `LocalSandboxProvider`(默认) | `deerflow/sandbox/local/` | 直接在宿主跑 shell / 文件 IO,**无隔离** |
| `AioSandboxProvider` | `deerflow/community/aio_sandbox/` | 走 Docker / Apple Container,完全隔离 |
| `AioSandboxProvider` + provisioner_url | 同上 | k3s 中由 provisioner 派发 Pod,适合生产 |

切换:改 `config.yaml: sandbox.use`。

### 4.5 Checkpointer

LangGraph 的状态持久化层。

| 类型 | 适用 | 配置 |
|---|---|---|
| `memory` | 单进程开发,**重启丢状态** | `type: memory` |
| `sqlite`(当前用) | 本地持久 / 单进程 | `type: sqlite, connection_string: checkpoints.db` |
| `postgres` | 多进程 / 生产 | `type: postgres, connection_string: postgresql://...` |

切换:改 `config.yaml: checkpointer`,记得 `uv add langgraph-checkpoint-{sqlite,postgres}`。

### 4.6 Channels(IM 通道)

`backend/app/channels/` 是独立可执行,**不通过 Gateway**,直接调 LangGraph 2024 + Gateway 8001 的辅助查询接口。

支持 feishu / slack / telegram,默认全关。开启:`config.yaml: channels.{feishu,slack,telegram}.enabled: true` + 对应 token 到 `.env`。

### 4.7 Skills(检索/工作流)

skill 是声明式的小型工作流单元,有 `SKILL.md`(元数据)+ 脚本。Lead Agent 读到用户提到某领域,会去 skills 目录找匹配的 skill 执行。

本仓库当前唯一已落地 skill:`skills/custom/network-traffic-analysis/`。

---

## 五、配置体系(`config.yaml` 详解)

每段含义(每段对应 `config.example.yaml` 注释,这里给操作要点):

| 段 | 作用 | 操作要点 |
|---|---|---|
| `config_version` | 配置版本号,**改 schema 时 +1** | `make config-upgrade` 会按版本号合并新字段 |
| `docker_ports` / `subnet` | docker 部署端口与子网 | 多人共享主机时务必改 `subnet.dev` 避免冲突 |
| `models` | LLM 注册表 | 详见 §5.1 |
| `embedding` | embedding 模型 | 默认 `sentence-transformers` 本地跑 `bge-m3`,无 key |
| `elasticsearch` | ES 连接 | 给 `index_rag_docs.py` 之类的离线脚本用,LangGraph 主链路不依赖 |
| `tool_groups` | 工具分组(权限切片) | 子 Agent 可只授某个组 |
| `tools` | 工具注册表 | 见 §4.3 |
| `sandbox` | 沙箱 Provider | 见 §4.4 |
| `subagents` | 子 Agent 超时 | 默认 900s,长任务调大 |
| `skills` | skill 目录与挂载点 | `container_path` 给 docker 沙箱挂载用 |
| `title` | 自动取对话标题 | 默认关 |
| `summarization` | 长对话自动摘要 | 默认开,15564 token 触发 |
| `memory` | 跨对话记忆 | 默认关;开启后写 `backend/memory.json` |
| `checkpointer` | LangGraph 状态持久化 | 见 §4.5 |
| `channels` | IM 通道 | 默认关;开启需对应 token |

### 5.1 添加 / 切换 LLM

`models` 列表里追加。**第一个 model 是默认 model**(供 summarization 等用)。每个 model:

```yaml
- name: <唯一名>                                # 调用时用
  display_name: <UI 显示名>
  use: <Python 路径>:<类>                       # 例:langchain_openai:ChatOpenAI
  model: <provider 侧模型 id>
  api_key: $XX_API_KEY                          # 解析 .env
  base_url: <可选,OpenAI 兼容必填>
  max_tokens: <可选>
  temperature: <可选>
  supports_vision: <bool, 启用 view_image>
  supports_thinking: <bool, 启用 reasoning>
  supports_reasoning_effort: <bool>
  when_thinking_enabled:                        # thinking 开启时合并的 extra_body
    extra_body: { thinking: { type: enabled } }
```

`config.example.yaml` 给了 8 个模板:Volcengine / OpenAI / Anthropic / Gemini / DeepSeek / Kimi / Novita / MiniMax / OpenRouter,照搬就好。

**改 model 必须重启 LangGraph**(HANDOVER §5.1)。

---

## 六、协议库 `retrieval_protocol`(本分支新增)

仅依赖 Python 标准库,可被任意检索 skill 拷贝引用。**对应 `task.md` §3 / §4 / §6 / §7**。

### 6.1 三个产物

| 产物 | 入口 | 用途 |
|---|---|---|
| **Input Envelope**(检索请求) | `envelope.build_input_envelope(...)` | 给检索 skill 的标准入参,带 `parameters` / `filters` / `data_sources` |
| **SkillResult**(检索结果) | `evidence.build_skill_result(...)` | 任意 skill 的标准出参,顶层 `summary` / `evidence[]` / `artifacts[]` / `diagnostics` |
| **evidence_unit**(每条命中证据) | `evidence.build_evidence_unit(...)` | 兼容 citybench 原 `sample_evidence.jsonl`,塞进 `evidence[].payload` |

### 6.2 5 个模块

| 模块 | 内容 |
|---|---|
| `schema.py` | `DATA_TYPES`(10 类登记)、`FEATURES_REGISTRY`、`SENSITIVITY_LEVELS`、`ACCESS_POLICIES`、`RETRIEVAL_STRATEGIES`、`TIME_RANGE_MODES` |
| `envelope.py` | `build_input_envelope` `build_filters` `build_retrieval_params` `build_time_range_absolute` `build_time_range_relative` `build_data_source` |
| `evidence.py` | `build_evidence_unit` `build_geo_scope` `build_locator` `build_time_range_*` `build_retrieval_evidence` `build_skill_result` `build_summary` `build_finding` `build_artifact` `build_diagnostics` `build_key_metric` |
| `validate.py` | `validate_skill_result(result) -> list[ValidationIssue]` 走 task.md §7 十条规则 |
| `adapters.py` | `from_citybench_search_hit` `from_network_traffic_hit` `from_road_traffic_hit` `from_policy_hit` 把已落地 skill 的原始输出薄映射成 wrapper+unit |

### 6.3 已接入

`skills/custom/network-traffic-analysis/scripts/rag_search.py` 加 `--format skillresult`:

```bash
uv run python skills/custom/network-traffic-analysis/scripts/rag_search.py \
  --query "可疑外联" --format skillresult > result.json
```

走 `adapters.from_network_traffic_hit` 把内部命中映射到 wrapper+unit,顶层包成 SkillResult。

### 6.4 测试

```bash
cd /Users/huanmeng/Downloads/Projects/imiss-deer-flow
uv run python -m unittest discover -s skills/_shared/retrieval_protocol/tests -t skills/_shared/retrieval_protocol
# 期望:128 个用例全过
```

6 个测试文件分别覆盖 schema / envelope / evidence / validate / adapters / 集成。

---

## 七、二次开发指引

### 7.1 改一个工具的行为

1. 找到 `backend/packages/harness/deerflow/tools/builtins/<tool>.py` 或 `community/<provider>/tools.py`
2. 修改实现,确保签名不变(LangGraph 的 tool 装饰器约定)
3. **不需要重启 LangGraph**:watchfiles 会 hot-reload 后端代码
4. 前端如果接收的字段变了,同步改 `frontend/src/core/` 与 `components/`

### 7.2 加一个新 LLM 模型

按 §5.1 在 `config.yaml: models` 加一段 → **重启 LangGraph**(HANDOVER §5.1)→ 前端 `/api/models` 接口自动反映。

### 7.3 加一个新 subagent

1. `backend/packages/harness/deerflow/subagents/` 下新建模块,实现 LangGraph subgraph
2. 在 subagents 注册表里声明
3. lead_agent 的 system prompt 模板告诉它"何时调用你"

### 7.4 加一个新 skill

1. `skills/custom/<your-skill>/SKILL.md` 写元数据(name / description / when_to_use / scenarios / task_types)
2. 实现脚本(可选 `--format skillresult`)
3. 引用 `_shared/retrieval_protocol` 构造标准输出
4. 重启 LangGraph 后 lead_agent 会自动 discovery

### 7.5 加一个新 IM 通道

1. `backend/app/channels/<provider>.py` 实现 `base.Channel` 抽象
2. `manager.py` 注册
3. `config.yaml: channels.<provider>` 加配置段
4. 独立进程跑:`uv run python -m app.channels.service`(不通过 make dev)

### 7.6 升级 LangGraph 版本

LangGraph ≥0.6 后 `configurable` 与 `context` 互斥(见 HANDOVER §5.2),所有 invoke 调用必须用 `context`。如果升级时遇到 400,检查请求体。

---

## 八、调试 / Trace / 日志

### 8.1 日志位置

```
logs/langgraph.log    # LangGraph 主链路,含中间件、tool call、LLM 请求
logs/gateway.log      # Gateway 路由日志
logs/frontend.log     # Next.js dev server 日志
```

实时跟:`tail -f logs/langgraph.log | grep -v watchfiles`

### 8.2 Run Events

`run_history_middleware` 把每次运行的中间事件写到本地。打开:

```yaml
# .env
DEERFLOW_RUN_EVENT_LOG_ENABLED=1
DEERFLOW_RUN_EVENT_LOG_DIR=./logs/run_events
```

事件文件:`logs/run_events/<thread_id>/<run_id>.jsonl`,每行一条事件。Gateway `/api/run-events` 也能查。

### 8.3 LangSmith Trace(可选)

```yaml
# .env
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=...
LANGSMITH_PROJECT=deer-flow
```

trace 自动上传到 LangSmith,UI 看每次调用的 graph 图、token、耗时。

### 8.4 直接调 LangGraph(绕过前端)

见 HANDOVER §4,curl 三连。

---

## 九、测试体系

### 9.1 协议库测试

```bash
uv run python -m unittest discover -s skills/_shared/retrieval_protocol/tests -t skills/_shared/retrieval_protocol
```

128 用例,纯标准库,秒跑完。

### 9.2 后端测试

```bash
uv run pytest backend/                       # 全量
uv run pytest backend/tests/test_xxx.py      # 单文件
```

### 9.3 前端测试

```bash
cd frontend && pnpm test                     # 如配置了 vitest/jest
cd frontend && pnpm lint                     # eslint
cd frontend && pnpm build                    # 生产构建做 smoke check
```

---

## 十、部署模式

### 10.1 本地开发(当前模式)

```bash
make dev-no-nginx   # 三服务直接暴露,无 sudo
# 或
make dev            # 含 nginx 2026 统一入口,需 sudo / nginx 装好
```

### 10.2 Docker

```bash
make docker-init                   # 首次:拉镜像 / 建 volume
make docker-start                  # 启
make docker-stop                   # 停
make docker-logs                   # 看全部日志
make docker-update-ports-cname     # 改端口后同步
```

详见仓库内 `部署启动.md`(中文) 与 `docker/` 下脚本。

### 10.3 Linux 守护进程

```bash
make linux-server-start
make linux-server-status
make linux-server-stop
```

适合在 Linux server 上长期跑(systemd 风格)。

---

## 十一、本压缩包包含什么

`deerflow-feat-unified-retrieval-protocol-2026-05-23.tar.gz`:

- ✅ 全部源代码(`backend/` `frontend/` `skills/` `docs/` `scripts/` 等)
- ✅ 全部 commit 历史(`.git/`,67 MB,可继续 git log/checkout/commit)
- ✅ `HANDOVER.md`(迁移指南)
- ✅ `USAGE.md`(本文)
- ✅ `task.md`(协议设计 spec)
- ✅ `config.example.yaml`(配置模板)

**不包含**(需另渠道传或新机重建):

- ❌ `.env`(含 `CODEXPROXY_API_KEY`)—— 旧机 `scp` 过来
- ❌ `config.yaml`(含内网 IP)—— 旧机 `scp` 或按 HANDOVER §2.4 重写
- ❌ `backend/.venv/`(881 MB,新机 `make install` 重建)
- ❌ `frontend/node_modules/`(891 MB,新机 `make install` 重建)
- ❌ `frontend/.next/`(111 MB,新机 build 自动生成)
- ❌ `logs/*.log`(运行时,无意义)
- ❌ `.deerflow-no-nginx/`(旧 PID,无意义)
- ❌ `checkpoints.db`(对话历史,看需要;迁移时可单独 `scp`)

---

## 十二、下一步建议

1. 解压压缩包到新机目标位置,改名 `imiss-deer-flow/`(或保持原名)
2. 读 HANDOVER.md §2 装环境,跑 `make install`
3. `scp` 旧机的 `.env` `config.yaml`(必要时含 `checkpoints.db`)过来
4. `make dev-no-nginx` 启服务,跑 HANDOVER §4 curl 验证脚本,期望末行 `ai : 二`
5. 浏览器开 `http://localhost:3000` 验证 UI
6. 按 HANDOVER §6.1 `git push -u origin feat/unified-retrieval-protocol`

之后即可继续:
- 接入 `task.md` §6 提到的另外 3 个检索 skill(citybench / road-traffic / policy 由其他仓库提交,以薄映射方式合入)
- 或:加新 LLM / 新工具 / 新 channel,见 §7

---

*本文与 HANDOVER.md 共同构成迁移与二次开发的入门套件。如发现实现与文档不符,以代码为准并把更正回写到本文。*
