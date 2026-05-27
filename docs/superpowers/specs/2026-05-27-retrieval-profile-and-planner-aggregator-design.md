# Skill Schema retrieval_profile + Planner / Aggregator —— 设计文档

- **状态**：📝 草稿（待用户 review）
- **设计日期**：2026-05-27
- **分支**：当前 `feat/unified-retrieval-protocol`（v1.1 已落地）→ 本设计目标分支
  `feat/retrieval-profile-and-planner`（待开）
- **触发反馈**：仓库 `docs/new_tasks/task.md` 第 44–48 行三条反馈
- **本次交付范围**：S1（profile 收敛）+ S2（Planner / Aggregator stdlib）。
  S3（LangGraph middleware 接入）拆到下一个分支，本次不做。

---

## 1. 背景

`retrieval_protocol` v1.1 已落地：Input Envelope（§3）、SkillResult（§4）、
§7 校验器、§6 适配器、v1.1 增补的 budget / errors / 中间件三件套。但当前实现是
**与 Skill Schema 平行的独立协议库**，而仓库内的"Skill Schema"事实上只有
`SKILL.md` 的 YAML frontmatter（name / description / license / metadata）。
检索 skill 是否支持某些 data_type、是否支持 budget、envelope 必填什么字段、
result 默认敏感度 —— 这些信息**没有形式化的 schema 描述**。

反馈三条：

> ① `Input Envelope` 和 `SkillResult` 不应该被设计成另一套独立协议，而是放进
>   `Skill Schema` 的 retrieval profile 里 —— `Skill Schema` 仍是唯一契约源头。
>
> ② `budget` 建议放在 `Envelope` 顶层，可选。Planner 主动拆，聚合层兜底裁剪。
>
> ③ Plan 模板承担"拆解和编排"职责。多个 retrieve 返回后，结果统一进入聚合层，
>   按 `query_id` 对齐、去重、排序、预算裁剪。

② 的"顶层 budget 字段" v1.1 已就绪；本设计聚焦 ① + ② 的"拆 + 兜底裁剪" + ③。

## 2. 范围

| Section | 内容 | 本次 |
|---|---|---|
| S1 | Skill Schema 收敛 retrieval_profile | ✅ |
| S2 | Planner / Aggregator stdlib 参考实现 | ✅ |
| S3 | LangGraph middleware 接入 LeadAgent | ❌ 下分支 |

S3 与 LeadAgent 中间件链耦合，单独立分支可避免本次 PR 同时影响协议层与
Agent 行为；如 S3 实施踩坑，S1+S2 仍可独立合入。

## 3. Section 1 —— retrieval_profile 收敛

### 3.1 SKILL.md frontmatter 增段（可选）

向后兼容：profile 段缺失时按"未声明"处理，老 skill 仍能加载。

```yaml
---
name: network-traffic-analysis
description: ...
license: ...
retrieval_profile:
  data_types: ["netflow"]
  strategies: ["bm25", "vector", "hybrid"]
  rerank: true
  supports_budget: true
  envelope:
    requires: ["parameters.query", "parameters.data_type"]
    optional: ["filters.where", "filters.time_range"]
  skill_result:
    evidence_payload: "evidence_unit"
    default_sensitivity: "open"
---
```

字段语义：

| 字段 | 类型 | 说明 |
|---|---|---|
| `data_types` | `list[str]` | 本 skill 能处理的数据类型，必须是 `schema.DATA_TYPES` 登记取值 |
| `strategies` | `list[str]` | 支持的检索策略子集，必须是 `RETRIEVAL_STRATEGIES` 取值 |
| `rerank` | `bool` | 是否默认 rerank |
| `supports_budget` | `bool` | skill 内部是否真正尊重 budget（不尊重的，聚合层兜底裁剪） |
| `envelope.requires` | `list[str]` | input 内必填路径列表（dot path，相对 `envelope.input.*`，如 `parameters.query`） |
| `envelope.optional` | `list[str]` | input 内允许的可选路径列表（同上 dot path 规则） |
| `skill_result.evidence_payload` | `str` | 当前仅支持 `"evidence_unit"`（task.md §4） |
| `skill_result.default_sensitivity` | `str` | 默认 `meta.sensitivity_level`，缺省 `"open"` |

### 3.2 `deerflow.skills.types.Skill` 字段扩展

```python
@dataclass
class Skill:
    name: str
    description: str
    license: str | None
    skill_dir: Path
    skill_file: Path
    relative_path: Path
    category: str
    enabled: bool = False
    retrieval_profile: dict | None = None   # 新增
```

`skills/loader.py` 在解析 frontmatter 时多读一段 `retrieval_profile`。
`SkillResponse`（`app/gateway/routers/skills.py`）同步加 `retrieval_profile`
字段，保持 Gateway Conformance 测试通过。

