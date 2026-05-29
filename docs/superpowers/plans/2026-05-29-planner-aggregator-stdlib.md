# Planner / Aggregator stdlib（S2）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 retrieval_protocol 补齐 task.md 反馈 #2（Planner 拆预算）+ #3（聚合层对齐/去重/排序/裁剪）的**纯 stdlib 编排层**：`planner.py`（split_budget + build_plan）与 `aggregator.py`（Aggregator.aggregate）。

**Architecture:** 新增两个独立模块 `planner.py` / `aggregator.py`，只依赖包内已有的 `envelope.build_budget` / `evidence.build_skill_result` / `errors.build_error`。无 LLM、无 Skill 路由、无 LangGraph 接入（那是 S3，单开分支）。沿用历史设计 spec `fffc423` 的 §4。**严格 TDD**，不破坏现有 284 测试基线，不改公开 API 既有导出（仅追加）。

**Tech Stack:** Python 3.11+, stdlib only（dataclasses / typing），unittest，从仓根跑 `python3 -m unittest`。

---

## 设计锚点（来自历史 spec fffc423 §4）

### planner.py
- `RetrievalTask(query_id, envelope, parallel_group=0)` —— frozen dataclass
- `Plan(parent_query_id, tasks=[], total_budget=None)`
- `split_budget(total, fan_out, weights=None) -> list[dict]`：把总 budget 拆给 fan_out 个并行任务；等权或按 weights；余数给第一个，保证各字段 sum 与 total 一致
- `build_plan(*, parent_query_id, subqueries, total_budget=None) -> Plan`：subqueries 每条 = `{query_id, envelope, parallel_group?, weight?}`；若给 total_budget，自动按 weight 给每个 task 的 `envelope["budget"]` 注入拆分后预算

### aggregator.py
- `AggregatorHooks(dedup_key=None, sort_key=None, token_estimator=None)`
  - 默认 `dedup_key` = `wrapper["payload"]["evidence_id"]`
  - 默认 `sort_key` = `-wrapper.get("score", 0.0)`（升序排 → score 高的在前）
  - 默认 `token_estimator` = `len(wrapper["payload"].get("text", "")) // 4`
- `Aggregator(hooks=None).aggregate(*, plan, skill_results) -> dict`
  - **对齐契约**：`skill_results` = `list[{"query_id": str, "skill_result": dict}]`（S3 PlannerMiddleware 派发时天然知道每个 result 对应哪个 query_id；用显式 query_id 配对，不依赖 request_id 串改）
  - 裁剪 5 步：① 桶内按 dedup_key 去重（保留 sort_key 最优一条）→ ② 全局按 sort_key 排序 → ③ 有 max_evidence_count 截前 N → ④ 有 max_token_estimate 累计 token 超限即丢后续 → ⑤ 任一裁剪发生 → 追加 `E_OUT_OF_BUDGET` + `status="partial"`

### 明确不做（YAGNI）
- 不引入 tiktoken（token 估计走 hook）
- 不实现 SkillRouter（build_plan 接受已路由好的 subqueries）
- 不接 LangGraph middleware（S3）
- 不动 schema.py / envelope.py / evidence.py / errors.py 既有函数（只 import 复用）

---

## File Structure

**新增**：
- `skills/_shared/retrieval_protocol/planner.py`
- `skills/_shared/retrieval_protocol/aggregator.py`
- `skills/_shared/retrieval_protocol/tests/test_planner.py`
- `skills/_shared/retrieval_protocol/tests/test_aggregator.py`

**修改**：
- `skills/_shared/retrieval_protocol/__init__.py`（追加导出，不动既有）
- `skills/_shared/retrieval_protocol/README.md`（新增 Planner/Aggregator 章节）

**不动**：schema.py / envelope.py / evidence.py / errors.py / validate.py / adapters.py / middleware.py / sensitivity_rules.py / audit.py

---

## Task 0：基线确认

- [ ] **Step 1: 工作区状态**

Run: `git status --short`
Expected: 仅历史 untracked（SYNC_*.md / 数据对接*.md / 补充回复.md / config.yaml 等），无意外 modified

- [ ] **Step 2: 基线测试**

Run: `python3 -m unittest discover -s skills/_shared/retrieval_protocol/tests -t skills/_shared/retrieval_protocol 2>&1 | tail -3`
Expected: `Ran 284 tests ... OK`

无 commit。

---

## Task 1：planner.py —— split_budget

**Files:**
- Create: `skills/_shared/retrieval_protocol/planner.py`
- Test: `skills/_shared/retrieval_protocol/tests/test_planner.py`

**实现策略**：先只做 `split_budget`，纯函数。RetrievalTask/Plan/build_plan 放 Task 2。

- [ ] **Step 1: 写失败测试**

Create `skills/_shared/retrieval_protocol/tests/test_planner.py`：

