# DeerFlow 迁移交接文档

> **作者**：本次开发会话（2026-05-23）
> **目的**：把当前工作机的状态完整迁移到新环境，clone + 配两份本地文件 + 启服务 = 无缝衔接。
> **当前分支**：`feat/unified-retrieval-protocol`（本地，**未 push**）

---

## 0. 60 秒摘要

```
项目        DeerFlow（LangGraph + FastAPI Gateway + Next.js Frontend 三件套）
当前任务    feat/unified-retrieval-protocol —— 统一检索协议库已落地，待 push
LLM 提供商  内网 CodexProxy（OpenAI Chat Completions 兼容），模型 gpt-5.5
服务状态    本地三服务全活；端到端 1+1=? → "二" 验证通过
未推 commit 5 个（本分支与远端无 upstream 关系，需首次 push 建立追踪）
```

---

## 1. 必须带走的本地文件（git 之外）

`.gitignore` 已挡掉如下文件，**不会被 clone 带过去**，需另渠道传给新机：

| 文件 | 用途 | 敏感度 |
|---|---|---|
| `.env` | `CODEXPROXY_API_KEY` 等 LLM/工具密钥 | **高（含 API key）** |
| `config.yaml` | 当前指向 CodexProxy 的模型配置（虽然历史上 track 过，但已被 .gitignore 覆盖，**不再 commit 后续改动**） | 中（含内网 IP） |
| `checkpoints.db` | sqlite checkpointer 持久化的线程状态 | 中（含历史对话内容） |
| `logs/` | 运行日志 | 低 |
| `.deerflow-no-nginx/` | 当前服务 PID/端口标记 | 低（旧 PID 无效，新机会重建） |

**推荐迁移方式**：用 `scp` / 加密 USB / 1Password 把 `.env` 和 `config.yaml` 单独传过去；`checkpoints.db` 视需要决定带不带（带则历史会话延续，不带则全新开始）。

`.deerflow-no-nginx/` 和 `logs/` 不要带 —— 新机会自动重建。

---

## 2. 新机 bootstrap

### 2.1 系统依赖

```bash
# macOS（brew）
brew install node@22 uv git
npm install -g pnpm     # 或 corepack enable && corepack prepare pnpm@latest --activate

# Linux（apt）
sudo apt install -y git curl
curl -LsSf https://astral.sh/uv/install.sh | sh
# Node 22+ 走 nvm 或 nodesource，pnpm 同上
```

**版本要求**：
- Python `>=3.12`（来自 `backend/pyproject.toml` 的 `requires-python`，uv 会自动装）
- Node `>=22`（前端 Next.js 15 需要）
- pnpm `>=10`

**可选（非必须）**：
- `nginx` —— 仅用于 `make dev` 的 2026 统一入口；不装就用 `make dev-no-nginx`，三服务直接暴露 2024/8001/3000
- `docker` / `apple container` —— 仅用于 AIO Sandbox（隔离 bash 工具执行环境）；不装就走默认 `LocalSandboxProvider`，工具直接在宿主跑

### 2.2 项目依赖

```bash
git clone <repo-url> imiss-deer-flow && cd imiss-deer-flow
git checkout feat/unified-retrieval-protocol

# 后端 + 前端依赖一把梭
make install
# 等价于：
#   uv sync --project backend
#   cd frontend && pnpm install
```

首次 `uv sync` 会自动装 Python 3.12 解释器（如果系统没有）。

### 2.3 创建 `.env`（项目根）

按下面模板新建 `.env`，密钥从旧机 `.env` 拷过来（或重新申请）：

