# Adapter 敏感度预标规则 + Audit Sink 字段扩展 —— 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 `skills/_shared/retrieval_protocol/` 6 类 adapter 按 evidence 字段
内容做保守敏感度预标，并把 `RetrievalMiddleware` 审计日志扩展到合规组可消费的
字段集（gate / scene / evidence_actions / policy_version / detector_version）。

**Architecture:** 新增 `sensitivity_rules.py` 把师兄给的四档语义 + 6 类升降级
规则锚定为代码常量与判定基元；6 个目标 adapter 在构造 `evidence_unit` 时调用
`classify_sensitivity` 覆盖现有硬编码；新增 `audit.py` 集中登记审计动作 / 闸门 /
场景 / 原因码等枚举与 `EvidenceAction` 构造校验；`middleware.py` 的 `call` 加可选
入参并把字段写入 audit record；默认 sink 复用 `JsonlSink`。**stdlib only**，不改
`SKILL.md` / `Skill` / `SkillResponse` / backend。

**Tech Stack:** Python 3.11+ 标准库（dataclasses / typing / re / json / unittest）。

**Spec:** `docs/superpowers/specs/2026-05-27-retrieval-profile-and-planner-aggregator-design.md`

---

## 文件结构

| 路径 | 动作 | 责任 |
|---|---|---|
| `skills/_shared/retrieval_protocol/schema.py` | 修改 | 在文件头追加四档语义锚定注释；不改变量 |
| `skills/_shared/retrieval_protocol/sensitivity_rules.py` | **新增** | DEFAULT_SENSITIVITY / K_THRESHOLD_AGGREGATED_SAFE / 8 判定基元 / classify_sensitivity |
| `skills/_shared/retrieval_protocol/adapters.py` | 修改 | 6 类 adapter (road_traffic/telecom/code/streetview/remote_sensing/surveillance) 改调 classify_sensitivity |
| `skills/_shared/retrieval_protocol/audit.py` | **新增** | AUDIT_ACTIONS / AUDIT_ACTION_STATUSES / AUDIT_GATES / AUDIT_SCENES / AUDIT_REASON_CODES / EvidenceAction / build_evidence_action / validate_evidence_action |
| `skills/_shared/retrieval_protocol/middleware.py` | 修改 | RetrievalMiddleware.call 增可选入参；_emit_audit 字段补全 |
| `skills/_shared/retrieval_protocol/__init__.py` | 修改 | 公开新模块 API |
| `skills/_shared/retrieval_protocol/README.md` | 修改 | 增"敏感度落档"+"审计字段"两章节 |
| `skills/_shared/retrieval_protocol/tests/test_sensitivity_rules.py` | **新增** | classify_sensitivity ≥ 25 unittest |
| `skills/_shared/retrieval_protocol/tests/test_audit.py` | **新增** | build/validate_evidence_action + 风险值脱敏护栏 ≥ 12 unittest |
| `skills/_shared/retrieval_protocol/tests/test_new_adapters.py` | 修改 | 6 类 adapter 集成断言：默认 / 升 / 降级路径 |
| `skills/_shared/retrieval_protocol/tests/test_middleware.py` | 修改 | call 扩展入参向后兼容 + audit record 字段齐全 |

---

## 工作目录与重跑命令

所有命令的工作目录：`/Users/huanmeng/Downloads/Projects/imiss-deer-flow/skills/_shared`。

跑全部 retrieval_protocol 测试：

```bash
cd /Users/huanmeng/Downloads/Projects/imiss-deer-flow/skills/_shared
python3 -m unittest discover -s retrieval_protocol/tests -t . -v
```

跑单文件：

```bash
cd /Users/huanmeng/Downloads/Projects/imiss-deer-flow/skills/_shared
python3 -m unittest retrieval_protocol.tests.test_sensitivity_rules -v
```

---

## Task 0：schema.py 锁四档语义注释

**Files:**
- Modify: `skills/_shared/retrieval_protocol/schema.py:53-57`

- [ ] **Step 1：把四档语义注释打到 schema.py 头部 SENSITIVITY_LEVELS 上方**

把现有 `SENSITIVITY_LEVELS` / `ACCESS_POLICIES` / `SENSITIVE_LEVELS` 三个常量
**保持不变**，仅在 `SENSITIVITY_LEVELS` 定义上方补一段 docstring 注释。

打开 `skills/_shared/retrieval_protocol/schema.py`，找到（约第 53 行起）：

```python
# task.md §4.3：隐私字段取值。
SENSITIVITY_LEVELS: frozenset[str] = frozenset({"open", "aggregated_safe", "pii_masked", "restricted"})
ACCESS_POLICIES: frozenset[str] = frozenset({"open", "restricted", "internal_only"})
# 视为隐私敏感、必须同时声明 access_policy 的 sensitivity_level 取值（task.md §7 规则 7）。
SENSITIVE_LEVELS: frozenset[str] = frozenset({"pii_masked", "restricted"})
```

替换为：

```python
# task.md §4.3：隐私字段取值。
#
# 四档语义锚定（spec 2026-05-27 §3.1）：
#   open
#     已公开、普通、基本不敏感的 evidence。例：公开政策法规、公开年鉴说明、
#     公开指标解释、普通公开文本。不含个人/设备/账号/车辆/精确位置/通道链接/
#     凭证密钥/内部研判/对象级风险标签。对应 access_policy=open。
#   aggregated_safe
#     只含聚合统计、不能定位到单个对象的 evidence。例：count/sum/avg/ratio/
#     flow_count/unique_count/duration_sum/change_score。第一阶段建议
#     k>=10 才算安全聚合(k = 该统计覆盖的可区分主体数：用户/号码/车辆/设备/
#     目标/点位/社区成员/统计样本)。k<10 或聚合结合具体位置/时间/人群特征/
#     风险标签 → 应升 restricted 或人工复核。对应 access_policy=open。
#   pii_masked
#     含对象/设备/车辆/图像目标/代码符号等敏感字段，但字段值已经哈希/脱敏/
#     泛化/匿名化/打码。已脱敏但建议内部使用，不是公开安全。
#     对应 access_policy=internal_only。
#   restricted
#     高敏 evidence，不能直接进 LLM 或直接输出。例：明文身份证/手机号/银行卡/
#     邮箱/IMEI/IP/MAC、精确经纬度、详细门牌、对象+时间+位置组合、通话内容、
#     单对象通信明细、对象级风险标签、视频 stream_url/playback_url/
#     channel_id/camera_id、具体监控点位、未打码人脸/车牌、人员轨迹、
#     代码中的 password/token/api_key/secret/private_key/数据库连接串/
#     内部服务地址、敏感设施点位、内部遥感标注。对应 access_policy=restricted。
SENSITIVITY_LEVELS: frozenset[str] = frozenset({"open", "aggregated_safe", "pii_masked", "restricted"})
ACCESS_POLICIES: frozenset[str] = frozenset({"open", "restricted", "internal_only"})
# 视为隐私敏感、必须同时声明 access_policy 的 sensitivity_level 取值（task.md §7 规则 7）。
SENSITIVE_LEVELS: frozenset[str] = frozenset({"pii_masked", "restricted"})
```

- [ ] **Step 2：跑现有 schema 测试确认未破**

```bash
cd /Users/huanmeng/Downloads/Projects/imiss-deer-flow/skills/_shared
python3 -m unittest retrieval_protocol.tests.test_schema -v
```

Expected: **15 个用例全 PASS**。

- [ ] **Step 3：commit**

```bash
cd /Users/huanmeng/Downloads/Projects/imiss-deer-flow
git add skills/_shared/retrieval_protocol/schema.py
git commit -m "docs(retrieval_protocol): 锁四档敏感度语义到 schema.py 注释"
```

---

## Task 1：sensitivity_rules.py —— DEFAULT_SENSITIVITY 与基线常量

**Files:**
- Create: `skills/_shared/retrieval_protocol/sensitivity_rules.py`
- Create: `skills/_shared/retrieval_protocol/tests/test_sensitivity_rules.py`

- [ ] **Step 1：写失败测试**

创建 `skills/_shared/retrieval_protocol/tests/test_sensitivity_rules.py`：

```python
"""敏感度落档规则单测 —— spec 2026-05-27 §3."""
from __future__ import annotations

import unittest

from retrieval_protocol import sensitivity_rules as sr


class TestDefaultTable(unittest.TestCase):
    def test_six_data_types_present(self):
        expected = {
            "gazetteer":      ("aggregated_safe", "open"),
            "telecom":        ("pii_masked",      "internal_only"),
            "code":           ("pii_masked",      "internal_only"),
            "streetview":     ("pii_masked",      "internal_only"),
            "remote_sensing": ("aggregated_safe", "open"),
            "surveillance":   ("restricted",      "restricted"),
        }
        self.assertEqual(sr.DEFAULT_SENSITIVITY, expected)

    def test_k_threshold(self):
        self.assertEqual(sr.K_THRESHOLD_AGGREGATED_SAFE, 10)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2：跑测试，确认 FAIL**

```bash
cd /Users/huanmeng/Downloads/Projects/imiss-deer-flow/skills/_shared
python3 -m unittest retrieval_protocol.tests.test_sensitivity_rules -v
```

Expected: `ImportError` / `ModuleNotFoundError: No module named ...sensitivity_rules`。

- [ ] **Step 3：创建 sensitivity_rules.py 的常量段**

创建 `skills/_shared/retrieval_protocol/sensitivity_rules.py`：

```python
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
```

- [ ] **Step 4：跑测试，确认 PASS**

```bash
cd /Users/huanmeng/Downloads/Projects/imiss-deer-flow/skills/_shared
python3 -m unittest retrieval_protocol.tests.test_sensitivity_rules -v
```

Expected: **2 个用例全 PASS**。

- [ ] **Step 5：commit**

```bash
cd /Users/huanmeng/Downloads/Projects/imiss-deer-flow
git add skills/_shared/retrieval_protocol/sensitivity_rules.py \
       skills/_shared/retrieval_protocol/tests/test_sensitivity_rules.py