```python
"""planner.py 单元测试 —— split_budget / build_plan。"""

from __future__ import annotations

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from retrieval_protocol import planner  # noqa: E402


class TestSplitBudget(unittest.TestCase):
    def test_equal_split_both_fields(self):
        total = {"max_evidence_count": 30, "max_token_estimate": 9000}
        parts = planner.split_budget(total, 3)
        self.assertEqual(len(parts), 3)
        self.assertEqual(sum(p["max_evidence_count"] for p in parts), 30)
        self.assertEqual(sum(p["max_token_estimate"] for p in parts), 9000)
        # 等分:每份 10 / 3000
        self.assertEqual([p["max_evidence_count"] for p in parts], [10, 10, 10])

    def test_remainder_goes_to_first(self):
        total = {"max_evidence_count": 10}
        parts = planner.split_budget(total, 3)
        # 10 // 3 = 3, 余 1 给第一个 → [4, 3, 3]
        self.assertEqual([p["max_evidence_count"] for p in parts], [4, 3, 3])
        self.assertEqual(sum(p["max_evidence_count"] for p in parts), 10)

    def test_weighted_split(self):
        total = {"max_evidence_count": 100}
        parts = planner.split_budget(total, 2, weights=[3.0, 1.0])
        # 75 / 25
        self.assertEqual(sum(p["max_evidence_count"] for p in parts), 100)
        self.assertGreater(parts[0]["max_evidence_count"], parts[1]["max_evidence_count"])
        self.assertEqual(parts[0]["max_evidence_count"], 75)
        self.assertEqual(parts[1]["max_evidence_count"], 25)

    def test_single_field_only(self):
        total = {"max_token_estimate": 8000}
        parts = planner.split_budget(total, 4)
        self.assertEqual(sum(p["max_token_estimate"] for p in parts), 8000)
        self.assertTrue(all("max_evidence_count" not in p for p in parts))

    def test_fan_out_one_returns_total(self):
        total = {"max_evidence_count": 7, "max_token_estimate": 100}
        parts = planner.split_budget(total, 1)
        self.assertEqual(parts, [{"max_evidence_count": 7, "max_token_estimate": 100}])

    def test_invalid_fan_out_raises(self):
        with self.assertRaises(ValueError):
            planner.split_budget({"max_evidence_count": 5}, 0)

    def test_weights_length_mismatch_raises(self):
        with self.assertRaises(ValueError):
            planner.split_budget({"max_evidence_count": 5}, 3, weights=[1.0, 1.0])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m unittest skills._shared.retrieval_protocol.tests.test_planner.TestSplitBudget -v`
Expected: FAIL（`No module named ... planner` 或 `AttributeError: split_budget`）

- [ ] **Step 3: 实现 planner.py（仅 split_budget）**

Create `skills/_shared/retrieval_protocol/planner.py`：

```python
"""检索计划编排（纯 stdlib）—— task.md 反馈 #2/#3 的 Planner 侧。

把一条复合检索的总预算拆给若干并行 retrieve 任务,并把已路由好的子问题
组织成结构化 Plan。**不含** LLM 拆问题语义与 Skill 路由 —— 那是上层
PlannerMiddleware(S3)与 SkillRouter 的职责。本模块只做结构化输出。

设计来源:历史 spec docs/superpowers/specs/2026-05-27-... §4.1。
本模块仅依赖 Python 标准库。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

_BUDGET_FIELDS = ("max_evidence_count", "max_token_estimate")


def _split_one(total_value: int, fan_out: int, weights: list[float] | None) -> list[int]:
    """把单个整数预算按权重拆成 fan_out 份,余数给第一个,保证 sum 一致。"""
    if weights is None:
        base = total_value // fan_out
        parts = [base] * fan_out
    else:
        weight_sum = sum(weights)
        parts = [int(total_value * w / weight_sum) for w in weights]
    # 余数(等权的整除余数,或加权的取整损失)统一补给第一个,保证 sum == total_value
    remainder = total_value - sum(parts)
    parts[0] += remainder
    return parts


def split_budget(
    total: dict[str, Any],
    fan_out: int,
    weights: list[float] | None = None,
) -> list[dict[str, Any]]:
    """把总 budget 拆给 ``fan_out`` 个并行任务。

    - ``total``: 含 ``max_evidence_count`` / ``max_token_estimate`` 之一或两者。
    - ``weights=None``: 等权;否则按权重比例,长度须等于 ``fan_out``。
    - 整除/取整余数统一补给第一个任务,保证每个字段拆分后 **sum 与 total 一致**。

    返回长度为 ``fan_out`` 的 budget 列表;只拆 ``total`` 实际给出的字段。
    """
    if not isinstance(fan_out, int) or isinstance(fan_out, bool) or fan_out < 1:
        raise ValueError("fan_out must be a positive integer")
    if weights is not None and len(weights) != fan_out:
        raise ValueError(f"weights length {len(weights)} != fan_out {fan_out}")
    if weights is not None and (sum(weights) <= 0 or any(w < 0 for w in weights)):
        raise ValueError("weights must be non-negative with a positive sum")

    present = [f for f in _BUDGET_FIELDS if f in total]
    if not present:
        raise ValueError(
            f"total budget must contain at least one of {_BUDGET_FIELDS}"
        )

    result: list[dict[str, Any]] = [{} for _ in range(fan_out)]
    for field_name in present:
        value = total[field_name]
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ValueError(f"{field_name} must be a non-negative integer")
        for i, part_value in enumerate(_split_one(value, fan_out, weights)):
            result[i][field_name] = part_value
    return result
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m unittest skills._shared.retrieval_protocol.tests.test_planner.TestSplitBudget -v`
Expected: 7 PASS

- [ ] **Step 5: 全量回归**

Run: `python3 -m unittest discover -s skills/_shared/retrieval_protocol/tests -t skills/_shared/retrieval_protocol 2>&1 | tail -3`
Expected: `Ran 291 tests ... OK`（284 + 7）

- [ ] **Step 6: Commit**