```bash
# ---- LLM provider (CodexProxy) ----
CODEXPROXY_API_KEY=sk-...        # 从旧机 .env 拷贝，或问 CodexProxy 管理员重新申请

# ---- Optional web tools（不填则 web_search/web_fetch 工具失效，主链路不受影响）----
# TAVILY_API_KEY=...
# JINA_API_KEY=...
# INFOQUEST_API_KEY=...

# ---- Optional CORS（前端跨域）----
# CORS_ORIGINS=http://localhost:3000,http://localhost:2026

# ---- Optional tracing ----
# LANGSMITH_TRACING=true
# LANGSMITH_API_KEY=...
# LANGSMITH_PROJECT=deer-flow
# DEERFLOW_RUN_EVENT_LOG_ENABLED=1
# DEERFLOW_RUN_EVENT_LOG_DIR=./logs/run_events
```

### 2.4 创建 `config.yaml`（项目根）

仓库里有 `config.example.yaml`（默认走 qwen3.5-plus + DashScope）。**当前生产配置是 CodexProxy**，对应 models 段如下，其余沿用 example：

```yaml
models:
  # CodexProxy（内网）—— OpenAI Chat Completions 兼容，上游为 Codex Responses API
  - name: codex-proxy
    display_name: GPT-5.5 (Codex Proxy)
    use: langchain_openai:ChatOpenAI
    model: gpt-5.5
    api_key: $CODEXPROXY_API_KEY
    base_url: http://172.23.125.173:8080/v1   # 注意：内网地址，新机必须能访问该 IP
    max_tokens: 8192
    temperature: 0.7
    supports_vision: true
```

**新机的 `base_url` 要不要改？**
- 如果新机在同一内网 → 直接抄
- 如果新机在外网 → 联系 CodexProxy 管理员要外部入口；或改回 qwen3.5-plus（`config.example.yaml` 默认配置）并申请 DashScope key 写到 `.env` 的 `DASHSCOPE_API_KEY`

**其他段不需要改**：embedding（本地 BAAI/bge-m3）、tool_groups、tools、sandbox（`LocalSandboxProvider`）、checkpointer（`sqlite:checkpoints.db`）、summarization 等都用 `config.example.yaml` 默认值即可。

完整启动版可直接抄旧机 `config.yaml`（建议直接 `scp` 过去）。

---

## 3. 启动 & 停止

### 3.1 推荐：no-nginx 模式（不需要 sudo）

```bash
make dev-no-nginx       # 后台启 3 服务：LangGraph(2024) + Gateway(8001) + Frontend(3000)
make status-no-nginx    # 查看运行状态
make stop-no-nginx      # 停止
```

PID 写到 `.deerflow-no-nginx/`，日志写到 `logs/{langgraph,gateway,frontend}.log`。

### 3.2 完整：nginx 统一入口

```bash
make check              # 会检查 nginx 是否安装
make dev                # 启 4 服务（含 nginx 2026 → 反代三件套）
```

打开 `http://localhost:2026`（统一入口）或 `http://localhost:3000`（前端直连）。

---

## 4. 验证链路通畅

```bash
# 1. 服务健康
curl -s http://localhost:2024/ok                              # → {"ok":true}
curl -s http://localhost:8001/health                          # → {"status":"healthy",...}
curl -sI http://localhost:3000 | head -1                      # → HTTP/1.1 200 OK

# 2. 模型在线
curl -s http://localhost:8001/api/models | head -200          # 看到 "codex-proxy" / "GPT-5.5 (Codex Proxy)"

# 3. 端到端跑一句话（LangGraph 直调，不经前端）
THREAD=$(curl -s -X POST http://localhost:2024/threads \
  -H 'content-type: application/json' -d '{}' | python3 -c 'import sys,json;print(json.load(sys.stdin)["thread_id"])')

curl -s -X POST "http://localhost:2024/threads/$THREAD/runs/wait" \
  -H 'content-type: application/json' -d "{
    \"assistant_id\": \"lead_agent\",
    \"input\": {\"messages\": [{\"role\": \"user\", \"content\": \"用一个字回答：1+1=？\"}]},
    \"context\": {
      \"thread_id\": \"$THREAD\",
      \"thinking_enabled\": false,
      \"is_plan_mode\": false,
      \"subagent_enabled\": false
    },
    \"config\": {\"recursion_limit\": 100}
  }" | python3 -c 'import sys,json;d=json.load(sys.stdin);[print(m["type"],":",m["content"]) for m in d["messages"]]'
# 期望最后一行：ai : 二
```

