"""敏感度落档规则 —— spec 2026-05-27 §3。

把师兄 2026-05-27 给出的四档语义与 6 类升降级规则锚定为代码常量与判定函数。
adapter 在构造 evidence_unit 时调用 :func:`classify_sensitivity` 做保守预标;
最终违规判定 / 处置仍由合规检测器统一决策。本模块仅依赖 Python 标准库。
"""

from __future__ import annotations

# spec §3.2.1: 6 类受改 data_type 默认级别表。
# (gazetteer 由 adapt_road_traffic_hit 输出 —— task.md §6.3 既有实现)
DEFAULT_SENSITIVITY: dict[str, tuple[str, str]] = {
    "gazetteer":      ("aggregated_safe", "open"),
    "telecom":        ("pii_masked",      "internal_only"),
    "code":           ("pii_masked",      "internal_only"),
    "streetview":     ("pii_masked",      "internal_only"),
    "remote_sensing": ("aggregated_safe", "open"),
    "surveillance":   ("restricted",      "restricted"),
}

# 本次不动的 4 类(保持现有 adapter 硬编码默认):
# spatiotemporal_trajectory / netflow / policy / traffic_flow

# spec §3.1: 第一阶段 k 阈值 —— 主体数 >= 10 才算安全聚合。
K_THRESHOLD_AGGREGATED_SAFE = 10