```bash
git add skills/_shared/retrieval_protocol/planner.py \
        skills/_shared/retrieval_protocol/tests/test_planner.py
git commit -m "feat(retrieval_protocol): planner.split_budget 拆预算

task.md 反馈 #2 的 Planner 侧: 把总 budget(max_evidence_count /
max_token_estimate)按等权或加权拆给 N 个并行 retrieve, 余数补第一个
保证 sum 一致。纯 stdlib, 无 LLM/路由。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 2：planner.py —— RetrievalTask / Plan / build_plan

**Files:**
- Modify: `skills/_shared/retrieval_protocol/planner.py`（追加 dataclass + build_plan）
- Test: `skills/_shared/retrieval_protocol/tests/test_planner.py`（新增 TestBuildPlan）

- [ ] **Step 1: 写失败测试**

在 `test_planner.py` 追加：

```python
class TestBuildPlan(unittest.TestCase):
    def _env(self, q):
        return {"input": {"parameters": {"query": q, "data_type": "netflow"}}}

    def test_plan_without_budget(self):
        plan = planner.build_plan(
            parent_query_id="root",
            subqueries=[
                {"query_id": "q1", "envelope": self._env("a")},
                {"query_id": "q2", "envelope": self._env("b")},
            ],
        )
        self.assertEqual(plan.parent_query_id, "root")
        self.assertEqual([t.query_id for t in plan.tasks], ["q1", "q2"])
        self.assertIsNone(plan.total_budget)
        # 无 total_budget 时不注入 envelope.budget
        self.assertNotIn("budget", plan.tasks[0].envelope)

    def test_plan_injects_split_budget(self):
        plan = planner.build_plan(
            parent_query_id="root",
            subqueries=[
                {"query_id": "q1", "envelope": self._env("a")},
                {"query_id": "q2", "envelope": self._env("b")},
            ],
            total_budget={"max_evidence_count": 10},
        )
        b1 = plan.tasks[0].envelope["budget"]
        b2 = plan.tasks[1].envelope["budget"]
        self.assertEqual(b1["max_evidence_count"] + b2["max_evidence_count"], 10)

    def test_plan_weighted_budget(self):
        plan = planner.build_plan(
            parent_query_id="root",
            subqueries=[
                {"query_id": "q1", "envelope": self._env("a"), "weight": 3.0},
                {"query_id": "q2", "envelope": self._env("b"), "weight": 1.0},
            ],
            total_budget={"max_evidence_count": 100},
        )
        self.assertEqual(plan.tasks[0].envelope["budget"]["max_evidence_count"], 75)
        self.assertEqual(plan.tasks[1].envelope["budget"]["max_evidence_count"], 25)

    def test_parallel_group_default_and_explicit(self):
        plan = planner.build_plan(
            parent_query_id="root",
            subqueries=[
                {"query_id": "q1", "envelope": self._env("a")},
                {"query_id": "q2", "envelope": self._env("b"), "parallel_group": 1},
            ],
        )
        self.assertEqual(plan.tasks[0].parallel_group, 0)
        self.assertEqual(plan.tasks[1].parallel_group, 1)

    def test_empty_subqueries_raises(self):
        with self.assertRaises(ValueError):
            planner.build_plan(parent_query_id="root", subqueries=[])

    def test_does_not_mutate_input_envelope(self):
        env = self._env("a")
        planner.build_plan(
            parent_query_id="root",
            subqueries=[{"query_id": "q1", "envelope": env}],
            total_budget={"max_evidence_count": 5},
        )
        # 原始入参 envelope 不应被注入 budget(build_plan 应深拷贝)
        self.assertNotIn("budget", env)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m unittest skills._shared.retrieval_protocol.tests.test_planner.TestBuildPlan -v`
Expected: FAIL（`AttributeError: build_plan` / `RetrievalTask`）

- [ ] **Step 3: 在 planner.py 追加 dataclass 与 build_plan**

在 `planner.py` 顶部 import 后、`_BUDGET_FIELDS` 附近加 import：

```python
import copy
```

在文件末尾追加：

```python
@dataclass(frozen=True)
class RetrievalTask:
    """一个并行可调度的 retrieve 任务。"""
    query_id: str
    envelope: dict[str, Any]
    parallel_group: int = 0


@dataclass
class Plan:
    """一条复合检索的拆解结果。"""
    parent_query_id: str
    tasks: list[RetrievalTask] = field(default_factory=list)
    total_budget: dict[str, Any] | None = None


def build_plan(
    *,
    parent_query_id: str,
    subqueries: list[dict[str, Any]],
    total_budget: dict[str, Any] | None = None,
) -> Plan:
    """把已路由好的子问题组织成 Plan;给定 total_budget 时按 weight 注入拆分预算。

    ``subqueries`` 每条 = ``{query_id, envelope, parallel_group?, weight?}``。
    本函数**深拷贝**每个 envelope,不修改调用方入参。若 ``total_budget`` 给出,
    按各子问题的 ``weight``(缺省 1.0)调用 :func:`split_budget`,把拆分后的
    budget 注入对应 task 的 ``envelope["budget"]``。
    """
    if not subqueries:
        raise ValueError("subqueries must be non-empty")

    envelopes = [copy.deepcopy(sq["envelope"]) for sq in subqueries]

    if total_budget is not None:
        weights = [float(sq.get("weight", 1.0)) for sq in subqueries]
        # 全部缺省权重时退化为等权(传 None 让 split_budget 走整除路径)
        use_weights = None if all(w == 1.0 for w in weights) else weights
        parts = split_budget(total_budget, len(subqueries), weights=use_weights)
        for env, part in zip(envelopes, parts):
            env["budget"] = part

    tasks = [
        RetrievalTask(
            query_id=sq["query_id"],
            envelope=env,
            parallel_group=int(sq.get("parallel_group", 0)),
        )
        for sq, env in zip(subqueries, envelopes)
    ]
    return Plan(parent_query_id=parent_query_id, tasks=tasks, total_budget=total_budget)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m unittest skills._shared.retrieval_protocol.tests.test_planner -v`
Expected: TestSplitBudget(7) + TestBuildPlan(6) 全 PASS

- [ ] **Step 5: 全量回归**

Run: `python3 -m unittest discover -s skills/_shared/retrieval_protocol/tests -t skills/_shared/retrieval_protocol 2>&1 | tail -3`
Expected: `Ran 297 tests ... OK`（291 + 6）

- [ ] **Step 6: Commit**

```bash
git add skills/_shared/retrieval_protocol/planner.py \
        skills/_shared/retrieval_protocol/tests/test_planner.py
