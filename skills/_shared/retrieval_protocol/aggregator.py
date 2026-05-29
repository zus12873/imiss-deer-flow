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