git commit -m "feat(retrieval_protocol): sensitivity_rules.py 默认级别表"
```

---

## Task 2：sensitivity_rules.py —— 8 个判定基元

**Files:**
- Modify: `skills/_shared/retrieval_protocol/sensitivity_rules.py`
- Modify: `skills/_shared/retrieval_protocol/tests/test_sensitivity_rules.py`

判定基元只读 `evidence_unit` 字段，不修改输入。所有正则采用保守命中（宁可
误判敏感，不漏敏感）。

- [ ] **Step 1：写失败测试 —— 8 个基元**

在 `tests/test_sensitivity_rules.py` 文件**末尾**（`if __name__ == "__main__":`
**之前**）追加：

```python
class TestStructIdDetector(unittest.TestCase):
    def test_plain_phone(self):
        unit = {"text": "客户手机号是 13800138000，注意保密"}
        self.assertTrue(sr._has_struct_id(unit))

    def test_plain_id_card(self):
        unit = {"text": "证件号 110101199001011234"}
        self.assertTrue(sr._has_struct_id(unit))

    def test_plain_imei(self):
        unit = {"text": "imei: 356938035643809"}
        self.assertTrue(sr._has_struct_id(unit))

    def test_plain_email(self):
        unit = {"text": "联系 zhang.san@example.com"}
        self.assertTrue(sr._has_struct_id(unit))

    def test_plain_ipv4(self):
        unit = {"text": "源 IP 192.168.10.42"}
        self.assertTrue(sr._has_struct_id(unit))

    def test_precise_geo(self):
        unit = {"text": "采集点 39.908823,116.397470"}
        self.assertTrue(sr._has_struct_id(unit))

    def test_hashed_id_not_flagged(self):
        unit = {"text": "用户 a3f5c9d2 出现 12 次"}
        self.assertFalse(sr._has_struct_id(unit))


class TestAggregatedKDetector(unittest.TestCase):
    def test_unique_users_ge_k(self):
        unit = {"features": {"unique_users": 25}}
        self.assertTrue(sr._has_aggregated_k_ge(unit, 10))

    def test_unique_contacts_lt_k(self):
        unit = {"features": {"unique_contacts": 8}}
        self.assertFalse(sr._has_aggregated_k_ge(unit, 10))

    def test_no_k_signal(self):
        unit = {"features": {"call_count": 100}}  # call_count 不是主体数
        self.assertFalse(sr._has_aggregated_k_ge(unit, 10))


class TestSecretTokenDetector(unittest.TestCase):
    def test_api_key(self):
        unit = {"text": 'API_KEY="sk_live_8eF2..."'}
        self.assertTrue(sr._has_secret_token(unit))

    def test_password(self):
        unit = {"text": "password = 'admin123'"}
        self.assertTrue(sr._has_secret_token(unit))

    def test_db_connection(self):
        unit = {"text": "postgresql://user:pwd@10.0.0.1:5432/db"}
        self.assertTrue(sr._has_secret_token(unit))

    def test_normal_code(self):
        unit = {"text": "def add(a, b): return a + b"}
        self.assertFalse(sr._has_secret_token(unit))


class TestObjectTimeGeoCombo(unittest.TestCase):
    def test_combo_present(self):
        unit = {"features": {"target_id": "veh_A", "timestamp": "2026-05-27T08:00:00", "cell_id": "cell_42"}}
        self.assertTrue(sr._has_object_time_geo_combo(unit))

    def test_missing_geo(self):
        unit = {"features": {"target_id": "veh_A", "timestamp": "2026-05-27T08:00:00"}}
        self.assertFalse(sr._has_object_time_geo_combo(unit))


class TestRiskLabel(unittest.TestCase):
    def test_purefraud_flag(self):
        unit = {"features": {"purefraud_flag": True}}
        self.assertTrue(sr._has_risk_label(unit))

    def test_no_label(self):
        unit = {"features": {"call_count": 10}}
        self.assertFalse(sr._has_risk_label(unit))


class TestStreamingLink(unittest.TestCase):
    def test_stream_url(self):
        unit = {"features": {"stream_url": "rtsp://10.0.0.1/stream1"}}
        self.assertTrue(sr._has_streaming_link(unit))

    def test_channel_id(self):
        unit = {"features": {"channel_id": "cam_42"}}
        self.assertTrue(sr._has_streaming_link(unit))

    def test_no_link(self):
        unit = {"features": {"objects": ["person"]}}
        self.assertFalse(sr._has_streaming_link(unit))


class TestUnmaskedFacePlate(unittest.TestCase):
    def test_unmasked_face(self):
        unit = {"features": {"objects": [{"label": "face", "masked": False}]}}
        self.assertTrue(sr._has_unmasked_face_plate(unit))

    def test_masked_face(self):
        unit = {"features": {"objects": [{"label": "face", "masked": True}]}}
        self.assertFalse(sr._has_unmasked_face_plate(unit))

    def test_license_plate_default_unmasked(self):
        unit = {"features": {"objects": [{"label": "license_plate"}]}}  # 未显式 masked → 视为未打码
        self.assertTrue(sr._has_unmasked_face_plate(unit))


class TestMarkedPublic(unittest.TestCase):
    def test_explicit_public(self):
        unit = {"features": {"public": True}}
        self.assertTrue(sr._marked_public(unit))

    def test_source_kind_public(self):
        unit = {"features": {"source_kind": "public"}}
        self.assertTrue(sr._marked_public(unit))

    def test_not_public(self):
        unit = {"features": {"source_kind": "internal"}}
        self.assertFalse(sr._marked_public(unit))
```

- [ ] **Step 2：跑测试，确认 FAIL**

```bash
cd /Users/huanmeng/Downloads/Projects/imiss-deer-flow/skills/_shared
python3 -m unittest retrieval_protocol.tests.test_sensitivity_rules -v
```

Expected: 多个 `AttributeError: module ... has no attribute '_has_struct_id'`。

- [ ] **Step 3：实现 8 个基元**

在 `sensitivity_rules.py` 末尾追加：

```python
import re
from typing import Any

# 保守正则:命中即视为含明文结构化 ID。宁可误升档,不漏敏感。
_RE_PHONE   = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
_RE_ID_CARD = re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)")
_RE_IMEI    = re.compile(r"(?<!\d)\d{15}(?!\d)")
_RE_EMAIL   = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_RE_IPV4    = re.compile(r"(?<!\d)(?:\d{1,3}\.){3}\d{1,3}(?!\d)")
_RE_LATLON  = re.compile(r"(?<!\d)-?\d{1,3}\.\d{4,}\s*,\s*-?\d{1,3}\.\d{4,}(?!\d)")
_RE_MAC     = re.compile(r"(?<![\w:])[\dA-Fa-f]{2}(?::[\dA-Fa-f]{2}){5}(?![\w:])")

_STRUCT_ID_PATTERNS = (_RE_PHONE, _RE_ID_CARD, _RE_IMEI, _RE_EMAIL, _RE_IPV4, _RE_LATLON, _RE_MAC)

_RE_SECRET_KV = re.compile(
    r"(?i)(?:password|passwd|secret|api[_-]?key|access[_-]?token|"
    r"private[_-]?key|client[_-]?secret)\s*[:=]"
)
_RE_DB_URL = re.compile(r"(?i)(?:postgres(?:ql)?|mysql|mongodb|redis)://[^\s]+:[^\s]*@")

_K_SUBJECT_FIELDS = (
    "unique_users", "unique_contacts", "unique_devices",
    "unique_targets", "community_size", "sample_count",
)

_RISK_LABEL_FIELDS = (
    "risk_label", "purefraud_flag", "mutation_flag", "case_priority",
)

_STREAMING_FIELDS = ("stream_url", "playback_url", "channel_id", "camera_id")

_OBJECT_TIME_GEO_TRIPLE = (
    ("target_id", "object_id", "user_id_hash"),
    ("timestamp", "time_start", "captured_at", "ts"),
    ("cell_id", "station_id", "geohash", "bbox", "roaming_place"),
)


def _text(unit: dict[str, Any]) -> str:
    """安全取 text；缺失返回空串。"""
    value = unit.get("text")
    return value if isinstance(value, str) else ""


def _features(unit: dict[str, Any]) -> dict[str, Any]:
    """安全取 features；缺失返回空 dict。"""
    value = unit.get("features")
    return value if isinstance(value, dict) else {}


def _has_struct_id(unit: dict[str, Any]) -> bool:
    """text 中是否含明文结构化 ID(手机/身份证/IMEI/邮箱/IP/精确经纬度/MAC)。"""
    text = _text(unit)
    if not text:
        return False
    return any(p.search(text) for p in _STRUCT_ID_PATTERNS)


def _has_aggregated_k_ge(unit: dict[str, Any], k: int) -> bool:
    """features 是否含可表达 k 的主体数字段且 >= k。"""
    feats = _features(unit)
    for field in _K_SUBJECT_FIELDS:
        value = feats.get(field)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and value >= k:
            return True
    return False


def _has_secret_token(unit: dict[str, Any]) -> bool:
    """text 中是否含 password / token / api_key / secret / DB 连接串等。"""
    text = _text(unit)
    if not text:
        return False
    return bool(_RE_SECRET_KV.search(text) or _RE_DB_URL.search(text))


def _has_object_time_geo_combo(unit: dict[str, Any]) -> bool:
    """features 中是否同时给出对象 + 时间 + 位置三元组。"""
    feats = _features(unit)
    return all(any(field in feats for field in group) for group in _OBJECT_TIME_GEO_TRIPLE)


def _has_risk_label(unit: dict[str, Any]) -> bool:
    """features 中是否含对象级风险标签。"""
    feats = _features(unit)
    return any(field in feats for field in _RISK_LABEL_FIELDS)


def _has_streaming_link(unit: dict[str, Any]) -> bool:
    """features 中是否含视频接入链接 / 通道号 / camera_id。"""
    feats = _features(unit)
    return any(feats.get(field) for field in _STREAMING_FIELDS)


def _has_unmasked_face_plate(unit: dict[str, Any]) -> bool:
    """features.objects 中是否含未打码的人脸 / 车牌。

    objects[*] 形如 {"label": "face", "masked": True} 或纯字符串 "face"。
    未显式 ``masked=True`` 视为未打码(保守原则)。
    """
    objects = _features(unit).get("objects")
    if not isinstance(objects, list):
        return False
    targets = {"face", "license_plate"}
    for obj in objects:
        if isinstance(obj, dict):
            label = obj.get("label")
            masked = obj.get("masked")
            if label in targets and not masked:
                return True
        elif isinstance(obj, str) and obj in targets:
            return True
    return False


def _marked_public(unit: dict[str, Any]) -> bool:
    """features 中是否明确标 ``public=True`` 或 ``source_kind="public"``。"""
    feats = _features(unit)
    if feats.get("public") is True:
        return True
    return feats.get("source_kind") == "public"
```

- [ ] **Step 4：跑测试，确认 PASS**

```bash
cd /Users/huanmeng/Downloads/Projects/imiss-deer-flow/skills/_shared
python3 -m unittest retrieval_protocol.tests.test_sensitivity_rules -v
```

Expected: 含 Task 1 的 2 用例 + Task 2 的 25 用例（**≥ 27 PASS**）。

- [ ] **Step 5：commit**

```bash
cd /Users/huanmeng/Downloads/Projects/imiss-deer-flow
git add skills/_shared/retrieval_protocol/sensitivity_rules.py \
       skills/_shared/retrieval_protocol/tests/test_sensitivity_rules.py