git commit -m "feat(retrieval_protocol): planner build_plan + RetrievalTask/Plan

task.md 反馈 #3 的拆解编排结构层: subqueries(已路由好)→ Plan, 给定
total_budget 时按 weight 调 split_budget 注入各 task 的 envelope.budget。
深拷贝 envelope 不改入参。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 3：aggregator.py —— Hooks + 对齐/去重/排序（不含裁剪）

**Files:**
- Create: `skills/_shared/retrieval_protocol/aggregator.py`
- Test: `skills/_shared/retrieval_protocol/tests/test_aggregator.py`

**实现策略**：先做对齐 + 去重 + 排序，输出统一 SkillResult；预算裁剪放 Task 4。

- [ ] **Step 1: 写失败测试**

Create `skills/_shared/retrieval_protocol/tests/test_aggregator.py`：

```python
"""aggregator.py 单元测试 —— 对齐/去重/排序/预算裁剪。"""

from __future__ import annotations

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from retrieval_protocol import aggregator, planner  # noqa: E402


def _wrapper(evidence_id, score, text="x"):
    """构造一条最小 retrieval evidence wrapper。"""
    return {
        "evidence_ref": evidence_id,
        "type": "retrieval",
        "score": score,
        "payload": {"evidence_id": evidence_id, "data_type": "netflow", "text": text},
    }


def _skill_result(evidence):
    return {
        "schema_version": "1.1",
        "request_id": "r",
        "skill_name": "s",
        "scenario": "netflow",
        "capability": "evidence_search",
        "status": "success",
        "result": {"summary": {}, "findings": [], "evidence": evidence, "artifacts": []},
        "diagnostics": {},
        "errors": [],
    }


def _plan(query_ids, total_budget=None):
    tasks = [planner.RetrievalTask(query_id=q, envelope={}) for q in query_ids]
    return planner.Plan(parent_query_id="root", tasks=tasks, total_budget=total_budget)


class TestAggregateBasic(unittest.TestCase):
    def test_align_and_merge_two_buckets(self):
        plan = _plan(["q1", "q2"])
        results = [
            {"query_id": "q1", "skill_result": _skill_result([_wrapper("e1", 0.9)])},
            {"query_id": "q2", "skill_result": _skill_result([_wrapper("e2", 0.8)])},
        ]
        agg = aggregator.Aggregator()
        out = agg.aggregate(plan=plan, skill_results=results)
        ev = out["result"]["evidence"]
        self.assertEqual(len(ev), 2)
        self.assertEqual(out["status"], "success")

    def test_dedup_keeps_best_score(self):
        plan = _plan(["q1", "q2"])
        results = [
            {"query_id": "q1", "skill_result": _skill_result([_wrapper("dup", 0.5)])},
            {"query_id": "q2", "skill_result": _skill_result([_wrapper("dup", 0.95)])},
        ]
        out = aggregator.Aggregator().aggregate(plan=plan, skill_results=results)
        ev = out["result"]["evidence"]
        self.assertEqual(len(ev), 1)
        self.assertAlmostEqual(ev[0]["score"], 0.95)

    def test_global_sort_desc_by_score(self):
        plan = _plan(["q1"])
        results = [
            {"query_id": "q1", "skill_result": _skill_result([
                _wrapper("a", 0.3), _wrapper("b", 0.9), _wrapper("c", 0.6),
            ])},
        ]
        out = aggregator.Aggregator().aggregate(plan=plan, skill_results=results)
        scores = [w["score"] for w in out["result"]["evidence"]]
        self.assertEqual(scores, [0.9, 0.6, 0.3])

    def test_unaligned_query_id_still_included(self):
        plan = _plan(["q1"])
        results = [
            {"query_id": "q1", "skill_result": _skill_result([_wrapper("a", 0.5)])},
            {"query_id": "zzz", "skill_result": _skill_result([_wrapper("b", 0.7)])},
        ]
        out = aggregator.Aggregator().aggregate(plan=plan, skill_results=results)
        # 未对齐的桶仍并入(不静默丢弃)
        ids = {w["payload"]["evidence_id"] for w in out["result"]["evidence"]}
        self.assertEqual(ids, {"a", "b"})


class TestAggregateHooks(unittest.TestCase):
    def test_custom_dedup_key(self):
        plan = _plan(["q1"])
        # 两条 evidence_id 不同但 text 相同 → 自定义 dedup 按 text 去重
        results = [
            {"query_id": "q1", "skill_result": _skill_result([
                _wrapper("a", 0.5, text="same"), _wrapper("b", 0.9, text="same"),
            ])},
        ]
        hooks = aggregator.AggregatorHooks(
            dedup_key=lambda w: w["payload"]["text"],
        )
        out = aggregator.Aggregator(hooks).aggregate(plan=plan, skill_results=results)
        self.assertEqual(len(out["result"]["evidence"]), 1)
        self.assertAlmostEqual(out["result"]["evidence"][0]["score"], 0.9)

    def test_custom_sort_key(self):
        plan = _plan(["q1"])
        results = [
            {"query_id": "q1", "skill_result": _skill_result([
                _wrapper("a", 0.9), _wrapper("b", 0.3),
            ])},
        ]
        # 反向:按 score 升序
        hooks = aggregator.AggregatorHooks(sort_key=lambda w: w.get("score", 0.0))
        out = aggregator.Aggregator(hooks).aggregate(plan=plan, skill_results=results)
        scores = [w["score"] for w in out["result"]["evidence"]]
        self.assertEqual(scores, [0.3, 0.9])

    def test_empty_results(self):
        plan = _plan(["q1"])
        out = aggregator.Aggregator().aggregate(plan=plan, skill_results=[])
        self.assertEqual(out["result"]["evidence"], [])
        self.assertEqual(out["status"], "success")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m unittest skills._shared.retrieval_protocol.tests.test_aggregator -v`