### 3.3 `retrieval_protocol` 包：新增 profile 模块

不重命名包、不动既有文件结构（避免破坏现有 import），**仅新增** `profile.py`
模块作为 Schema 锚点；定位上把整个包重新表述为"Skill Schema retrieval_profile
的参考实现"。

```
skills/_shared/retrieval_protocol/
├── profile.py        # 新：RetrievalProfile schema + 校验
├── schema.py         # 不变：DATA_TYPES / RETRIEVAL_STRATEGIES 常量
├── envelope.py       # 不变：构造器
├── evidence.py       # 不变：构造器
├── errors.py         # 不变
├── middleware.py     # 不变
├── validate.py       # +validate_envelope_against_profile / +validate_result_against_profile
├── adapters.py       # 不变
└── README.md         # 更新文案：retrieval_protocol 是 Skill Schema retrieval_profile 的参考实现
```

`profile.py` 关键 API：

```python
PROFILE_FIELDS_REQUIRED = ("data_types", "strategies")
PROFILE_FIELDS_OPTIONAL = ("rerank", "supports_budget", "envelope", "skill_result")

def validate_skill_retrieval_profile(profile: dict) -> list[str]:
    """校验 SKILL.md frontmatter 里的 retrieval_profile 段。
    返回错误信息列表;空列表表示合规。
    """
    ...

def envelope_matches_profile(envelope: dict, profile: dict) -> list[str]:
    """检查给定 envelope 是否符合 profile 声明的 requires/optional/strategies。"""
    ...

def result_matches_profile(result: dict, profile: dict) -> list[str]:
    """检查给定 SkillResult 是否符合 profile.skill_result 声明。"""
    ...
```

`validate.py` 在原有十条规则之外暴露：

```python
def validate_envelope_against_profile(envelope, profile) -> list[str]: ...
def validate_result_against_profile(result, profile) -> list[str]: ...
```

### 3.4 示范：network-traffic-analysis SKILL.md

把 §3.1 示例填进 `skills/custom/network-traffic-analysis/SKILL.md`
frontmatter，作为：

- 实际验证用例：profile 校验器跑通；
- 文档：其它 skill 写 profile 时直接抄。

### 3.5 测试

- `tests/test_profile.py`（新）：profile 校验器正反例 ≥ 12 例。
- `tests/test_validate_against_profile.py`（新）：envelope/result 对照 profile
  校验 ≥ 8 例。
- `backend/tests/test_skills.py`（若存在则扩展，否则新建）：loader 解析
  retrieval_profile + Skill 类字段 ≥ 4 例。
- `backend/tests/test_gateway_conformance.py`（增）：SkillResponse 含
  retrieval_profile 字段。

## 4. Section 2 —— Planner / Aggregator stdlib

### 4.1 `planner.py`

```python
from dataclasses import dataclass, field

@dataclass(frozen=True)
class RetrievalTask:
    query_id: str
    envelope: dict
    parallel_group: int = 0

@dataclass
class Plan:
    parent_query_id: str
    tasks: list[RetrievalTask] = field(default_factory=list)
    total_budget: dict | None = None

def split_budget(
    total: dict,
    fan_out: int,
    weights: list[float] | None = None,
) -> list[dict]:
    """把总 budget 拆给 fan_out 个并行任务。
    weights=None 等权；总和余数给第一个任务,保证 sum 一致。
    """

def build_plan(
    *,
    parent_query_id: str,
    subqueries: list[dict],
    total_budget: dict | None = None,
) -> Plan:
    """subqueries 每条 = {query_id, envelope, parallel_group?, weight?}。
    若 total_budget 给出,自动给每个 task 注入 envelope.budget(按 weight 拆)。
    """
```

不做的事：

- LLM 调用 / 实际拆问题语义 —— 那是 PlannerMiddleware（S3）的职责；
  本模块只是结构化输出。
- Skill 路由 —— route 由 SkillRouter 决定，build_plan 只接受已经路由好的
  subqueries（每条带 envelope 即可）。

### 4.2 `aggregator.py`

```python
from dataclasses import dataclass
from typing import Callable

@dataclass
class AggregatorHooks:
    dedup_key: Callable[[dict], str] | None = None      # wrapper -> str;默认 evidence_id
    sort_key: Callable[[dict], float] | None = None     # wrapper -> float;默认 -score
    token_estimator: Callable[[dict], int] | None = None  # wrapper -> int;默认 len(text)//4

class Aggregator:
    def __init__(self, hooks: AggregatorHooks | None = None) -> None: ...

    def aggregate(
        self,
        *,
        plan: Plan,
        skill_results: list[dict],
    ) -> dict:
        """按 plan.tasks[].query_id 对齐 skill_results,逐桶 dedup,全局排序,
        按 plan.total_budget 兜底裁剪。返回统一 SkillResult(裁剪发生时附
        E_OUT_OF_BUDGET 错误码 + status='partial')。
        """
```

