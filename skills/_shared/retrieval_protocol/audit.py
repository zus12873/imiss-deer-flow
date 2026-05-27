"""审计动作 / 闸门 / 场景 / 原因码枚举常量。

spec 2026-05-27 §4。本模块仅依赖 Python 标准库。

风险值脱敏护栏意图: 后续 Task 6 的 build_evidence_action / validate_evidence_action
将拒绝任何含原始敏感值的 risk_locations —— 审计日志不得成为二次泄露源。
dataclass / Any 已在此预导入供 Task 6 直接使用。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# spec §4.2: action 枚举
AUDIT_ACTIONS: frozenset[str] = frozenset({
    "allow", "warn", "desensitize", "aggregate",
    "rewrite", "filter", "refuse", "manual_review",
})

# spec §4.2: action_status 枚举
AUDIT_ACTION_STATUSES: frozenset[str] = frozenset({"applied", "pending", "failed"})

# spec §4.1: gate 枚举
AUDIT_GATES: frozenset[str] = frozenset({"InputGate", "ContextGate", "OutputGate"})

# spec §4.1: scene 枚举
AUDIT_SCENES: frozenset[str] = frozenset({
    "self_use", "internal_org", "cross_org", "public_release", "research_anon",
})

# spec §4.2: reason_code 初始集(首版按合规反馈,后续可扩)
AUDIT_REASON_CODES: frozenset[str] = frozenset({
    "struct_id_detected",
    "geo_loc_with_object_time",
    "re_identify_combo_risk",
    "secret_token_detected",
    "small_sample_k_below_threshold",
    "unmasked_face_or_plate",
    "streaming_link_present",
    "object_level_risk_label",
    "sensitive_facility_marker",
    "public_source_confirmed",
})