Expected: FAIL（`No module named ... aggregator`）

- [ ] **Step 3: 实现 aggregator.py（不含裁剪）**

Create `skills/_shared/retrieval_protocol/aggregator.py`：

```python
"""检索结果聚合（纯 stdlib）—— task.md 反馈 #3 的聚合层。

把并行 retrieve 返回的多份 SkillResult 按 query_id 对齐成桶,逐桶去重,
全局排序,按 Plan 总预算兜底裁剪,产出一份统一 SkillResult。

对齐契约: ``skill_results`` 每条 = ``{"query_id": str, "skill_result": dict}``
(上层 PlannerMiddleware 派发时天然知道每个 result 对应哪个 query_id)。

设计来源:历史 spec docs/superpowers/specs/2026-05-27-... §4.2。
本模块仅依赖 Python 标准库 + 包内 evidence/errors 构造器。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .errors import build_error, STATUS_PARTIAL
from .evidence import build_skill_result, build_summary
from .planner import Plan


def _default_dedup_key(wrapper: dict[str, Any]) -> str:
    return str(wrapper.get("payload", {}).get("evidence_id", ""))


def _default_sort_key(wrapper: dict[str, Any]) -> float:
    # 升序排序键:取负分 → score 高者在前
    return -float(wrapper.get("score") or 0.0)


def _default_token_estimator(wrapper: dict[str, Any]) -> int:
    text = wrapper.get("payload", {}).get("text", "")
    return len(text) // 4 if isinstance(text, str) else 0


@dataclass
class AggregatorHooks:
    """可插拔策略;任一为 None 走对应默认实现。"""
    dedup_key: Callable[[dict[str, Any]], str] | None = None
    sort_key: Callable[[dict[str, Any]], float] | None = None
    token_estimator: Callable[[dict[str, Any]], int] | None = None


class Aggregator:
    """按 Plan 把多份 SkillResult 对齐/去重/排序/裁剪成一份。"""

    def __init__(self, hooks: AggregatorHooks | None = None) -> None:
        hooks = hooks or AggregatorHooks()
        self._dedup_key = hooks.dedup_key or _default_dedup_key
        self._sort_key = hooks.sort_key or _default_sort_key
        self._token_estimator = hooks.token_estimator or _default_token_estimator

    def aggregate(
        self,
        *,
        plan: Plan,
        skill_results: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """对齐 → 去重 → 排序（→ 裁剪在 Task 4 补）。返回统一 SkillResult。"""
        # 1. 收集所有 wrapper(按出现顺序),逐桶去重
        deduped = self._collect_and_dedup(skill_results)
        # 2. 全局排序
        deduped.sort(key=self._sort_key)
        # 3. 组装统一 SkillResult
        errors: list[dict[str, Any]] = []
        status = "success"
        return self._build_result(deduped, errors=errors, status=status)

    def _collect_and_dedup(
        self, skill_results: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """逐桶按 dedup_key 去重,保留 sort_key 最优一条;桶间合并后再全局去重。"""
        best: dict[str, dict[str, Any]] = {}
        order: list[str] = []
        for item in skill_results:
            sr = item.get("skill_result") or {}
            evidence = sr.get("result", {}).get("evidence", []) or []
            for wrapper in evidence:
                key = self._dedup_key(wrapper)
                if key not in best:
                    best[key] = wrapper
                    order.append(key)
                else:
                    # 保留 sort_key 更优(更小)的一条
                    if self._sort_key(wrapper) < self._sort_key(best[key]):
                        best[key] = wrapper
        return [best[k] for k in order]

    def _build_result(
        self,
        evidence: list[dict[str, Any]],
        *,
        errors: list[dict[str, Any]],
        status: str,
    ) -> dict[str, Any]:
        summary = build_summary(
            title="聚合检索证据",
            overview=f"对齐去重排序后保留 {len(evidence)} 条证据。",
        )
        return build_skill_result(
            skill_name="retrieval-aggregator",
            scenario="aggregate",
            capability="evidence_aggregate",
            status=status,
            summary=summary,
            evidence=evidence,
            errors=errors,
        )
```

**注意**：确认 `build_summary` 的签名（在 evidence.py）。若 `build_summary` 不接受 `title`/`overview` 关键字，read evidence.py 对齐参数名后再写。

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m unittest skills._shared.retrieval_protocol.tests.test_aggregator -v`
Expected: TestAggregateBasic(4) + TestAggregateHooks(3) 全 PASS

- [ ] **Step 5: 全量回归**

Run: `python3 -m unittest discover -s skills/_shared/retrieval_protocol/tests -t skills/_shared/retrieval_protocol 2>&1 | tail -3`
Expected: `Ran 304 tests ... OK`（297 + 7）

- [ ] **Step 6: Commit**

```bash
git add skills/_shared/retrieval_protocol/aggregator.py \
        skills/_shared/retrieval_protocol/tests/test_aggregator.py
git commit -m "feat(retrieval_protocol): aggregator 对齐/去重/排序

task.md 反馈 #3 的聚合层: 多份 SkillResult 按 query_id 桶收集, 按
dedup_key 去重(保留 sort_key 最优), 全局排序, 产出统一 SkillResult。
dedup/sort/token 三个 hook 可覆盖默认。裁剪逻辑下个 task 补。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 4：aggregator.py —— 预算裁剪 + E_OUT_OF_BUDGET + status=partial