git commit -m "feat(retrieval_protocol): sensitivity_rules.py 8 个判定基元"
```

---

## Task 3：classify_sensitivity 主入口（6 类分派）

**Files:**
- Modify: `skills/_shared/retrieval_protocol/sensitivity_rules.py`
- Modify: `skills/_shared/retrieval_protocol/tests/test_sensitivity_rules.py`

- [ ] **Step 1：写失败测试 —— 6 类默认 + 升 + 降 + 边界**

在 `tests/test_sensitivity_rules.py` 末尾追加：

```python
class TestClassifyGazetteer(unittest.TestCase):
    def test_default(self):
        unit = {"text": "2024 年全市道路总里程 X 公里", "features": {"unique_targets": 50}}
        self.assertEqual(sr.classify_sensitivity(data_type="gazetteer", evidence_unit=unit),
                         ("aggregated_safe", "open"))

    def test_small_sample_upgrade(self):
        unit = {"text": "样本社区 5 个的统计", "features": {"unique_targets": 5}}
        self.assertEqual(sr.classify_sensitivity(data_type="gazetteer", evidence_unit=unit),
                         ("restricted", "restricted"))

    def test_public_downgrade(self):
        unit = {"text": "公开年鉴第三章", "features": {"source_kind": "public", "unique_targets": 50}}
        self.assertEqual(sr.classify_sensitivity(data_type="gazetteer", evidence_unit=unit),
                         ("open", "open"))


class TestClassifyTelecom(unittest.TestCase):
    def test_default_with_hashed_id(self):
        unit = {"text": "user a3f5 在 community_42", "features": {"community_id": "42"}}
        self.assertEqual(sr.classify_sensitivity(data_type="telecom", evidence_unit=unit),
                         ("pii_masked", "internal_only"))

    def test_plain_phone_upgrade(self):
        unit = {"text": "号码 13800138000 通话", "features": {}}
        self.assertEqual(sr.classify_sensitivity(data_type="telecom", evidence_unit=unit),
                         ("restricted", "restricted"))

    def test_aggregated_safe_downgrade(self):
        unit = {"text": "区间通话量统计", "features": {"call_count": 1200, "unique_contacts": 25}}
        self.assertEqual(sr.classify_sensitivity(data_type="telecom", evidence_unit=unit),
                         ("aggregated_safe", "open"))

    def test_aggregated_k_below_threshold_keeps_default(self):
        # spec §3.4 边界：聚合但 k<10 不降级
        unit = {"text": "区间通话量统计", "features": {"call_count": 1200, "unique_contacts": 8}}
        self.assertEqual(sr.classify_sensitivity(data_type="telecom", evidence_unit=unit),
                         ("pii_masked", "internal_only"))

    def test_risk_label_upgrade(self):
        unit = {"text": "聚类社区 42", "features": {"community_id": "42", "purefraud_flag": True}}
        self.assertEqual(sr.classify_sensitivity(data_type="telecom", evidence_unit=unit),
                         ("restricted", "restricted"))


class TestClassifyCode(unittest.TestCase):
    def test_default(self):
        unit = {"text": "def add(a, b): return a + b", "features": {"lang": "python"}}
        self.assertEqual(sr.classify_sensitivity(data_type="code", evidence_unit=unit),
                         ("pii_masked", "internal_only"))

    def test_secret_upgrade(self):
        unit = {"text": 'API_KEY = "sk_live_xxxxx"', "features": {}}
        self.assertEqual(sr.classify_sensitivity(data_type="code", evidence_unit=unit),
                         ("restricted", "restricted"))

    def test_public_code_downgrade(self):
        unit = {"text": "def add(a, b): return a + b", "features": {"source_kind": "public"}}
        self.assertEqual(sr.classify_sensitivity(data_type="code", evidence_unit=unit),
                         ("open", "open"))

    def test_public_but_has_token_keeps_restricted(self):
        # spec §3.4 边界：保守原则,公开标记 + 含 token 仍升 restricted
        unit = {"text": 'token = "abc"', "features": {"source_kind": "public"}}
        self.assertEqual(sr.classify_sensitivity(data_type="code", evidence_unit=unit),
                         ("restricted", "restricted"))


class TestClassifyStreetview(unittest.TestCase):
    def test_default_masked(self):
        unit = {"features": {"objects": [{"label": "face", "masked": True}]}}
        self.assertEqual(sr.classify_sensitivity(data_type="streetview", evidence_unit=unit),
                         ("pii_masked", "internal_only"))

    def test_unmasked_face_upgrade(self):
        unit = {"features": {"objects": [{"label": "face", "masked": False}]}}
        self.assertEqual(sr.classify_sensitivity(data_type="streetview", evidence_unit=unit),
                         ("restricted", "restricted"))

    def test_count_only_downgrade(self):
        # spec §3.4 边界：仅目标计数 + 无可识别对象 + 无精确位置 → aggregated_safe+open
        unit = {"features": {"target_count": 30, "unique_targets": 30, "category": "tree"}}
        self.assertEqual(sr.classify_sensitivity(data_type="streetview", evidence_unit=unit),
                         ("aggregated_safe", "open"))

    def test_target_count_with_precise_geo_upgrade(self):
        # spec §3.4 边界：含精确位置即升 restricted
        unit = {"text": "采集点 39.908823,116.397470",
                "features": {"target_count": 30, "unique_targets": 30}}
        self.assertEqual(sr.classify_sensitivity(data_type="streetview", evidence_unit=unit),
                         ("restricted", "restricted"))


class TestClassifyRemoteSensing(unittest.TestCase):
    def test_default(self):
        unit = {"features": {"tile_id": "T50T", "change_score": 0.12}}
        self.assertEqual(sr.classify_sensitivity(data_type="remote_sensing", evidence_unit=unit),
                         ("aggregated_safe", "open"))

    def test_precise_geo_upgrade(self):
        unit = {"text": "点位 39.908823,116.397470 变化"}
        self.assertEqual(sr.classify_sensitivity(data_type="remote_sensing", evidence_unit=unit),
                         ("restricted", "restricted"))

    def test_public_downgrade(self):
        unit = {"features": {"tile_id": "T50T", "source_kind": "public"}}
        self.assertEqual(sr.classify_sensitivity(data_type="remote_sensing", evidence_unit=unit),
                         ("open", "open"))


class TestClassifySurveillance(unittest.TestCase):
    def test_default(self):
        unit = {"features": {"stream_url": "rtsp://10.0.0.1/cam"}}
        self.assertEqual(sr.classify_sensitivity(data_type="surveillance", evidence_unit=unit),
                         ("restricted", "restricted"))

    def test_masked_no_link_downgrade_pii(self):
        unit = {"features": {"objects": [{"label": "face", "masked": True}]}}
        self.assertEqual(sr.classify_sensitivity(data_type="surveillance", evidence_unit=unit),
                         ("pii_masked", "internal_only"))

    def test_aggregated_only_downgrade_safe(self):
        unit = {"features": {"target_count": 120, "unique_targets": 80}}
        self.assertEqual(sr.classify_sensitivity(data_type="surveillance", evidence_unit=unit),
                         ("aggregated_safe", "open"))


class TestClassifyErrors(unittest.TestCase):
    def test_unregistered_data_type_raises(self):
        with self.assertRaises(ValueError):
            sr.classify_sensitivity(data_type="not_a_type", evidence_unit={})

    def test_empty_unit_returns_default(self):
        self.assertEqual(sr.classify_sensitivity(data_type="telecom", evidence_unit={}),
                         ("pii_masked", "internal_only"))
```

- [ ] **Step 2：跑测试，确认 FAIL**

```bash
cd /Users/huanmeng/Downloads/Projects/imiss-deer-flow/skills/_shared
python3 -m unittest retrieval_protocol.tests.test_sensitivity_rules -v
```

Expected: `AttributeError: module ... has no attribute 'classify_sensitivity'`。

- [ ] **Step 3：实现 classify_sensitivity**

在 `sensitivity_rules.py` 末尾追加：

```python
_RESTRICTED = ("restricted", "restricted")
_PII = ("pii_masked", "internal_only")
_AGGREGATED_SAFE = ("aggregated_safe", "open")
_OPEN = ("open", "open")


def classify_sensitivity(
    *,
    data_type: str,
    evidence_unit: dict[str, Any],
    k_threshold: int = K_THRESHOLD_AGGREGATED_SAFE,
) -> tuple[str, str]:
    """按 data_type 与 evidence_unit 字段做保守敏感度预标。

    返回 ``(sensitivity_level, access_policy)``;未登记 data_type 抛 ``ValueError``。
    判定不确定时升一档(保守原则)。本函数只读 ``evidence_unit``,不修改入参。
    """
    if data_type not in DEFAULT_SENSITIVITY:
        raise ValueError(
            f"unknown data_type {data_type!r}; expected one of {sorted(DEFAULT_SENSITIVITY)}"
        )
    return _DISPATCH[data_type](evidence_unit, k_threshold)


def _classify_gazetteer(unit: dict[str, Any], k: int) -> tuple[str, str]:
    # 升级:小样本(k<10) / 含明文结构化 ID(可定位到具体对象或设施)
    if _has_struct_id(unit):
        return _RESTRICTED
    feats = _features(unit)
    if any(field in feats for field in _K_SUBJECT_FIELDS) and not _has_aggregated_k_ge(unit, k):
        return _RESTRICTED
    # 降级:已公开 且 无敏感信号
    if _marked_public(unit):
        return _OPEN
    return _AGGREGATED_SAFE


def _classify_telecom(unit: dict[str, Any], k: int) -> tuple[str, str]:
    # 升级:明文结构化 ID / 对象+时间+位置组合 / 对象级风险标签
    if _has_struct_id(unit) or _has_object_time_geo_combo(unit) or _has_risk_label(unit):
        return _RESTRICTED
    # 降级:聚合 + k>=10 + 不绑定单对象(_has_object_time_geo_combo 已在升级里挡掉)
    if _has_aggregated_k_ge(unit, k):
        return _AGGREGATED_SAFE
    return _PII


def _classify_code(unit: dict[str, Any], k: int) -> tuple[str, str]:
    # 升级:含密钥 / token / DB 连接串 / 内部 IP(后者由 struct_id IPv4 命中)
    if _has_secret_token(unit) or _has_struct_id(unit):
        return _RESTRICTED
    # 降级:已公开 且 无密钥
    if _marked_public(unit):
        return _OPEN
    return _PII


def _classify_streetview(unit: dict[str, Any], k: int) -> tuple[str, str]:
    # 升级:未打码人脸 / 车牌 / 精确位置(明文经纬度等)
    if _has_unmasked_face_plate(unit) or _has_struct_id(unit):
        return _RESTRICTED
    # 降级:仅目标计数 / 类别统计 + 无可识别对象 + 无精确位置 + k>=10
    feats = _features(unit)
    objects = feats.get("objects")
    only_counts = (
        ("target_count" in feats or "category" in feats)
        and (objects is None or objects == [])
    )
    if only_counts and _has_aggregated_k_ge(unit, k):
        return _AGGREGATED_SAFE
    return _PII


