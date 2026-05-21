"""schema 常量与登记表 —— task.md §2（数据类型分组）与 §4.4（features 注册建议）。

新增数据类型时，只需在本模块登记 ``data_type`` 取值与 ``FEATURES_REGISTRY`` 子
字段，外层 Input Envelope / SkillResult 信封不动（task.md §1「可扩展」）。

本模块仅依赖 Python 标准库。
"""

from __future__ import annotations

# task.md §3 / §4：协议版本号。
SCHEMA_VERSION = "1.0"

# task.md §2：数据类型分组。分组只为复用召回逻辑，与 SkillRouter 的 scenes 无关。
#   structured —— 结构化 / 表格
#   text       —— 文本
#   image      —— 图像
#   video      —— 视频
DATA_TYPE_GROUPS: dict[str, tuple[str, ...]] = {
    "structured": ("spatiotemporal_trajectory", "traffic_flow", "gazetteer", "netflow", "telecom"),
    "text": ("code", "policy"),
    "image": ("streetview", "remote_sensing"),
    "video": ("surveillance",),
}

# 全部登记的 data_type 取值 —— task.md §7 校验规则 4 的唯一来源，禁止临时造别名。
DATA_TYPES: frozenset[str] = frozenset(dt for members in DATA_TYPE_GROUPS.values() for dt in members)

# task.md §4.4：各 data_type 的 features 注册建议。这是「建议」而非硬约束 ——
# §7 校验规则 2 只要求 meta.features 存在且为对象，不要求具体子字段齐全。
FEATURES_REGISTRY: dict[str, tuple[str, ...]] = {
    "spatiotemporal_trajectory": ("checkin_count", "unique_users", "top_categories", "wow_change_pct", "anomaly_flag"),
    "traffic_flow": ("flow_count", "peak_hour", "avg_speed", "congestion_level", "wow_change_pct", "anomaly_flag"),
    "gazetteer": ("metric_name", "value", "unit", "year", "region"),
    "netflow": ("src_ip", "dst_ip", "protocol", "bytes", "packets", "flow_duration", "ja3_hash", "anomaly_flag"),
    "telecom": ("call_count", "unique_contacts", "community_id", "duration_sum"),
    "code": ("doc_id", "snippet", "lang", "ast_node_type", "symbol"),
    "policy": ("doc_id", "snippet", "policy_number", "effective_date", "issuer"),
    "streetview": ("objects", "bbox", "taken_at"),
    "remote_sensing": ("objects", "bbox", "tile_id", "taken_at", "change_score"),
    "surveillance": ("objects", "bbox", "clip_start", "clip_end", "behavior"),
}

# task.md §3.3：时间语义。absolute 用真实墙钟时间，relative 用相对采集起点。
TIME_RANGE_MODES: frozenset[str] = frozenset({"absolute", "relative"})

# task.md §3.2：检索策略与运行档位。
RETRIEVAL_STRATEGIES: frozenset[str] = frozenset({"bm25", "vector", "hybrid"})
RUN_MODES: frozenset[str] = frozenset({"auto", "es", "local", "demo"})

# task.md §4.3：隐私字段取值。
SENSITIVITY_LEVELS: frozenset[str] = frozenset({"open", "aggregated_safe", "pii_masked", "restricted"})
ACCESS_POLICIES: frozenset[str] = frozenset({"open", "restricted", "internal_only"})
# 视为隐私敏感、必须同时声明 access_policy 的 sensitivity_level 取值（task.md §7 规则 7）。
SENSITIVE_LEVELS: frozenset[str] = frozenset({"pii_masked", "restricted"})

# task.md §4.1 / §7 规则 1：evidence wrapper 的检索型取值。
EVIDENCE_TYPE_RETRIEVAL = "retrieval"

# SkillResult 顶层 status 的约定取值。task.md §4.1 示例用 "success"；其余为常见约定。
SKILL_RESULT_STATUSES: frozenset[str] = frozenset({"success", "partial", "error"})


def data_type_group(data_type: str) -> str | None:
    """返回 ``data_type`` 所属大类（structured/text/image/video）；未登记返回 ``None``。"""
    for group, members in DATA_TYPE_GROUPS.items():
        if data_type in members:
            return group
    return None


def is_registered_data_type(data_type: str) -> bool:
    """``data_type`` 是否为 task.md §2 登记的取值。"""
    return data_type in DATA_TYPES