**Files:**
- Modify: `skills/_shared/retrieval_protocol/aggregator.py`（aggregate 增裁剪 3-5 步）
- Test: `skills/_shared/retrieval_protocol/tests/test_aggregator.py`（新增 TestAggregateBudget）

- [ ] **Step 1: 写失败测试**

在 `test_aggregator.py` 追加：

```python
class TestAggregateBudget(unittest.TestCase):
    def test_clip_by_max_evidence_count(self):
        plan = _plan(["q1"], total_budget={"max_evidence_count": 2})
        results = [
            {"query_id": "q1", "skill_result": _skill_result([
                _wrapper("a", 0.9), _wrapper("b", 0.8), _wrapper("c", 0.7),
            ])},
        ]
        out = aggregator.Aggregator().aggregate(plan=plan, skill_results=results)
        ev = out["result"]["evidence"]
        self.assertEqual(len(ev), 2)
        # 保留分高的前 2
        self.assertEqual([w["payload"]["evidence_id"] for w in ev], ["a", "b"])
        self.assertEqual(out["status"], "partial")
        codes = [e["code"] for e in out["errors"]]
        self.assertIn("E_OUT_OF_BUDGET", codes)

    def test_clip_by_max_token_estimate(self):
        plan = _plan(["q1"], total_budget={"max_token_estimate": 5})
        # token = len(text)//4; text 长 20 → 5 token 一条就到顶
        results = [
            {"query_id": "q1", "skill_result": _skill_result([
                _wrapper("a", 0.9, text="x" * 20),
                _wrapper("b", 0.8, text="x" * 20),
            ])},
        ]
        out = aggregator.Aggregator().aggregate(plan=plan, skill_results=results)
        ev = out["result"]["evidence"]
        self.assertEqual(len(ev), 1)
        self.assertEqual(ev[0]["payload"]["evidence_id"], "a")
        self.assertEqual(out["status"], "partial")
        self.assertIn("E_OUT_OF_BUDGET", [e["code"] for e in out["errors"]])

    def test_no_clip_when_within_budget(self):
        plan = _plan(["q1"], total_budget={"max_evidence_count": 10})
        results = [
            {"query_id": "q1", "skill_result": _skill_result([
                _wrapper("a", 0.9), _wrapper("b", 0.8),
            ])},
        ]
        out = aggregator.Aggregator().aggregate(plan=plan, skill_results=results)
        self.assertEqual(len(out["result"]["evidence"]), 2)
        self.assertEqual(out["status"], "success")
        self.assertEqual(out["errors"], [])

    def test_no_budget_no_clip(self):
        plan = _plan(["q1"])  # total_budget=None
        results = [
            {"query_id": "q1", "skill_result": _skill_result([
                _wrapper(f"e{i}", 0.5) for i in range(50)
            ])},
        ]
        out = aggregator.Aggregator().aggregate(plan=plan, skill_results=results)
        self.assertEqual(len(out["result"]["evidence"]), 50)
        self.assertEqual(out["status"], "success")
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m unittest skills._shared.retrieval_protocol.tests.test_aggregator.TestAggregateBudget -v`
Expected: FAIL（当前 aggregate 不裁剪，count/token 测试不通过）

- [ ] **Step 3: 在 aggregate 中加裁剪逻辑**

修改 `aggregator.py` 的 `aggregate` 方法，替换为：

```python
    def aggregate(
        self,
        *,
        plan: Plan,
        skill_results: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """对齐 → 去重 → 排序 → 按 plan.total_budget 兜底裁剪。返回统一 SkillResult。"""
        deduped = self._collect_and_dedup(skill_results)
        deduped.sort(key=self._sort_key)

        kept, clipped = self._clip_to_budget(deduped, plan.total_budget)

        errors: list[dict[str, Any]] = []
        status = "success"
        if clipped:
            errors.append(build_error(
                code="E_OUT_OF_BUDGET",
                message=(
                    f"聚合证据超预算,已裁剪 {clipped} 条,保留 {len(kept)} 条。"
                ),
                detail={"kept": len(kept), "clipped": clipped},
            ))
            status = STATUS_PARTIAL
        return self._build_result(kept, errors=errors, status=status)

    def _clip_to_budget(
        self,
        evidence: list[dict[str, Any]],
        total_budget: dict[str, Any] | None,
    ) -> tuple[list[dict[str, Any]], int]:
        """按 total_budget 裁剪;返回 (保留列表, 被裁剪条数)。无预算则不裁。"""
        if not total_budget:
            return evidence, 0
        original = len(evidence)
        kept = evidence

        max_count = total_budget.get("max_evidence_count")
        if isinstance(max_count, int) and not isinstance(max_count, bool):
            kept = kept[:max_count]

        max_token = total_budget.get("max_token_estimate")
        if isinstance(max_token, int) and not isinstance(max_token, bool):
            budgeted: list[dict[str, Any]] = []
            running = 0
            for wrapper in kept:
                running += self._token_estimator(wrapper)
                if running > max_token:
                    break
                budgeted.append(wrapper)
            kept = budgeted

        return kept, original - len(kept)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m unittest skills._shared.retrieval_protocol.tests.test_aggregator -v`
Expected: TestAggregateBasic(4) + TestAggregateHooks(3) + TestAggregateBudget(4) 全 PASS

- [ ] **Step 5: 全量回归**

Run: `python3 -m unittest discover -s skills/_shared/retrieval_protocol/tests -t skills/_shared/retrieval_protocol 2>&1 | tail -3`
Expected: `Ran 308 tests ... OK`（304 + 4）

- [ ] **Step 6: Commit**