def _classify_remote_sensing(unit: dict[str, Any], k: int) -> tuple[str, str]:
    # 升级:精确坐标 / 内部标注 / 敏感设施点位(由 struct_id LATLON + sensitive_facility 字段)
    feats = _features(unit)
    if _has_struct_id(unit) or feats.get("sensitive_facility") or feats.get("internal_annotation"):
        return _RESTRICTED
    # 降级:已公开 且 无敏感信号
    if _marked_public(unit):
        return _OPEN
    return _AGGREGATED_SAFE


def _classify_surveillance(unit: dict[str, Any], k: int) -> tuple[str, str]:
    # 默认顶档,只允许两条降级路径
    feats = _features(unit)
    objects = feats.get("objects")
    has_streaming = _has_streaming_link(unit)
    has_unmasked = _has_unmasked_face_plate(unit)
    has_specific_location = _has_struct_id(unit) or feats.get("camera_location")

    # 降级 1:打码 + 无 streaming + 无具体点位 → pii_masked+internal_only
    if (
        isinstance(objects, list) and objects
        and not has_unmasked
        and not has_streaming
        and not has_specific_location
    ):
        return _PII

    # 降级 2:仅聚合统计(人数/车流量/目标数量) + k>=10 + 无 streaming / 未打码
    only_counts = (
        ("target_count" in feats or "people_count" in feats or "vehicle_count" in feats)
        and (objects is None or objects == [])
    )
    if only_counts and _has_aggregated_k_ge(unit, k) and not has_streaming and not has_unmasked:
        return _AGGREGATED_SAFE

    return _RESTRICTED


_DISPATCH = {
    "gazetteer":      _classify_gazetteer,
    "telecom":        _classify_telecom,
    "code":           _classify_code,
    "streetview":     _classify_streetview,
    "remote_sensing": _classify_remote_sensing,
    "surveillance":   _classify_surveillance,
}
```

- [ ] **Step 4：跑测试，确认 PASS**

```bash
cd /Users/huanmeng/Downloads/Projects/imiss-deer-flow/skills/_shared
python3 -m unittest retrieval_protocol.tests.test_sensitivity_rules -v
```

Expected: 全部 **≥ 50 用例** PASS（Task 1+2+3 累计）。

- [ ] **Step 5：commit**

```bash
cd /Users/huanmeng/Downloads/Projects/imiss-deer-flow
git add skills/_shared/retrieval_protocol/sensitivity_rules.py \
       skills/_shared/retrieval_protocol/tests/test_sensitivity_rules.py
git commit -m "feat(retrieval_protocol): classify_sensitivity 6 类分派"
```

---

## Task 4：6 类 adapter 调用 classify_sensitivity

**Files:**
- Modify: `skills/_shared/retrieval_protocol/adapters.py` (6 处函数)
- Modify: `skills/_shared/retrieval_protocol/tests/test_new_adapters.py`

模式：每个 adapter 在调用 `build_evidence_unit` **之前**先 `classify_sensitivity`，
把结果传进 `sensitivity_level` / `access_policy` 实参（覆盖现有硬编码）。

- [ ] **Step 1：在 adapters.py 顶部 import classify_sensitivity**

`adapters.py` 文件顶部既有 import 段后追加：

```python
from .sensitivity_rules import classify_sensitivity
```

- [ ] **Step 2：写失败测试 —— 6 类 adapter 集成断言**

修改 `skills/_shared/retrieval_protocol/tests/test_new_adapters.py`。

找到 `test_pii_defaults`（约 52 行）—— 这是 telecom 的旧硬编码断言，**改写**为：

```python
    def test_default_with_hashed_id(self):
        wrapper = adapt_telecom_hit({
            "doc_id": "tc1", "summary": "user a3f5 in community_42",
            "community_id": "42",
        })
        payload = wrapper["payload"]
        self.assertEqual(payload["meta"]["sensitivity_level"], "pii_masked")
        self.assertEqual(payload["meta"]["access_policy"], "internal_only")

    def test_upgrade_on_plain_phone(self):
        wrapper = adapt_telecom_hit({
            "doc_id": "tc2", "summary": "号码 13800138000 通话",
        })
        payload = wrapper["payload"]
        self.assertEqual(payload["meta"]["sensitivity_level"], "restricted")
        self.assertEqual(payload["meta"]["access_policy"], "restricted")

    def test_downgrade_on_aggregated_safe(self):
        wrapper = adapt_telecom_hit({
            "doc_id": "tc3", "summary": "区间通话量统计",
            "call_count": 1200, "unique_contacts": 25,
        })
        payload = wrapper["payload"]
        self.assertEqual(payload["meta"]["sensitivity_level"], "aggregated_safe")
        self.assertEqual(payload["meta"]["access_policy"], "open")
```

找到 `test_clip_and_pii_defaults`（约 136 行，surveillance 类）—— **改写**为：

```python
    def test_default_restricted(self):
        wrapper = adapt_surveillance_hit({
            "doc_id": "sv1", "summary": "frame summary",
            "stream_url": "rtsp://10.0.0.1/cam",
        })
        payload = wrapper["payload"]
        self.assertEqual(payload["meta"]["sensitivity_level"], "restricted")
        self.assertEqual(payload["meta"]["access_policy"], "restricted")

    def test_downgrade_when_masked_no_link(self):
        wrapper = adapt_surveillance_hit({
            "doc_id": "sv2", "summary": "blurred crowd",
            "objects": [{"label": "face", "masked": True}],
        })
        payload = wrapper["payload"]
        self.assertEqual(payload["meta"]["sensitivity_level"], "pii_masked")
        self.assertEqual(payload["meta"]["access_policy"], "internal_only")
```

在文件末尾、`if __name__ == "__main__":` 之前追加 4 类剩余 adapter 的集成断言：

```python
class TestRoadTrafficGazetteerSensitivity(unittest.TestCase):
    def test_default_aggregated_safe(self):
        from retrieval_protocol import adapt_road_traffic_hit
        wrapper = adapt_road_traffic_hit({
            "section_path": "第二章 道路概况", "pages": "12-13",
            "preview": "2024 年全市道路总里程 X 公里", "unique_targets": 50,
        })
        payload = wrapper["payload"]
        self.assertEqual(payload["meta"]["sensitivity_level"], "aggregated_safe")
        self.assertEqual(payload["meta"]["access_policy"], "open")

    def test_public_downgrade_to_open(self):
        from retrieval_protocol import adapt_road_traffic_hit
        wrapper = adapt_road_traffic_hit({
            "section_path": "公开年鉴", "pages": "1",
            "preview": "公开年鉴第三章", "source_kind": "public",
            "unique_targets": 50,
        })
        payload = wrapper["payload"]
        self.assertEqual(payload["meta"]["sensitivity_level"], "open")
        self.assertEqual(payload["meta"]["access_policy"], "open")


class TestCodeSensitivity(unittest.TestCase):
    def test_default_pii_masked(self):
        from retrieval_protocol import adapt_code_hit
        wrapper = adapt_code_hit({
            "doc_id": "c1", "snippet": "def add(a, b): return a + b",
            "lang": "python", "file_path": "/srv/repo/x.py",
            "line_start": 1, "line_end": 1,
        })
        payload = wrapper["payload"]
        self.assertEqual(payload["meta"]["sensitivity_level"], "pii_masked")
        self.assertEqual(payload["meta"]["access_policy"], "internal_only")

    def test_secret_upgrade(self):
        from retrieval_protocol import adapt_code_hit
        wrapper = adapt_code_hit({
            "doc_id": "c2", "snippet": 'API_KEY = "sk_live_xxxxx"',
            "lang": "python", "file_path": "/srv/repo/x.py",
        })
        payload = wrapper["payload"]
        self.assertEqual(payload["meta"]["sensitivity_level"], "restricted")
        self.assertEqual(payload["meta"]["access_policy"], "restricted")


class TestStreetviewSensitivity(unittest.TestCase):
    def test_unmasked_face_upgrade(self):
        from retrieval_protocol import adapt_streetview_hit
        wrapper = adapt_streetview_hit({
            "doc_id": "sv1", "summary": "frame",
            "objects": [{"label": "face", "masked": False}],
        })
        payload = wrapper["payload"]
        self.assertEqual(payload["meta"]["sensitivity_level"], "restricted")
        self.assertEqual(payload["meta"]["access_policy"], "restricted")

    def test_masked_default_pii(self):
        from retrieval_protocol import adapt_streetview_hit
        wrapper = adapt_streetview_hit({
            "doc_id": "sv2", "summary": "frame",
            "objects": [{"label": "face", "masked": True}],
        })
        payload = wrapper["payload"]
        self.assertEqual(payload["meta"]["sensitivity_level"], "pii_masked")
        self.assertEqual(payload["meta"]["access_policy"], "internal_only")


class TestRemoteSensingSensitivity(unittest.TestCase):
    def test_default_aggregated_safe(self):
        from retrieval_protocol import adapt_remote_sensing_hit
        wrapper = adapt_remote_sensing_hit({
            "doc_id": "r1", "summary": "tile change",
            "tile_id": "T50T", "change_score": 0.12,
        })
        payload = wrapper["payload"]
        self.assertEqual(payload["meta"]["sensitivity_level"], "aggregated_safe")
        self.assertEqual(payload["meta"]["access_policy"], "open")

    def test_precise_geo_upgrade(self):
        from retrieval_protocol import adapt_remote_sensing_hit
        wrapper = adapt_remote_sensing_hit({
            "doc_id": "r2",
            "summary": "点位 39.908823,116.397470 变化",
        })
        payload = wrapper["payload"]
        self.assertEqual(payload["meta"]["sensitivity_level"], "restricted")
        self.assertEqual(payload["meta"]["access_policy"], "restricted")