裁剪顺序：

1. 桶内按 `dedup_key` 去重，保留 `sort_key` 最优一条；
2. 全部 wrapper 合并后按 `sort_key` 升序（默认 `-score`）；
3. 若有 `max_evidence_count`：保留前 N；
4. 若有 `max_token_estimate`：累计 token 估计，超过即丢弃后续；
5. 任一裁剪发生 → result.errors[] 追加 `E_OUT_OF_BUDGET` +
   `status="partial"`。

### 4.3 测试

新建 `tests/test_planner.py` / `tests/test_aggregator.py`，共 ≥ 25 单测：

| 场景 | 用例数 |
|---|---|
| split_budget 等权 / 加权 / 余数分配 | 6 |
| build_plan 子任务注入 budget | 4 |
| Aggregator 默认 dedup / sort / token | 6 |
| Aggregator hooks 覆盖默认 | 3 |
| Aggregator 预算裁剪 + 错误码联动 | 4 |
| 多 plan 桶对齐（query_id 不匹配） | 2 |

## 5. Section 3 —— LangGraph middleware（不在本次范围）

仅记录意图，下分支落地：

- `PlannerMiddleware`：`before_model` 阶段调 LLM 拆子问题 → `build_plan` →
  写入 `thread_state.retrieval_plan`。
- `AggregatorMiddleware`：`after_model` 阶段收集 retrieve 型 SkillResult →
  `Aggregator.aggregate` → 把聚合结果写回 messages。
- 挂在 `TodoListMiddleware` 之后、`MemoryMiddleware` 之前。
- 由 `config.configurable.retrieval_planning_enabled`（默认 False）开关。
- 新增 `tests/test_planner_middleware.py` / `tests/test_aggregator_middleware.py`。
- `tests/test_harness_boundary.py` 不能破。

## 6. 向后兼容

| 项 | 影响 |
|---|---|
| 旧 SKILL.md 无 retrieval_profile | 加载行为不变；skill 仍能用 |
| 旧调用 `build_input_envelope()` 不传 budget | 行为不变 |
| 旧 `validate_skill_result()` | 行为不变；新增的 `validate_*_against_profile` 是独立 API |
| `Skill` dataclass 新增字段默认 `None` | 现有 import 不破 |
| `SkillResponse` 新增字段 | Gateway 客户端可选读 |

## 7. 测试与验证策略

- 全部测试用 Python `unittest`，与现有 retrieval_protocol 测试风格一致。
- 重跑命令：
  ```bash
  cd skills/_shared && python3 -m unittest discover -s retrieval_protocol/tests -t . -v
  cd backend && make test
  ```
- 落地完成前：
  - retrieval_protocol 测试 ≥ 当前 182 + 新增 ≥ 33 = ≥ 215 个 unittest 全绿；
  - backend tests 全绿（含 Gateway Conformance）；
  - `tests/test_harness_boundary.py` 不破。

## 8. 开放问题

- profile 中是否要声明 skill 的"运行档位"（`auto/es/local/demo`）？当前
  envelope.parameters.mode 已有；本次先**不**进 profile。如未来路由层需要按
  skill 的 mode 能力做匹配，可补字段。
- Aggregator 默认 token 估计是 `len(text)//4`，中英文混排误差较大。下一步
  可允许用户在 SKILL.md profile 里声明 token_estimator 名（dispatch 到内置
  实现）。本次先用 hook 覆盖即可。

## 9. 实施顺序（写到 plan 时细化）

1. `profile.py` + 单测
2. `validate.py` 增 against_profile 两函数 + 单测
3. `skills/loader.py` 解析 retrieval_profile + `Skill` 字段
4. `SkillResponse` 加字段 + Gateway Conformance 测试
5. network-traffic-analysis SKILL.md 加 profile 段
6. `planner.py` + 单测
7. `aggregator.py` + 单测
8. README 更新（retrieval_protocol 定位为 Skill Schema retrieval_profile 的参考实现）
9. 分步 commit；完整测试矩阵全绿

## 10. 不做的事（明确 YAGNI）

- 不在 retrieval_protocol 引入第三方 token 估计器（tiktoken）；用户自定走 hook。
- 不在 profile 引入 `skill_priority` / `quality_score` 等加权字段；聚合层
  用 `sort_key` hook 即可定制。
- 不在本次实现 SkillRouter；build_plan 仍接受"已路由好的 subqueries"。
- 不修改 task.md 协议设计（v1.1 的 budget / errors 已对齐反馈②的协议侧）。