```bash
git add skills/_shared/retrieval_protocol/aggregator.py \
        skills/_shared/retrieval_protocol/tests/test_aggregator.py
git commit -m "feat(retrieval_protocol): aggregator 预算兜底裁剪 + E_OUT_OF_BUDGET

聚合层裁剪 5 步收尾: 排序后按 max_evidence_count 截前 N, 再按
max_token_estimate 累计截断; 任一裁剪发生 → status=partial +
errors 追加 E_OUT_OF_BUDGET(detail 记 kept/clipped 数)。无预算不裁。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 5：__init__.py 公开 planner / aggregator API

**Files:**
- Modify: `skills/_shared/retrieval_protocol/__init__.py`

- [ ] **Step 1: 写失败测试（公开 API 存在性）**

新建 `skills/_shared/retrieval_protocol/tests/test_planner_aggregator_api.py`：

```python
"""planner / aggregator 公开 API 可从包顶层 import。"""

from __future__ import annotations

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))


class TestPublicAPI(unittest.TestCase):
    def test_planner_exports(self):
        import retrieval_protocol as rp
        for name in ("split_budget", "build_plan", "RetrievalTask", "Plan"):
            self.assertTrue(hasattr(rp, name), f"missing {name}")
            self.assertIn(name, rp.__all__, f"{name} not in __all__")

    def test_aggregator_exports(self):
        import retrieval_protocol as rp
        for name in ("Aggregator", "AggregatorHooks"):
            self.assertTrue(hasattr(rp, name), f"missing {name}")
            self.assertIn(name, rp.__all__, f"{name} not in __all__")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m unittest skills._shared.retrieval_protocol.tests.test_planner_aggregator_api -v`
Expected: FAIL（`missing split_budget` 等）

- [ ] **Step 3: 在 __init__.py 追加 import 与 __all__**

在 `__init__.py` 的 import 段（`from .validate import ...` 之后、`__all__` 之前）加：

```python
from .planner import (
    Plan,
    RetrievalTask,
    build_plan,
    split_budget,
)
from .aggregator import (
    Aggregator,
    AggregatorHooks,
)
```

在 `__all__` 列表中（建议放在 errors 段之后、sensitivity_rules 段之前，并加分组注释）追加：

```python
    # planner / aggregator —— task.md 反馈 #2/#3 编排层(S2)
    "Plan",
    "RetrievalTask",
    "build_plan",
    "split_budget",
    "Aggregator",
    "AggregatorHooks",
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m unittest skills._shared.retrieval_protocol.tests.test_planner_aggregator_api -v`
Expected: 2 PASS

- [ ] **Step 5: 全量回归**

Run: `python3 -m unittest discover -s skills/_shared/retrieval_protocol/tests -t skills/_shared/retrieval_protocol 2>&1 | tail -3`
Expected: `Ran 310 tests ... OK`（308 + 2）

- [ ] **Step 6: Commit**

```bash
git add skills/_shared/retrieval_protocol/__init__.py \
        skills/_shared/retrieval_protocol/tests/test_planner_aggregator_api.py
git commit -m "feat(retrieval_protocol): 公开 planner/aggregator API

包顶层导出 split_budget / build_plan / RetrievalTask / Plan /
Aggregator / AggregatorHooks, 并入 __all__。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 6：README 新增 Planner/Aggregator 章节

**Files:**
- Modify: `skills/_shared/retrieval_protocol/README.md`

- [ ] **Step 1: 在 README 末尾追加章节**

```markdown
## 编排层：Planner / Aggregator（S2，task.md 反馈 #2/#3）

纯 stdlib，无 LLM、无 Skill 路由、无 LangGraph 接入（那是 S3，单开分支）。

### Planner（`planner.py`）

- `split_budget(total, fan_out, weights=None)`：把总 `budget`（`max_evidence_count` / `max_token_estimate`）按等权或加权拆给 N 个并行 retrieve；整除/取整余数补给第一个任务，保证每字段拆分后 sum 与 total 一致。
- `build_plan(*, parent_query_id, subqueries, total_budget=None)`：把**已路由好**的子问题（`{query_id, envelope, parallel_group?, weight?}`）组织成 `Plan`；给定 `total_budget` 时按 weight 注入各 task 的 `envelope["budget"]`。深拷贝 envelope，不改入参。
- 不含 LLM 拆问题语义与 SkillRouter —— 那是 S3 PlannerMiddleware 的职责。

### Aggregator（`aggregator.py`）

- 对齐契约：`aggregate(*, plan, skill_results)`，`skill_results` 每条 = `{"query_id": str, "skill_result": dict}`。
- 裁剪 5 步：① 桶内按 `dedup_key` 去重（保留 `sort_key` 最优）→ ② 全局按 `sort_key` 排序 → ③ 有 `max_evidence_count` 截前 N → ④ 有 `max_token_estimate` 累计 token 超限即丢后续 → ⑤ 任一裁剪发生 → `status="partial"` + `errors` 追加 `E_OUT_OF_BUDGET`。
- `AggregatorHooks` 可覆盖 `dedup_key`（默认 `payload.evidence_id`）/ `sort_key`（默认 `-score`）/ `token_estimator`（默认 `len(text)//4`）。
- 未对齐到 plan 的桶仍并入结果，不静默丢弃。

> **S3（下分支）**：`PlannerMiddleware`（`before_model` 调 LLM 拆子问题 → `build_plan`）+ `AggregatorMiddleware`（`after_model` 收集 retrieve 型 SkillResult → `Aggregator.aggregate`），挂在 `TodoListMiddleware` 之后、`MemoryMiddleware` 之前，由 `config.configurable.retrieval_planning_enabled`（默认 False）开关。
```

- [ ] **Step 2: 全量回归（保险）**

Run: `python3 -m unittest discover -s skills/_shared/retrieval_protocol/tests -t skills/_shared/retrieval_protocol 2>&1 | tail -3`
Expected: `Ran 310 tests ... OK`

- [ ] **Step 3: Commit**

```bash
git add skills/_shared/retrieval_protocol/README.md
git commit -m "docs(retrieval_protocol): README 增 Planner/Aggregator 章节