```

- [ ] **Step 3：跑测试，确认 FAIL**

```bash
cd /Users/huanmeng/Downloads/Projects/imiss-deer-flow/skills/_shared
python3 -m unittest retrieval_protocol.tests.test_new_adapters -v
```

Expected: 多个测试 FAIL（现有 adapter 仍是硬编码默认）。

- [ ] **Step 4：在 `adapt_road_traffic_hit` 中调用 classify**

`adapters.py` 中 `adapt_road_traffic_hit`（约 193–233 行），在 `payload = build_evidence_unit(...)` 之前插入分类，并把结果传入：

```python
def adapt_road_traffic_hit(
    hit: dict[str, Any],
    *,
    rank: int | None = None,
    source_id: str = "road_traffic_annual_report",
) -> dict[str, Any]:
    """task.md §6.3：road-traffic 年报 RAG ``rag_xian2024_min.py`` 命中映射。

    ``preview → text``、``section_path + pages → meta.locator``、
    ``distance / rerank_score → evidence wrapper.retrieval.raw_scores``、
    ``data_type = "gazetteer"``。

    spec 2026-05-27 §3：``sensitivity_level`` / ``access_policy`` 由
    :func:`classify_sensitivity` 按字段内容预标。
    """
    raw_scores: dict[str, Any] = {}
    if hit.get("distance") is not None:
        raw_scores["distance"] = hit["distance"]
    if hit.get("rerank_score") is not None:
        raw_scores["rerank_score"] = hit["rerank_score"]

    features = {
        key: hit[key]
        for key in (
            "section_path", "pages", "year", "region", "metric_name",
            "value", "unit", "source_kind", "public", "unique_targets",
        )
        if hit.get(key) is not None
    }
    classify_unit = {
        "text": _first_nonempty(hit.get("preview"), hit.get("text"), hit.get("section_path")),
        "features": features,
    }
    level, policy = classify_sensitivity(data_type="gazetteer", evidence_unit=classify_unit)

    payload = build_evidence_unit(
        evidence_id=_road_traffic_evidence_id(hit),
        data_type="gazetteer",
        text=_first_nonempty(hit.get("preview"), hit.get("text"), hit.get("section_path")),
        source_id=hit.get("source_id") or source_id,
        source_path=hit.get("source_path") or None,
        granularity="paragraph",
        locator=build_locator(section=hit.get("section_path"), page=hit.get("pages")),
        sensitivity_level=level,
        access_policy=policy,
        features=features,
    )
    return build_retrieval_evidence(
        evidence_ref=_road_traffic_evidence_id(hit),
        rank=rank,
        score=hit.get("rerank_score", hit.get("score")),
        method="vector_rerank",
        raw_scores=raw_scores or None,
        matched_fields=["preview"],
        payload=payload,
    )
```

- [ ] **Step 5：在 `adapt_telecom_hit` 中调用 classify**

`adapters.py` 中 `adapt_telecom_hit`（约 377–423 行）—— 把 `sensitivity_level` /
`access_policy` 改为 classify 结果：

```python
def adapt_telecom_hit(
    hit: dict[str, Any],
    *,
    rank: int | None = None,
    source_id: str = "telecom_cdr",
) -> dict[str, Any]:
    """telecom CDR 命中映射。预期字段:``doc_id`` / ``summary`` / ``call_count`` /
    ``unique_contacts`` / ``community_id`` / ``duration_sum``。

    spec 2026-05-27 §3:级别由 :func:`classify_sensitivity` 按字段内容预标。
    """
    feature_keys = (
        "call_count", "unique_contacts", "community_id", "duration_sum",
        "anomaly_flag", "purefraud_flag", "risk_label", "case_priority",
        "mutation_flag", "target_id", "object_id", "cell_id", "station_id",
        "roaming_place", "timestamp", "time_start", "source_kind", "public",
    )
    features = {key: hit[key] for key in feature_keys if hit.get(key) is not None}

    time_range = None
    if hit.get("time_start") and hit.get("time_end"):
        time_range = {
            "mode": "absolute",
            "start": hit["time_start"],
            "end": hit["time_end"],
            "timezone": hit.get("timezone") or "Asia/Shanghai",
        }

    text = _first_nonempty(hit.get("summary"), hit.get("text"), hit.get("title"))
    level, policy = classify_sensitivity(
        data_type="telecom",
        evidence_unit={"text": text, "features": features},
    )

    payload = build_evidence_unit(
        evidence_id=hit.get("doc_id") or hit.get("evidence_id") or "",
        data_type="telecom",
        text=text,
        source_id=hit.get("source_id") or source_id,
        source_path=hit.get("source_path") or None,
        time_range=time_range,
        geo_scope={},
        granularity=hit.get("granularity") or "user_window",
        sensitivity_level=level,
        access_policy=policy,
        features=features,
    )
    return build_retrieval_evidence(
        evidence_ref=hit.get("doc_id") or "",
        rank=rank,
        score=hit.get("score"),
        method="bm25_vector_rrf",
        rrf_k=60,
        matched_fields=["summary"],
        payload=payload,
    )
```

- [ ] **Step 6：在 `adapt_code_hit` 中调用 classify**

`adapters.py` 中 `adapt_code_hit`（约 435–490 行）—— 类似修改。把现有
`features` 字典扩为：

```python
    features = {
        key: hit[key]
        for key in (
            "doc_id", "snippet", "lang", "ast_node_type", "symbol",
            "repo", "source_kind", "public",
        )
        if hit.get(key) is not None
    }
```

然后在 `payload = build_evidence_unit(...)` 之前插入：

```python
    text = _first_nonempty(hit.get("snippet"), hit.get("text"), hit.get("summary"))
    level, policy = classify_sensitivity(
        data_type="code",
        evidence_unit={"text": text, "features": features},
    )
```

在 `build_evidence_unit(...)` 调用里：

- 把 `text=` 实参替换为 `text=text`（避免重复算 `_first_nonempty`）。
- 加 `sensitivity_level=level, access_policy=policy,` 两参数。
- 如已有硬编码 `sensitivity_level=...` / `access_policy=...` 则**删除**那两行。

- [ ] **Step 7：在 `adapt_streetview_hit` 中调用 classify**

`adapters.py` 中 `adapt_streetview_hit`（约 496–558 行）—— 把现有 `features`
字典扩为包含 `objects` / `target_count` / `category` / `source_kind` / `public`
等 classify 用到的字段。然后在 `payload = build_evidence_unit(...)` 之前插入：

```python
    level, policy = classify_sensitivity(
        data_type="streetview",
        evidence_unit={"text": text, "features": features},
    )
```

把 `build_evidence_unit(...)` 的 `sensitivity_level` / `access_policy` 实参
替换为 `level` / `policy`。

- [ ] **Step 8：在 `adapt_remote_sensing_hit` 中调用 classify**

`adapters.py` 中 `adapt_remote_sensing_hit`（约 563–620 行）—— 把现有 `features`
字典扩为包含 `tile_id` / `change_score` / `sensitive_facility` /
`internal_annotation` / `source_kind` / `public`。然后：

```python
    level, policy = classify_sensitivity(
        data_type="remote_sensing",
        evidence_unit={"text": text, "features": features},
    )
```

并把 `build_evidence_unit(...)` 的级别实参替换。

- [ ] **Step 9：在 `adapt_surveillance_hit` 中调用 classify**

`adapters.py` 中 `adapt_surveillance_hit`（约 626 行起）—— 把现有 `features`
字典扩为包含 `objects` / `stream_url` / `playback_url` / `channel_id` /
`camera_id` / `camera_location` / `target_count` / `people_count` /
`vehicle_count` / `unique_targets`。然后：

```python
    level, policy = classify_sensitivity(
        data_type="surveillance",
        evidence_unit={"text": text, "features": features},
    )
```

并把 `build_evidence_unit(...)` 的级别实参替换。

- [ ] **Step 10：跑测试，确认 PASS**

```bash
cd /Users/huanmeng/Downloads/Projects/imiss-deer-flow/skills/_shared
python3 -m unittest retrieval_protocol.tests.test_new_adapters -v
```

Expected: 全部用例 PASS（含新增的 ≥ 12 个集成断言）。

- [ ] **Step 11：跑全量回归**

```bash
cd /Users/huanmeng/Downloads/Projects/imiss-deer-flow/skills/_shared
python3 -m unittest discover -s retrieval_protocol/tests -t . -v
```

Expected: 含本任务之前所有用例全 PASS（**≥ 195 个**）。

- [ ] **Step 12：commit**

```bash
cd /Users/huanmeng/Downloads/Projects/imiss-deer-flow
git add skills/_shared/retrieval_protocol/adapters.py \
       skills/_shared/retrieval_protocol/tests/test_new_adapters.py
git commit -m "feat(retrieval_protocol): 6 类 adapter 调用 classify_sensitivity"
```

---

## Task 5：audit.py —— 枚举常量

**Files:**
- Create: `skills/_shared/retrieval_protocol/audit.py`
- Create: `skills/_shared/retrieval_protocol/tests/test_audit.py`

- [ ] **Step 1：写失败测试 —— 枚举常量**

创建 `skills/_shared/retrieval_protocol/tests/test_audit.py`：

```python
"""审计字段单测 —— spec 2026-05-27 §4."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from retrieval_protocol import audit


class TestAuditEnums(unittest.TestCase):
    def test_actions_set(self):
        expected = {
            "allow", "warn", "desensitize", "aggregate",
            "rewrite", "filter", "refuse", "manual_review",
        }
        self.assertEqual(audit.AUDIT_ACTIONS, frozenset(expected))

    def test_action_statuses(self):
        self.assertEqual(audit.AUDIT_ACTION_STATUSES, frozenset({"applied", "pending", "failed"}))

    def test_gates(self):
        self.assertEqual(audit.AUDIT_GATES, frozenset({"InputGate", "ContextGate", "OutputGate"}))

    def test_scenes(self):
        expected = {"self_use", "internal_org", "cross_org", "public_release", "research_anon"}
        self.assertEqual(audit.AUDIT_SCENES, frozenset(expected))

    def test_reason_codes_include_three_examples(self):
        # spec §4.2 例:struct_id_detected / geo_loc_with_object_time / re_identify_combo_risk
        self.assertIn("struct_id_detected", audit.AUDIT_REASON_CODES)
        self.assertIn("geo_loc_with_object_time", audit.AUDIT_REASON_CODES)
        self.assertIn("re_identify_combo_risk", audit.AUDIT_REASON_CODES)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2：跑测试，确认 FAIL**

```bash
cd /Users/huanmeng/Downloads/Projects/imiss-deer-flow/skills/_shared
python3 -m unittest retrieval_protocol.tests.test_audit -v
```

Expected: `ImportError: cannot import name 'audit' from 'retrieval_protocol'`。

- [ ] **Step 3：创建 audit.py 的枚举段**

创建 `skills/_shared/retrieval_protocol/audit.py`：

```python
"""审计动作 / 闸门 / 场景 / 原因码登记 + EvidenceAction 构造校验。

spec 2026-05-27 §4。本模块仅依赖 Python 标准库。

风险值脱敏护栏:``build_evidence_action`` / ``validate_evidence_action`` 拒绝任何
含原始敏感值的 ``risk_locations`` —— 审计日志不能成为二次泄露源。
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
```

- [ ] **Step 4：跑测试，确认 PASS**

```bash
cd /Users/huanmeng/Downloads/Projects/imiss-deer-flow/skills/_shared
python3 -m unittest retrieval_protocol.tests.test_audit -v
```

Expected: **5 个用例 PASS**。

- [ ] **Step 5：commit**

```bash
cd /Users/huanmeng/Downloads/Projects/imiss-deer-flow
git add skills/_shared/retrieval_protocol/audit.py \
       skills/_shared/retrieval_protocol/tests/test_audit.py