---

## 5. 已知坑（踩过的雷）

### 5.1 LangGraph dev 不 hot-reload `config.yaml`

`langgraph dev`（端口 2024）的 watchfiles 只看代码，**不监听 `config.yaml`**。改了模型名 / base_url / 删了字段后必须重启：

```bash
make stop-no-nginx && make dev-no-nginx
```

Gateway（8001，uvicorn）有 `--reload-include=*.yaml`，可以热加载，但 LangGraph 那边的 model 路由仍指旧配置。所以**任何 yaml 改动都要整体重启**。

### 5.2 调用 LangGraph API 必须传 `context`，不能用 `configurable`

`ThreadDataMiddleware.before_agent` 强依赖 `runtime.context.get("thread_id")`：

```python
# backend/packages/harness/deerflow/agents/middlewares/thread_data_middleware.py:74
thread_id = runtime.context.get("thread_id")
```

少传 `context` → `AttributeError: 'NoneType' object has no attribute 'get'`。

`/runs/wait` 请求体 **必须含**：
```json
{
  "context": {
    "thread_id": "<同 URL 里的 thread_id>",
    "thinking_enabled": false,
    "is_plan_mode": false,
    "subagent_enabled": false
  }
}
```

LangGraph ≥0.6 之后**不能同时**给 `configurable` 和 `context` —— 会直接 400。只用 `context`。

### 5.3 递归限制默认太低

`lead_agent` 一次问答通常会跑 30–80 步（plan → research → write → reflect），默认 `recursion_limit=25` 容易被打爆。`/runs/wait` 请求体里加 `"config": {"recursion_limit": 100}`。IM 渠道（feishu/slack/telegram）走 `config.yaml` 的 `channels.session.config.recursion_limit`。

### 5.4 CodexProxy 仅支持特定模型名

直接调 `gpt-5` 会被拒。可用清单查询：

```bash
curl -s http://172.23.125.173:8080/v1/models | python3 -m json.tool
```

当前生效的模型是 **`gpt-5.5`**。其他可选：`gpt-5.4`、`gpt-5.4-mini`、`gpt-5.3-codex`、`gpt-5.3-codex-spark`、`gpt-5.2`、`gpt-image-2 *`。

### 5.5 `pnpm` 版本不一致

`brew install node` 自带的 corepack pnpm 是 11.x，而仓库锁文件用的是 10.x。`make check` 会报警告，但不阻塞。要消除可：

```bash
corepack prepare pnpm@10.26.2 --activate
```

---

## 6. 当前未完成事项（迁移后立即着手）

### 6.1 待 push 的 5 个 commit

```bash
git log --oneline e7455d1 ~5
# e7455d1 test: 集成测试加载 rag_search.py 时禁止写入 .pyc
# 0ce2e39 docs: 更新统一检索协议落地计划为完成状态
# b9e0613 feat: network-traffic rag_search 支持统一 SkillResult 输出
# 434c70a feat: 新增统一检索协议库 retrieval_protocol
# 03d5230 Add SkillRouter scope and prompt design document
# （另含本次 HANDOVER + task.md 归档 + plan 完成态 三个新 commit，见 §7）
```

新机首次 push：

```bash
git push -u origin feat/unified-retrieval-protocol
```

GitLab 会回显 MR 创建链接，按需用。

### 6.2 协议库后续接入

`skills/_shared/retrieval_protocol/` 已落地，但仅接入了 `network-traffic-analysis/scripts/rag_search.py`。task.md §6 提到的另外 3 个 skill（citybench / road-traffic / policy）**不在本仓库**，由其他仓库维护，等他们的 PR 走 §6 的薄映射方案接入。

完整状态报告：`docs/superpowers/plans/2026-05-21-unified-retrieval-protocol.md`。

### 6.3 可选增强