记录 S2 编排层 API(split_budget/build_plan/Aggregator)与裁剪 5 步,
并标注 S3 LangGraph 中间件接入留待下分支。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 7：完成记录 + 全量回归

**Files:**
- Modify: `docs/superpowers/plans/2026-05-29-planner-aggregator-stdlib.md`（本文件）

- [ ] **Step 1: 全量回归 + 计数**

Run: `python3 -m unittest discover -s skills/_shared/retrieval_protocol/tests -t skills/_shared/retrieval_protocol 2>&1 | tail -3`
Expected: `Ran 310 tests ... OK`（284 基线 + 26 新）

- [ ] **Step 2: 在本文件末尾追加完成记录**（基线 284 / 完成 310 / commits 列表 / 遗留 S3）

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/plans/2026-05-29-planner-aggregator-stdlib.md
git commit -m "docs(plan): 标记 planner-aggregator-stdlib 完成

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

- [ ] **Step 4: 告知用户 task 完成，S3 待后续分支。**

---

## Self-Review 检查

**1. Spec coverage**（对照 task.md #2 / #3 + 历史 spec §4）：
- #2 Planner 拆预算 → Task 1（split_budget）+ Task 2（build_plan 注入）
- #2 聚合层兜底裁剪 → Task 4
- #3 拆解编排结构 → Task 2（build_plan）
- #3 聚合层对齐/去重/排序 → Task 3
- #3 query_id 对齐 → Task 3（对齐契约）
- 公开 API → Task 5；文档 → Task 6
- S3 LangGraph → 明确标注不做，留下分支

**2. Placeholder scan**：每个代码步骤均有完整代码块。唯一需运行时确认的是 `build_summary` 签名（Task 3 Step 3 已注明：若关键字不符则 read evidence.py 对齐）。

**3. Type 一致性**：
- `Plan` / `RetrievalTask` 在 Task 2 定义，Task 3/4 测试 import 使用，字段名一致（`parent_query_id` / `tasks` / `total_budget` / `query_id` / `envelope` / `parallel_group`）
- `split_budget` 签名在 Task 1 定义，Task 2 build_plan 调用一致
- aggregate 返回 SkillResult，用 `build_skill_result`，字段 `result.evidence` / `status` / `errors` 与既有 schema 一致
- `STATUS_PARTIAL` / `build_error` / `build_skill_result` / `build_summary` 均从包内 import，名称与现有 errors.py / evidence.py 一致

---

**Execution Handoff**：本 plan 完成。subagent-driven 执行（每 task fresh implementer + spec/quality 双 review）。

---

## 完成记录

- **执行模式**：subagent-driven-development（fresh implementer + spec reviewer + code quality reviewer）
- **执行时间**：2026-05-29
- **基线测试数**：284（S2 启动前 `67e08db`）
- **完成后测试数**：**315**（+31 全 PASS）
- **新增测试明细**：
  - T1 split_budget：+7（+ T2 顺带补 2 条拒绝路径 = 共 9）
  - T2 build_plan：+6（+ T7 补 1 条嵌套深拷贝断言）
  - T3 aggregator 对齐/去重/排序：+7
  - T4 预算裁剪：+4（+ fix 补 combined-clip / 0-kept 边界 2 条 = 共 6）
  - T5 公开 API：+2
  - T7 deepcopy 强化：+1
- **commits**（7 + 1 fix + 完成记录）：
  - `1e856fc` feat: planner.split_budget 拆预算
  - `713e8ff` feat: planner build_plan + RetrievalTask/Plan
  - `4c35f9c` feat: aggregator 对齐/去重/排序
  - `d794adc` feat: aggregator 预算兜底裁剪 + E_OUT_OF_BUDGET
  - `99dbb83` test: aggregator 补 combined-clip + 0-kept 边界 + 文档硬上限语义（T4 fix）
  - `39a44d0` feat: 公开 planner/aggregator API
  - `d680963` docs: README 增 Planner/Aggregator 章节
  - （T7 deepcopy 测试 + 本完成记录一并提交）
- **影响的公开 API**：仅**新增** `split_budget` / `build_plan` / `RetrievalTask` / `Plan` / `Aggregator` / `AggregatorHooks`，既有导出零改动
- **关键设计决策**：
  - 对齐契约 = `list[{"query_id", "skill_result"}]`（S3 PlannerMiddleware 派发时天然知道配对，不依赖 request_id 串改）
  - 全局去重（非逐桶）：跨桶同 evidence_id 也收敛，保留 sort_key 最优
  - budget 是**硬上限**：单条 evidence 超 max_token_estimate → 0 保留（有意为之，宁空不撑爆，附 E_OUT_OF_BUDGET + partial）
  - 未对齐到 plan 的桶仍并入，不静默丢弃
- **覆盖 task.md 反馈**：#2 Planner 拆预算 ✅ + 聚合层兜底裁剪 ✅；#3 拆解编排结构 ✅ + 对齐/去重/排序/裁剪 ✅
- **遗留（S3，下分支）**：`PlannerMiddleware`（LLM 拆子问题）+ `AggregatorMiddleware`（LangGraph 接入），耦合 LeadAgent 中间件链，原设计即建议单开分支；`config.configurable.retrieval_planning_enabled` 开关默认 False

所有 spec reviewer 与 code quality reviewer 均 ✅；T3/T4 各一次 reviewer-driven 文档/测试补强已落地。