git commit -m "feat(retrieval_protocol): audit.py 枚举常量"
```

---

## Task 6：audit.py —— build_evidence_action + 风险值脱敏护栏

**Files:**
- Modify: `skills/_shared/retrieval_protocol/audit.py`
- Modify: `skills/_shared/retrieval_protocol/tests/test_audit.py`

- [ ] **Step 1：写失败测试**

在 `tests/test_audit.py` 末尾、`if __name__ == "__main__":` 之前追加：

```python
class TestBuildEvidenceAction(unittest.TestCase):
    def test_minimal_valid(self):
        action = audit.build_evidence_action(
            evidence_id="ev_1",
            action="desensitize",
            action_status="applied",
            triggered_violation_types=[],
            risk_locations=[{"field_path": "meta.subject", "risk_type": "phone"}],
            reason_code="struct_id_detected",
            sensitivity_before="pii_masked",
            sensitivity_after="restricted",
        )
        self.assertEqual(action["evidence_id"], "ev_1")
        self.assertEqual(action["action"], "desensitize")
        self.assertEqual(action["risk_locations"], [{"field_path": "meta.subject", "risk_type": "phone"}])

    def test_unknown_action_rejected(self):
        with self.assertRaises(ValueError):
            audit.build_evidence_action(
                evidence_id="ev_1", action="frobnicate", action_status="applied",
                triggered_violation_types=[], risk_locations=[],
                reason_code="struct_id_detected",
                sensitivity_before="pii_masked", sensitivity_after="restricted",
            )

    def test_unknown_status_rejected(self):
        with self.assertRaises(ValueError):
            audit.build_evidence_action(
                evidence_id="ev_1", action="allow", action_status="bogus",
                triggered_violation_types=[], risk_locations=[],
                reason_code="struct_id_detected",
                sensitivity_before="open", sensitivity_after="open",
            )

    def test_unknown_reason_code_rejected(self):
        with self.assertRaises(ValueError):
            audit.build_evidence_action(
                evidence_id="ev_1", action="allow", action_status="applied",
                triggered_violation_types=[], risk_locations=[],
                reason_code="not_a_code",
                sensitivity_before="open", sensitivity_after="open",
            )


class TestValidateEvidenceAction(unittest.TestCase):
    def test_extra_key_in_risk_location_rejected(self):
        # spec §4.3 护栏:risk_locations[*] 只允许 field_path + risk_type 两个键
        action = {
            "evidence_id": "ev_1", "action": "allow", "action_status": "applied",
            "triggered_violation_types": [],
            "risk_locations": [
                {"field_path": "meta.subject", "risk_type": "phone", "raw": "13800138000"},
            ],
            "reason_code": "struct_id_detected",
            "sensitivity_before": "pii_masked", "sensitivity_after": "restricted",
        }
        errors = audit.validate_evidence_action(action)
        self.assertTrue(errors, "validate_evidence_action 应该报错 risk_locations 含第三键")
        self.assertTrue(any("risk_locations" in e for e in errors))

    def test_long_string_rejected(self):
        action = {
            "evidence_id": "ev_1", "action": "allow", "action_status": "applied",
            "triggered_violation_types": [],
            "risk_locations": [{"field_path": "x" * 200, "risk_type": "phone"}],
            "reason_code": "struct_id_detected",
            "sensitivity_before": "open", "sensitivity_after": "open",
        }
        errors = audit.validate_evidence_action(action)
        self.assertTrue(errors)
        self.assertTrue(any("length" in e or "长度" in e for e in errors))

    def test_empty_evidence_id_rejected(self):
        action = {
            "evidence_id": "", "action": "allow", "action_status": "applied",
            "triggered_violation_types": [],
            "risk_locations": [{"field_path": "meta.x", "risk_type": "phone"}],
            "reason_code": "struct_id_detected",
            "sensitivity_before": "open", "sensitivity_after": "open",
        }
        errors = audit.validate_evidence_action(action)
        self.assertTrue(errors)
        self.assertTrue(any("evidence_id" in e for e in errors))

    def test_unknown_sensitivity_level_rejected(self):
        action = {
            "evidence_id": "ev_1", "action": "allow", "action_status": "applied",
            "triggered_violation_types": [],
            "risk_locations": [{"field_path": "meta.x", "risk_type": "phone"}],
            "reason_code": "struct_id_detected",
            "sensitivity_before": "weird", "sensitivity_after": "open",
        }
        errors = audit.validate_evidence_action(action)
        self.assertTrue(errors)

    def test_valid_returns_empty(self):
        action = {
            "evidence_id": "ev_1", "action": "allow", "action_status": "applied",
            "triggered_violation_types": [],
            "risk_locations": [{"field_path": "meta.x", "risk_type": "phone"}],
            "reason_code": "struct_id_detected",
            "sensitivity_before": "open", "sensitivity_after": "open",
        }
        self.assertEqual(audit.validate_evidence_action(action), [])
```

- [ ] **Step 2：跑测试，确认 FAIL**

```bash
cd /Users/huanmeng/Downloads/Projects/imiss-deer-flow/skills/_shared
python3 -m unittest retrieval_protocol.tests.test_audit -v
```

Expected: `AttributeError: module ... has no attribute 'build_evidence_action'`。

- [ ] **Step 3：实现 build_evidence_action + validate_evidence_action**

在 `audit.py` 末尾追加：

```python
# ---------------------------------------------------------------------------
# 构造器与校验器
# ---------------------------------------------------------------------------

_MAX_FIELD_LEN = 128
_RISK_LOCATION_KEYS = frozenset({"field_path", "risk_type"})

# 与 schema.SENSITIVITY_LEVELS 对齐(避免运行时 import 循环,显式列出)
_SENSITIVITY_LEVELS_AUDIT: frozenset[str] = frozenset({
    "open", "aggregated_safe", "pii_masked", "restricted",
})


def build_evidence_action(
    *,
    evidence_id: str,
    action: str,
    action_status: str,
    triggered_violation_types: list[str],
    risk_locations: list[dict[str, str]],
    reason_code: str,
    sensitivity_before: str,
    sensitivity_after: str,
) -> dict[str, Any]:
    """构造一条 ``EvidenceAction`` 记录。

    会立即调用 :func:`validate_evidence_action`,违规即抛 ``ValueError``。
    ``risk_locations[*]`` 严禁含 ``field_path`` / ``risk_type`` 之外的任何键。
    """
    record: dict[str, Any] = {
        "evidence_id": evidence_id,
        "action": action,
        "action_status": action_status,
        "triggered_violation_types": list(triggered_violation_types),
        "risk_locations": [dict(loc) for loc in risk_locations],
        "reason_code": reason_code,
        "sensitivity_before": sensitivity_before,
        "sensitivity_after": sensitivity_after,
    }
    errors = validate_evidence_action(record)
    if errors:
        raise ValueError("invalid EvidenceAction: " + "; ".join(errors))
    return record


def validate_evidence_action(record: dict[str, Any]) -> list[str]:
    """逐字段校验 EvidenceAction。返回错误信息列表,空列表 = 合规。"""
    errors: list[str] = []

    # evidence_id
    ev_id = record.get("evidence_id")
    if not isinstance(ev_id, str) or not ev_id:
        errors.append("evidence_id must be a non-empty string")
    elif len(ev_id) > _MAX_FIELD_LEN:
        errors.append(f"evidence_id length exceeds {_MAX_FIELD_LEN}")

    # action
    if record.get("action") not in AUDIT_ACTIONS:
        errors.append(f"action must be one of {sorted(AUDIT_ACTIONS)}")

    # action_status
    if record.get("action_status") not in AUDIT_ACTION_STATUSES:
        errors.append(f"action_status must be one of {sorted(AUDIT_ACTION_STATUSES)}")

    # triggered_violation_types
    tvt = record.get("triggered_violation_types")
    if not isinstance(tvt, list) or not all(isinstance(x, str) for x in tvt):
        errors.append("triggered_violation_types must be list[str]")

    # risk_locations 护栏
    risk_locs = record.get("risk_locations")
    if not isinstance(risk_locs, list):
        errors.append("risk_locations must be a list")
    else:
        for i, loc in enumerate(risk_locs):
            if not isinstance(loc, dict):
                errors.append(f"risk_locations[{i}] must be a dict")
                continue
            keys = set(loc.keys())
            if keys != _RISK_LOCATION_KEYS:
                errors.append(
                    f"risk_locations[{i}] keys must be exactly {{field_path, risk_type}}, got {sorted(keys)}"
                )
                continue
            for k in ("field_path", "risk_type"):
                v = loc.get(k)
                if not isinstance(v, str) or not v:
                    errors.append(f"risk_locations[{i}].{k} must be a non-empty string")
                elif len(v) > _MAX_FIELD_LEN:
                    errors.append(f"risk_locations[{i}].{k} length exceeds {_MAX_FIELD_LEN}")

    # reason_code
    if record.get("reason_code") not in AUDIT_REASON_CODES:
        errors.append(f"reason_code must be one of {sorted(AUDIT_REASON_CODES)}")

    # sensitivity_before/after
    for field in ("sensitivity_before", "sensitivity_after"):
        if record.get(field) not in _SENSITIVITY_LEVELS_AUDIT:
            errors.append(f"{field} must be one of {sorted(_SENSITIVITY_LEVELS_AUDIT)}")

    return errors
```

- [ ] **Step 4：跑测试，确认 PASS**

```bash
cd /Users/huanmeng/Downloads/Projects/imiss-deer-flow/skills/_shared
python3 -m unittest retrieval_protocol.tests.test_audit -v
```

Expected: 含 Task 5 + Task 6 累计 **≥ 13 个用例** PASS。

- [ ] **Step 5：commit**

```bash
cd /Users/huanmeng/Downloads/Projects/imiss-deer-flow
git add skills/_shared/retrieval_protocol/audit.py \
       skills/_shared/retrieval_protocol/tests/test_audit.py