- 装 `nginx` → 用 `make dev` 走统一 2026 入口
- 装 docker → 切到 `AioSandboxProvider`（容器化 bash 工具，更安全）
- 填 `TAVILY_API_KEY` / `JINA_API_KEY` → 启用 `web_search` / `web_fetch` 工具
- 切换 sqlite checkpointer 到 postgres（多进程部署时）

---

## 7. 仓库结构速查

```
imiss-deer-flow/
├── HANDOVER.md                              # 本文（迁移交接）
├── task.md                                  # 统一检索协议设计 spec（已归档进仓库）
├── config.example.yaml                      # 配置模板（DashScope/qwen 默认值）
├── config.yaml                              # 实际配置（被 .gitignore 覆盖，需单独传）
├── .env                                     # 密钥（被 .gitignore 覆盖，需单独传）
├── Makefile                                 # make dev / dev-no-nginx / install / check 等
├── backend/
│   ├── pyproject.toml                       # Python deps（uv 管理）
│   ├── packages/
│   │   ├── harness/deerflow/                # 主框架（agents/middlewares/tools/...）
│   │   ├── adapters/                        # langgraph / fastapi 适配层
│   │   └── community/                       # 第三方集成（tavily/jina/aio_sandbox/...）
│   └── apps/
│       ├── langgraph-server/                # 2024 端口入口
│       └── gateway/                         # 8001 端口入口
├── frontend/                                # Next.js 15，3000 端口
├── skills/
│   ├── _shared/retrieval_protocol/          # 本分支新增：统一检索协议库
│   │   ├── schema.py envelope.py evidence.py validate.py adapters.py
│   │   ├── tests/                           # 128 个测试用例
│   │   └── README.md
│   └── custom/network-traffic-analysis/
│       └── scripts/rag_search.py            # 已接入 --format skillresult
├── docs/
│   └── superpowers/plans/
│       └── 2026-05-21-unified-retrieval-protocol.md  # 完成态报告
└── scripts/
    ├── dev-no-nginx.sh                      # make dev-no-nginx 实际执行的脚本
    └── update-docker-ports.sh
```

---

## 8. 常用命令清单

```bash
# 开发循环
make dev-no-nginx          # 启服务
make status-no-nginx       # 看状态
tail -f logs/langgraph.log # 看 LangGraph 日志
tail -f logs/gateway.log   # 看 Gateway 日志
tail -f logs/frontend.log  # 看前端日志
make stop-no-nginx         # 停服务

# Python（uv 项目）
uv run pytest skills/_shared/retrieval_protocol/tests/   # 跑协议库测试
uv run python -m <module>                                 # 跑任意 backend 脚本
uv add <pkg>                                              # 加运行时依赖
uv add --dev <pkg>                                        # 加开发依赖

# 前端
cd frontend && pnpm dev    # 单独跑前端（make dev-no-nginx 已含）
cd frontend && pnpm build  # 生产构建
cd frontend && pnpm lint   # eslint

# Git（按 ~/.claude/CLAUDE.md 规范 3）
git status                 # 查改动
git add <具体文件>          # 禁止 git add . / -A
git commit                 # 走 commit skill / 手写规范 message
git push -u origin <分支>   # 首次 push 建追踪；不自动 push
```

---

## 9. 联系与背景上下文

- **CodexProxy**：内网搭建的 OpenAI 兼容代理，三端点 `/v1/responses`、`/v1/chat/completions`、`/v1/messages`，上游 Codex Responses API（GPT-5.x 系列）。本项目用 `/v1/chat/completions` 走 `langchain_openai:ChatOpenAI`。
- **DeerFlow 上游**：本仓库 fork 自 imiss-flow，主分支 `main`。开发分支：`feat/unified-retrieval-protocol`。
- **任务来源**：见 `task.md` 与 `docs/superpowers/plans/2026-05-21-unified-retrieval-protocol.md`。

---

迁移过程中遇到坑请补到本文 §5 已知坑里，持续累积。