git commit -m "feat(retrieval_protocol): build/validate_evidence_action + 脱敏护栏"
```

---

## Task 7：middleware.py —— `call` 扩展入参 + _emit_audit 字段补全

**Files:**
- Modify: `skills/_shared/retrieval_protocol/middleware.py`
- Modify: `skills/_shared/retrieval_protocol/tests/test_middleware.py`

- [ ] **Step 1：写失败测试 —— 扩展入参 + audit 字段补全**

在 `tests/test_middleware.py` 末尾、`if __name__ == "__main__":` 之前追加：

```python
class TestExtendedAuditFields(unittest.TestCase):
    def _envelope_with_data_type(self, data_type: str = "telecom") -> dict:
        # 构造一个最小合法 envelope,仅供 audit 字段抽取用
        return {
            "schema_version": "1.1",
            "request_id": "rid-1",
            "skill_name": "test-skill",
            "scenario": "test-scene",
            "capability": "evidence_search",
            "input": {
                "data_sources": [],
                "parameters": {"query": "q", "data_type": data_type, "top_k": 5, "mode": "auto"},
                "filters": {},
                "context": {},
            },
        }

    def test_call_accepts_new_kwargs_backward_compat(self):
        # 老调用 (无新 kwargs) 仍然能用
        records = []
        mw = middleware.RetrievalMiddleware(audit_sink=lambda r: records.append(r))
        env = self._envelope_with_data_type()
        result = {"status": "success", "result": {"evidence": []}}
        mw.call(env, retrieve_fn=lambda e: result)
        self.assertEqual(len(records), 1)

    def test_audit_record_has_gate_scene_data_type(self):
        records = []
        mw = middleware.RetrievalMiddleware(audit_sink=lambda r: records.append(r))
        env = self._envelope_with_data_type("telecom")
        result = {"status": "success", "result": {"evidence": []}}
        mw.call(
            env, retrieve_fn=lambda e: result,
            gate="InputGate", scene="self_use",
            policy_version="2026-05-27.1", detector_version="d-0.3.0",
        )
        rec = records[0]
        self.assertEqual(rec["gate"], "InputGate")
        self.assertEqual(rec["scene"], "self_use")
        self.assertEqual(rec["data_type"], "telecom")
        self.assertEqual(rec["policy_version"], "2026-05-27.1")
        self.assertEqual(rec["detector_version"], "d-0.3.0")

    def test_audit_record_carries_evidence_actions(self):
        from retrieval_protocol import build_evidence_action
        action = build_evidence_action(
            evidence_id="ev_1", action="filter", action_status="applied",
            triggered_violation_types=["V_PII_PHONE"],
            risk_locations=[{"field_path": "meta.subject", "risk_type": "phone"}],
            reason_code="struct_id_detected",
            sensitivity_before="pii_masked", sensitivity_after="restricted",
        )
        records = []
        mw = middleware.RetrievalMiddleware(audit_sink=lambda r: records.append(r))
        env = self._envelope_with_data_type("telecom")
        result = {"status": "success", "result": {"evidence": []}}
        mw.call(
            env, retrieve_fn=lambda e: result,
            gate="OutputGate", evidence_actions=[action],
        )
        self.assertEqual(records[0]["evidence_actions"], [action])

    def test_audit_record_omits_none_fields(self):
        records = []
        mw = middleware.RetrievalMiddleware(audit_sink=lambda r: records.append(r))
        env = self._envelope_with_data_type()
        result = {"status": "success", "result": {"evidence": []}}
        mw.call(env, retrieve_fn=lambda e: result)  # 不传新 kwargs
        rec = records[0]
        # 新字段缺省应为 None
        self.assertIsNone(rec.get("gate"))
        self.assertIsNone(rec.get("scene"))
        self.assertIsNone(rec.get("policy_version"))
        self.assertIsNone(rec.get("detector_version"))
        # data_type 仍应从 envelope 抽取
        self.assertEqual(rec["data_type"], "telecom")
        # evidence_actions 缺省空列表
        self.assertEqual(rec["evidence_actions"], [])


class TestJsonlSinkAsAuditSink(unittest.TestCase):
    def test_jsonl_audit_sink_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "audit.jsonl"
            sink = middleware.JsonlSink(path)
            mw = middleware.RetrievalMiddleware(audit_sink=sink.emit)
            env = {
                "schema_version": "1.1", "request_id": "rid", "skill_name": "s",
                "scenario": "sc", "capability": "evidence_search",
                "input": {"data_sources": [], "parameters": {"query": "q", "data_type": "telecom", "top_k": 1, "mode": "auto"}, "filters": {}, "context": {}},
            }
            mw.call(env, retrieve_fn=lambda e: {"status": "success", "result": {"evidence": []}},
                    gate="InputGate", scene="self_use")
            lines = path.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(lines), 1)
            row = json.loads(lines[0])
            self.assertEqual(row["gate"], "InputGate")
            self.assertEqual(row["data_type"], "telecom")
```

文件头部需加 `import json, tempfile` 与 `from pathlib import Path`（若尚未导入）。

- [ ] **Step 2：跑测试，确认 FAIL**

```bash
cd /Users/huanmeng/Downloads/Projects/imiss-deer-flow/skills/_shared
python3 -m unittest retrieval_protocol.tests.test_middleware -v
```

Expected: 新测试 FAIL（旧 `call` 不接受新 kwargs；audit record 没有新字段）。

- [ ] **Step 3：修改 `RetrievalMiddleware.call` 签名 + audit 写入**

打开 `skills/_shared/retrieval_protocol/middleware.py`。

把 `call` 方法（约 195 行起）整体替换为：

```python
    def call(
        self,
        envelope: dict[str, Any],
        *,
        retrieve_fn: RetrieveFn,
        user_id: str | None = None,
        gate: str | None = None,
        scene: str | None = None,
        policy_version: str | None = None,
        detector_version: str | None = None,
        evidence_actions: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """对 ``retrieve_fn(envelope)`` 包一层。

        ``user_id`` 仅用于审计,不参与缓存键计算。``gate`` / ``scene`` /
        ``policy_version`` / ``detector_version`` / ``evidence_actions`` 均为
        可选审计字段(spec 2026-05-27 §4),缺省不写入 audit record。
        """
        cache_key = compute_cache_key(envelope)
        started_at = time.time()
        cached = self._cache.get(cache_key)
        if cached is not None:
            self._emit_log(envelope, cache_key, cached, started_at, cache_hit=True)
            self._emit_audit(
                envelope, cached, user_id=user_id, cache_hit=True,
                gate=gate, scene=scene,
                policy_version=policy_version, detector_version=detector_version,
                evidence_actions=evidence_actions,
            )
            return cached

        result = retrieve_fn(envelope)
        status = result.get("status") if isinstance(result, dict) else None
        if status in ("success", "partial"):
            self._cache.put(cache_key, result)
        self._emit_log(envelope, cache_key, result, started_at, cache_hit=False)
        self._emit_audit(
            envelope, result, user_id=user_id, cache_hit=False,
            gate=gate, scene=scene,
            policy_version=policy_version, detector_version=detector_version,
            evidence_actions=evidence_actions,
        )
        return result
```

- [ ] **Step 4：扩展 `_emit_audit` 字段**

继续在 `middleware.py` 中，把 `_emit_audit` 整体替换为：

```python
    def _emit_audit(
        self,
        envelope: dict[str, Any],
        result: dict[str, Any],
        *,
        user_id: str | None,
        cache_hit: bool,
        gate: str | None = None,
        scene: str | None = None,
        policy_version: str | None = None,
        detector_version: str | None = None,
        evidence_actions: list[dict[str, Any]] | None = None,
    ) -> None:
        if self._audit is None:
            return
        evidence = (result.get("result", {}) or {}).get("evidence", []) if isinstance(result, dict) else []
        evidence_list = evidence if isinstance(evidence, list) else []
        sensitivity = summarize_sensitivity(evidence_list)
        sensitive_hits = sum(
            count for level, count in sensitivity.items() if level in _SENSITIVE_LEVELS
        )
        data_type = (
            ((envelope.get("input") or {}).get("parameters") or {}).get("data_type")
        )
        record = {
            "ts": int(time.time() * 1000),
            "request_id": envelope.get("request_id"),
            "user_id": user_id,
            "skill_name": envelope.get("skill_name"),
            "scenario": envelope.get("scenario"),
            "cache_hit": cache_hit,
            "sensitivity_distribution": sensitivity,
            "sensitive_hit_count": sensitive_hits,
            "filters": (envelope.get("input", {}) or {}).get("filters", {}),
            # spec 2026-05-27 §4 新增字段
            "gate": gate,
            "scene": scene,
            "data_type": data_type,
            "policy_version": policy_version,
            "detector_version": detector_version,
            "evidence_actions": list(evidence_actions) if evidence_actions else [],
        }
        try:
            self._audit(record)
        except Exception:
            pass
```

- [ ] **Step 5：跑测试，确认 PASS**

```bash
cd /Users/huanmeng/Downloads/Projects/imiss-deer-flow/skills/_shared
python3 -m unittest retrieval_protocol.tests.test_middleware -v
```

Expected: 含本任务 5 个新用例的全部 middleware 用例 PASS。

- [ ] **Step 6：commit**

```bash
cd /Users/huanmeng/Downloads/Projects/imiss-deer-flow
git add skills/_shared/retrieval_protocol/middleware.py \
       skills/_shared/retrieval_protocol/tests/test_middleware.py
git commit -m "feat(retrieval_protocol): middleware audit 字段补全 + 入参扩展"
```

---

## Task 8：__init__.py 公开新 API

**Files:**
- Modify: `skills/_shared/retrieval_protocol/__init__.py`

- [ ] **Step 1：写引入测试（用临时脚本验证）**

新建 `skills/_shared/retrieval_protocol/tests/test_public_api_new.py`：

```python
"""公共 API 引入测试 —— spec 2026-05-27 新增导出。"""
import unittest


class TestPublicApiNew(unittest.TestCase):
    def test_sensitivity_imports(self):
        from retrieval_protocol import classify_sensitivity, DEFAULT_SENSITIVITY, K_THRESHOLD_AGGREGATED_SAFE
        self.assertTrue(callable(classify_sensitivity))
        self.assertIn("telecom", DEFAULT_SENSITIVITY)
        self.assertEqual(K_THRESHOLD_AGGREGATED_SAFE, 10)

    def test_audit_imports(self):
        from retrieval_protocol import (
            AUDIT_ACTIONS, AUDIT_ACTION_STATUSES, AUDIT_GATES, AUDIT_SCENES,
            AUDIT_REASON_CODES, build_evidence_action, validate_evidence_action,
        )
        self.assertIn("filter", AUDIT_ACTIONS)
        self.assertIn("InputGate", AUDIT_GATES)
        self.assertTrue(callable(build_evidence_action))
        self.assertTrue(callable(validate_evidence_action))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2：跑测试，确认 FAIL**

```bash
cd /Users/huanmeng/Downloads/Projects/imiss-deer-flow/skills/_shared
python3 -m unittest retrieval_protocol.tests.test_public_api_new -v
```

Expected: `ImportError: cannot import name 'classify_sensitivity' from 'retrieval_protocol'`。

- [ ] **Step 3：扩展 `__init__.py` 的导出**

打开 `skills/_shared/retrieval_protocol/__init__.py`，在现有 `from .middleware import (...)` **之前**追加两行 import：

```python
from .sensitivity_rules import (
    DEFAULT_SENSITIVITY,
    K_THRESHOLD_AGGREGATED_SAFE,
    classify_sensitivity,
)
from .audit import (
    AUDIT_ACTIONS,
    AUDIT_ACTION_STATUSES,
    AUDIT_GATES,
    AUDIT_REASON_CODES,
    AUDIT_SCENES,
    build_evidence_action,
    validate_evidence_action,
)
```

在 `__all__` 列表内追加（按现有分块风格，在 `# middleware` 段之前插入两个新段）：

```python
    # sensitivity_rules —— spec 2026-05-27 §3
    "DEFAULT_SENSITIVITY",
    "K_THRESHOLD_AGGREGATED_SAFE",
    "classify_sensitivity",
    # audit —— spec 2026-05-27 §4
    "AUDIT_ACTIONS",
    "AUDIT_ACTION_STATUSES",
    "AUDIT_GATES",
    "AUDIT_REASON_CODES",
    "AUDIT_SCENES",
    "build_evidence_action",
    "validate_evidence_action",
```

- [ ] **Step 4：跑测试，确认 PASS**

```bash
cd /Users/huanmeng/Downloads/Projects/imiss-deer-flow/skills/_shared
python3 -m unittest retrieval_protocol.tests.test_public_api_new -v
```

Expected: **2 个用例 PASS**。

- [ ] **Step 5：commit**

```bash
cd /Users/huanmeng/Downloads/Projects/imiss-deer-flow
git add skills/_shared/retrieval_protocol/__init__.py \
       skills/_shared/retrieval_protocol/tests/test_public_api_new.py
git commit -m "feat(retrieval_protocol): 公开 sensitivity_rules / audit API"
```

---

## Task 9：README 更新

**Files:**
- Modify: `skills/_shared/retrieval_protocol/README.md`

- [ ] **Step 1：插入"敏感度落档"章节**

在 README.md 中现有"## v1.1 标准化错误码"章节**之前**插入：

````markdown
## 敏感度落档 + 6 类 adapter 预标（spec 2026-05-27 §3）

`adapt_road_traffic_hit` / `adapt_telecom_hit` / `adapt_code_hit` /
`adapt_streetview_hit` / `adapt_remote_sensing_hit` / `adapt_surveillance_hit`
在构造 `evidence_unit` 时调用 `classify_sensitivity`，按字段内容做**保守预标**。
预标只是初始档；最终是否过滤 / 脱敏 / 拒绝，仍由合规检测器统一决策。

```python
from retrieval_protocol import classify_sensitivity, DEFAULT_SENSITIVITY

level, policy = classify_sensitivity(
    data_type="telecom",
    evidence_unit={
        "text": "号码 13800138000 通话",
        "features": {},
    },
)
# ("restricted", "restricted") —— 明文手机号触发升档
```

四档语义见 `schema.py` 中 `SENSITIVITY_LEVELS` 注释；6 类默认级别表见
`sensitivity_rules.py` 的 `DEFAULT_SENSITIVITY`。**不动**的 4 类
(`spatiotemporal_trajectory` / `netflow` / `policy` / `traffic_flow`) 保留
现有 adapter 硬编码默认。
````

- [ ] **Step 2：插入"审计字段"章节**

在上一章节之后、"v1.1 标准化错误码"之前插入：

````markdown
## 审计字段扩展（spec 2026-05-27 §4）

`RetrievalMiddleware.call` 新增可选入参，自动注入到 audit record：

```python
from retrieval_protocol import (
    RetrievalMiddleware, JsonlSink,
    build_evidence_action,
)

action = build_evidence_action(
    evidence_id="ev_1", action="filter", action_status="applied",
    triggered_violation_types=["V_PII_PHONE"],
    risk_locations=[{"field_path": "meta.subject", "risk_type": "phone"}],
    reason_code="struct_id_detected",
    sensitivity_before="pii_masked", sensitivity_after="restricted",
)

mw = RetrievalMiddleware(
    audit_sink=JsonlSink("logs/retrieval.audit.jsonl").emit,
)
mw.call(
    envelope,
    retrieve_fn=my_rag_search,
    user_id="zhangsan",
    gate="OutputGate",          # InputGate / ContextGate / OutputGate
    scene="internal_org",       # self_use / internal_org / cross_org / public_release / research_anon
    policy_version="2026-05-27.1",
    detector_version="d-0.3.0",
    evidence_actions=[action],
)
```

audit record 字段：

| 字段 | 类型 | 备注 |
|---|---|---|
| `gate` / `scene` | str/None | 闸门 + 场景 |
| `data_type` | str/None | 从 envelope.input.parameters.data_type 自动抽 |
| `policy_version` / `detector_version` | str/None | 处置矩阵 / 检测器版本 |
| `evidence_actions[]` | list | 每条含 evidence_id / action / action_status / triggered_violation_types / risk_locations / reason_code / sensitivity_before / sensitivity_after |

**风险值脱敏护栏**：`build_evidence_action` 拒绝 `risk_locations[*]` 中除
`field_path` + `risk_type` 之外的任何键、长度 > 128 字符的字符串、空
`evidence_id` —— 审计日志不能成为二次泄露源。

默认 audit sink 复用 `JsonlSink`（已有日志 sink）。ES 后端只需提供
`Callable[[dict], None]` 接口写 bulk 即可。
````

- [ ] **Step 3：commit**

```bash
cd /Users/huanmeng/Downloads/Projects/imiss-deer-flow
git add skills/_shared/retrieval_protocol/README.md
git commit -m "docs(retrieval_protocol): README 增敏感度落档 + 审计字段章节"
```

---

## Task 10：全量验证

**Files:** 无修改，仅运行测试。

- [ ] **Step 1：跑全量测试矩阵**

```bash
cd /Users/huanmeng/Downloads/Projects/imiss-deer-flow/skills/_shared
python3 -m unittest discover -s retrieval_protocol/tests -t . -v 2>&1 | tail -20
```

Expected：

- 最后一行 `OK`
- 数量 **≥ 219**（v1.1 既有 182 + 本次新增 ≥ 37）

- [ ] **Step 2：分类跑一遍确认每个子模块测试通过**

```bash
cd /Users/huanmeng/Downloads/Projects/imiss-deer-flow/skills/_shared
for mod in test_schema test_envelope test_evidence test_errors test_validate \
           test_adapters test_new_adapters test_middleware test_budget \
           test_rag_search_integration test_sensitivity_rules test_audit \
           test_public_api_new ; do
    echo "=== $mod ==="
    python3 -m unittest retrieval_protocol.tests.$mod -v 2>&1 | tail -3
done
```

Expected：每段末尾都是 `OK`。

- [ ] **Step 3：确认无遗留改动**

```bash
cd /Users/huanmeng/Downloads/Projects/imiss-deer-flow
git status --short
```

Expected：`docs/new_tasks/` / `SYNC_*.md` / `docs/数据*.md` 等既存未跟踪文件以外，
`skills/_shared/retrieval_protocol/` 下应**无未提交修改**。

- [ ] **Step 4：补一份完成笔记到 plan 文档底部**

在 `docs/superpowers/plans/2026-05-27-sensitivity-rules-and-audit.md` 末尾追加：

```markdown
---

## 完成记录

- **完成日期**：<填入>
- **完整测试数**：<填入,例 220>
- **commit 列表**：

  | commit | task |
  |---|---|
  | `<short hash>` | Task 0 schema 注释 |
  | `<short hash>` | Task 1 默认表 |
  | `<short hash>` | Task 2 判定基元 |
  | `<short hash>` | Task 3 classify_sensitivity |
  | `<short hash>` | Task 4 6 类 adapter 改造 |
  | `<short hash>` | Task 5 audit 枚举 |
  | `<short hash>` | Task 6 build/validate_evidence_action |
  | `<short hash>` | Task 7 middleware audit 字段 |
  | `<short hash>` | Task 8 公开 API |
  | `<short hash>` | Task 9 README |

- **未 push**（按规范 3 等师兄确认）
```

- [ ] **Step 5：commit 完成记录**

```bash
cd /Users/huanmeng/Downloads/Projects/imiss-deer-flow
git add docs/superpowers/plans/2026-05-27-sensitivity-rules-and-audit.md
git commit -m "docs(plan): 标记 sensitivity-rules-and-audit 完成"
```

---

## 推后内容（不在本分支）

下分支 `feat/retrieval-planner-and-aggregator` 落地（spec §5）：

- `planner.py` —— `RetrievalTask` / `Plan` / `split_budget` / `build_plan`
- `aggregator.py` —— `AggregatorHooks` + 默认 dedup/sort/clip + `E_OUT_OF_BUDGET` 联动
- `agents/middlewares/planner_middleware.py` —— LangGraph 接入
- `agents/middlewares/aggregator_middleware.py` —— LangGraph 接入

那一轮要动 `backend/packages/harness/deerflow/agents/`，与本次的"协议层 +
adapter 内部 + audit 字段"完全隔离。

---

## 完成记录

- **完成日期**：2026-05-27
- **完整测试数**：272
- **commit 列表**（按时间顺序，从 5a23d34 之后）：

  | commit | 说明 |
  |---|---|
  | d04a0d2 | Task 0：锁四档敏感度语义到 schema.py 注释 |
  | e30535c | Task 1：sensitivity_rules.py 默认级别表 |
  | 182c895 | Task 2：sensitivity_rules.py 8 个判定基元 |
  | 033508f | Task 3：classify_sensitivity 6 类分派 |
  | 6fc8872 | Task 4：加 _DISPATCH 与 DEFAULT_SENSITIVITY 同步断言 |
  | 71aa6bc | Task 4：6 类 adapter 调用 classify_sensitivity |
  | d5f69ab | Task 4 review：修复 (text 复用 + docstring + _assert_valid) |
  | 569887d | Task 5：audit.py 枚举常量 |
  | 6c8639f | Task 6：audit.py docstring 移除 Task 6 超前引用 |
  | dc72e55 | Task 6：build/validate_evidence_action + 脱敏护栏 |
  | b9ba611 | Task 7：middleware audit 字段补全 + 入参扩展 |
  | 12c8f5d | Task 8 refactor：audit 直接 import schema.SENSITIVITY_LEVELS |
  | d6f59a4 | Task 8：公开 sensitivity_rules / audit API |
  | 24c0cdc | Task 9：README 增敏感度落档 + 审计字段章节 |
  | b3180a4 | Task 10：README 增敏感度落档 + 审计字段章节（末尾补充） |

- **子模块全 OK**：
  - test_schema ✓
  - test_envelope ✓
  - test_evidence ✓
  - test_errors ✓
  - test_validate ✓
  - test_adapters ✓
  - test_new_adapters ✓
  - test_middleware ✓
  - test_budget ✓
  - test_rag_search_integration ✓
  - test_sensitivity_rules ✓
  - test_audit ✓
  - test_public_api_new ✓

- **未 push**（按规范 3 等师兄确认）
