# Adapter 重塑（按 5/29 补充回复）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 按 `docs/new_tasks/补充回复.md` 中 5 个数据类型负责人的反馈，对齐 retrieval_protocol 6 类 adapter 的 features schema 与敏感度判定细则，使其与真实数据形态一致。

**Architecture:** 仅改 `adapters.py` 中 4 个 adapter（telecom / streetview / surveillance / remote_sensing）与 `sensitivity_rules.py` 中 `_classify_telecom` 的字段名集合；不改 `__init__.py` 公开 API；不改 schema.py 四档语义；不改 audit。code adapter 仅文档说明本期不参与 retrieval（功能侧无变更）。statistics_yearbook 无对应 adapter，本期不进入计划。**严格 TDD：每个 task 先写测试 → 跑失败 → 实现 → 跑通过 → commit。** 不破坏现有 272 个 pass 测试基线。

**Tech Stack:** Python 3.11+, stdlib only, unittest, uv runner.

---

## 输入与范围

### 补充回复.md 关键约束

| 数据类型 | 反馈要点 | 本计划处置 |
|---|---|---|
| telecom_network | features 不固定 schema；4 类 evidence（用户节点 / 通话边 / 设备关系 / 聚合统计）；明文兜底升档；哈希 ID + 时间 + 基站组合按 restricted | Task 1-2 |
| streetview | 实际字段是 `metadata.address.*` + `latitude/longitude`；无 bbox / 无人脸号牌遮挡 | Task 3-4 |
| video_surveillance | 实际字段是 `video_id / camera_id / filename / raw_segment_uri / started_at / ended_at / labels / object_summary / location / metadata`；无逐帧 bbox；人脸/车牌打码理论可做未测试 | Task 5 |
| remote_sensing | 实际字段是 `id / title / content / similarity / rank / url / hash / resolution / exif`；合规仅精确地理位置 | Task 6 |
| code_snippet | 本期仅敏感词分析，不参与 retrieval | Task 7（文档） |
| statistics_yearbook | skill 表格处理不自带数据源、不参与 retrieval | 不在本计划范围 |

### 不动的部分

- 公开 API（`__init__.py` 现有导出列表）保持不变
- schema.py 四档敏感度语义注释不变
- audit.py 枚举与护栏不变
- middleware.call 入参不变
- 既有 4 个 adapter（citybench / network_traffic / road_traffic / policy）不变
- traffic_flow adapter 不变（补充回复未涉及）

---

## File Structure

**会改的文件**：
- `skills/_shared/retrieval_protocol/adapters.py`：4 处函数体改动
  - `adapt_telecom_hit`：features 改为「灵活字典 + 保留字段保护」
  - `adapt_streetview_hit`：features 从 `metadata.address.*` 展平 + 取 `metadata.latitude/longitude` 进 geo_scope
  - `adapt_surveillance_hit`：features 增加 `video_id/camera_id/filename/raw_segment_uri/started_at/ended_at/labels/object_summary/location/metadata`；time_range 优先 `started_at/ended_at`
  - `adapt_remote_sensing_hit`：features 增加 `id/title/content/similarity/url/hash/resolution/exif`；evidence_id 优先 `id`，text 拼 `title + content`
- `skills/_shared/retrieval_protocol/sensitivity_rules.py`：1 处常量改动
  - `_OBJECT_TIME_GEO_TRIPLE` 增加 telecom 实际字段名：`src_user_id` / `dst_counterparty_id` / `event_time` / `event_date` / `event_hour` / `station` / `cell` / `roaming_place`
- `skills/_shared/retrieval_protocol/tests/test_new_adapters.py`：新增 8-10 个 test case 覆盖新字段映射
- `skills/_shared/retrieval_protocol/README.md`：更新 6 类 adapter 字段映射章节（追加 5/29 反馈对齐说明）
- `skills/custom/code-snippet-analysis/SKILL.md` 或同级 README：说明「本期仅敏感词分析，不参与 retrieval」（如存在）；不存在则在 retrieval_protocol/README.md 补充说明

**不动**：
- `__init__.py`、`schema.py`、`audit.py`、`envelope.py`、`evidence.py`、`errors.py`、`middleware.py`、`validate.py`

---

## Task 0：写本计划完成跟踪 + 锁定范围

**Files:**
- Modify: `docs/superpowers/plans/2026-05-29-adapter-rebuild-after-feedback.md`（本文件，task 完成时勾选 checkbox）

- [ ] **Step 1: 用 git status 确认工作区干净（除已知 untracked 文档外）**

Run: `git status --short`
Expected: 仅显示之前已存在的 untracked 文件（SYNC_*.md / 数据对接*.md / 补充回复.md 等），无新增 modified

- [x] **Step 2: 用 stdlib unittest 跑全量测试确认 272 基线**

Run: `python3 -m unittest discover -s skills/_shared/retrieval_protocol/tests -t skills/_shared/retrieval_protocol`
Expected: `Ran 272 tests in N.NNNs / OK`，0 failures

**注**：本项目尚未配置 pyproject.toml + uv 环境（无 .venv），retrieval_protocol 仅依赖 stdlib，测试用 stdlib unittest 跑。所有后续 task 中 `uv run python -m pytest ...` 命令统一替换为 `python3 -m unittest discover -s skills/_shared/retrieval_protocol/tests -t skills/_shared/retrieval_protocol -p "test_*.py" -v` 或针对单个 test class 用 `python3 -m unittest skills._shared.retrieval_protocol.tests.test_new_adapters.TestTelecom -v`（需在仓根运行）。

- [x] **Step 3: 基线确认**

**基线测试数：272 passed**（2026-05-29 09:50 在 main+本分支 03dbf92 上实测）

无 commit。本步骤仅作起点确认。

---

## Task 1：telecom adapter — features 灵活字典 + 4 类 evidence 字段映射

**Files:**
- Modify: `skills/_shared/retrieval_protocol/adapters.py`（`adapt_telecom_hit` 函数体）
- Test: `skills/_shared/retrieval_protocol/tests/test_new_adapters.py`（新增测试方法）

**实现策略**：
- 不再写死 `feature_keys` 白名单，而是改为「**拷贝 hit 全部字段到 features**，剔除 evidence wrapper 顶层保留字段 + 已用于 time_range/source/score 的字段」
- 保留字段集合：`{"doc_id", "evidence_id", "summary", "text", "title", "score", "source_id", "source_path", "granularity", "time_start", "time_end", "timezone"}`
- 这样 4 类 evidence（用户节点 / 通话边 / 设备关系 / 聚合统计）都能落进 features，不强求字段集

- [ ] **Step 1: 写失败测试 —— 用户节点类 evidence 透传全部字段**

在 `tests/test_new_adapters.py` 的 `TestTelecom` 类追加：

```python
def test_user_node_features_passthrough(self):
    """用户节点 evidence: 14 个字段全部透传到 features。"""
    hit = {
        "doc_id": "tc-un-1",
        "summary": "user node passthrough",
        "province": "江苏",
        "dataset_name": "ds1",
        "user_id": "u_hash_a3f5",
        "label": "normal",
        "sub_label": "purefraud",
        "age": 35,
        "open_card_time": "2024-01-01",
        "access_mode": "4G",
        "monthly_fee": 88.0,
        "monthly_flow_mb": 12000,
        "monthly_call_duration": 380,
        "caller_ratio_3m": 0.62,
        "caller_dispersion_3m": 0.41,
        "cross_province_ratio_3m": 0.08,
        "broadband_flag": True,
        "source_table": "user_nodes",
        "score": 0.9,
    }
    wrapper = adapters.adapt_telecom_hit(hit, rank=1)
    _assert_valid(self, wrapper)
    feats = wrapper["payload"]["meta"]["features"]
    for key in ("province", "dataset_name", "user_id", "label", "sub_label",
                "age", "open_card_time", "access_mode", "monthly_fee",
                "monthly_flow_mb", "monthly_call_duration", "caller_ratio_3m",
                "caller_dispersion_3m", "cross_province_ratio_3m",
                "broadband_flag", "source_table"):
        self.assertIn(key, feats, msg=f"missing {key}")
    # 评分类 / wrapper 顶层字段不应落进 features
    self.assertNotIn("score", feats)
    self.assertNotIn("doc_id", feats)
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `uv run python -m pytest skills/_shared/retrieval_protocol/tests/test_new_adapters.py::TestTelecom::test_user_node_features_passthrough -v`
Expected: FAIL，原因是 features 缺 `province / dataset_name / user_id / age / open_card_time / ...` 等

- [ ] **Step 3: 修改 adapt_telecom_hit 实现灵活字典**

在 `adapters.py` 中替换 `adapt_telecom_hit` 函数中 features 构造逻辑：

```python
def adapt_telecom_hit(
    hit: dict[str, Any],
    *,
    rank: int | None = None,
    source_id: str = "telecom_cdr",
) -> dict[str, Any]:
    """telecom 命中映射。features 采用「灵活字典 + 保留字段保护」策略,
    兼容 4 类 evidence(用户节点 / 通话边 / 设备关系 / 聚合统计)。

    保留字段(不进 features): doc_id / evidence_id / summary / text / title /
    score / source_id / source_path / granularity / time_start / time_end /
    timezone。其余字段一律透传进 features,由 :func:`classify_sensitivity`
    按字段内容预标级别。

    spec 2026-05-27 §3 + 补充回复 5/29: 级别由 classify_sensitivity 按字段
    内容预标(明文 ID 升 restricted; 哈希 user_id + event_time + station/cell
    组合升 restricted; 聚合统计 k>=10 降 aggregated_safe)。
    """
    _WRAPPER_RESERVED = {
        "doc_id", "evidence_id", "summary", "text", "title", "score",
        "source_id", "source_path", "granularity",
        "time_start", "time_end", "timezone",
    }
    features = {k: v for k, v in hit.items() if k not in _WRAPPER_RESERVED and v is not None}

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

把 `_WRAPPER_RESERVED` 放到函数体内常量（不外溢到模块层），避免影响其他 adapter。

- [ ] **Step 4: 运行测试，确认通过**

Run: `uv run python -m pytest skills/_shared/retrieval_protocol/tests/test_new_adapters.py::TestTelecom -v`
Expected: 全部 PASS（包含原有的 `test_default_with_hashed_id` / `test_upgrade_on_plain_phone` / `test_downgrade_on_aggregated_safe` / `test_geo_scope_is_object` 与新增 `test_user_node_features_passthrough`）

- [ ] **Step 5: 跑全量回归确认无破坏**

Run: `uv run python -m pytest skills/_shared/retrieval_protocol/tests/ -q`
Expected: 全 PASS（基线 + 1 新测试）

- [ ] **Step 6: 写新增测试 —— 通话边类 evidence 字段透传**

在 `TestTelecom` 类追加：

```python
def test_call_edge_features_passthrough(self):
    """通话边 evidence: 15 个字段全部透传 + time_range 取 event_time 时不被吞。"""
    hit = {
        "doc_id": "tc-ce-1",
        "summary": "call edge",
        "province": "江苏",
        "dataset_name": "ds1",
        "src_user_id": "u_hash_src",
        "dst_counterparty_id": "u_hash_dst",
        "event_time": "2024-03-01T10:00:00+08:00",
        "event_date": "2024-03-01",
        "event_hour": 10,
        "duration": 65,
        "call_type": "voice",
        "imei": "imei_hash_xyz",
        "city": "南京",
        "county": "玄武",
        "station": "station_hash_42",
        "cell": "cell_hash_7",
        "roaming_place": "place_hash_abc",
        "counterparty_belong": "中国移动",
        "source_table": "call_edges",
        "score": 0.8,
    }
    wrapper = adapters.adapt_telecom_hit(hit, rank=2)
    _assert_valid(self, wrapper)
    feats = wrapper["payload"]["meta"]["features"]
    for key in ("src_user_id", "dst_counterparty_id", "event_time",
                "event_date", "event_hour", "duration", "call_type", "imei",
                "city", "county", "station", "cell", "roaming_place",
                "counterparty_belong", "source_table"):
        self.assertIn(key, feats, msg=f"missing {key}")
```

- [ ] **Step 7: 运行测试，确认通过**

Run: `uv run python -m pytest skills/_shared/retrieval_protocol/tests/test_new_adapters.py::TestTelecom::test_call_edge_features_passthrough -v`
Expected: PASS

- [ ] **Step 8: 写新增测试 —— 设备关系类 + 聚合统计类 evidence**

在 `TestTelecom` 类追加：

```python
def test_edge_relation_features_passthrough(self):
    """设备关系 evidence: src_id / dst_id / edge_type / edge_count 等透传。"""
    hit = {
        "doc_id": "tc-er-1",
        "summary": "phone-imei edge",
        "src_id": "ph_42", "dst_id": "imei_88",
        "src_type": "phone", "dst_type": "imei",
        "edge_type": "uses_imei",
        "dataset": "edges_phone_imei",
        "user_id": "u_hash_a", "imei": "imei_hash_b",
        "edge_count": 14,
        "score": 0.7,
    }
    wrapper = adapters.adapt_telecom_hit(hit)
    _assert_valid(self, wrapper)
    feats = wrapper["payload"]["meta"]["features"]
    for key in ("src_id", "dst_id", "src_type", "dst_type", "edge_type",
                "dataset", "edge_count"):
        self.assertIn(key, feats, msg=f"missing {key}")

def test_aggregated_stat_features_passthrough(self):
    """聚合统计 evidence: relation_strength / risk_user_count / source_refs 等透传。"""
    hit = {
        "doc_id": "tc-agg-1",
        "summary": "community stats",
        "community_id": "comm_42",
        "relation_strength": 0.82,
        "risk_user_count": 3,
        "label_count": {"normal": 120, "risk": 3},
        "cross_province_ratio": 0.14,
        "caller_dispersion": 0.6,
        "source_table": "community_stats",
        "source_refs": ["call_edges#W12", "user_nodes#prov-江苏"],
        "score": 0.6,
    }
    wrapper = adapters.adapt_telecom_hit(hit)
    _assert_valid(self, wrapper)
    feats = wrapper["payload"]["meta"]["features"]
    for key in ("community_id", "relation_strength", "risk_user_count",
                "label_count", "cross_province_ratio", "caller_dispersion",
                "source_table", "source_refs"):
        self.assertIn(key, feats, msg=f"missing {key}")
```

- [ ] **Step 9: 运行测试，确认通过**

Run: `uv run python -m pytest skills/_shared/retrieval_protocol/tests/test_new_adapters.py::TestTelecom -v`
Expected: 全部 PASS（包括 4 个新增 + 4 个既有）

- [ ] **Step 10: 跑全量回归**

Run: `uv run python -m pytest skills/_shared/retrieval_protocol/tests/ -q`
Expected: 全 PASS（基线 + 4 个新测试）

- [ ] **Step 11: Commit**

```bash
git add skills/_shared/retrieval_protocol/adapters.py \
        skills/_shared/retrieval_protocol/tests/test_new_adapters.py
git commit -m "feat(retrieval_protocol): telecom adapter features 改为灵活字典

按 5/29 补充回复, telecom evidence 不再强制单一字段集。adapter 改为
拷贝 hit 全部字段到 features (保留 wrapper 必需字段除外),兼容用户
节点 / 通话边 / 设备关系 / 聚合统计 4 类 evidence。新增 4 个测试
覆盖 4 类字段透传场景。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 2：telecom 升档规则扩字段（哈希 user_id + 时间 + 基站三元组）

**Files:**
- Modify: `skills/_shared/retrieval_protocol/sensitivity_rules.py`（`_OBJECT_TIME_GEO_TRIPLE` 常量）
- Test: `skills/_shared/retrieval_protocol/tests/test_sensitivity_rules.py`（新增 test case）

**实现策略**：
扩充 `_OBJECT_TIME_GEO_TRIPLE` 元组，使其覆盖 telecom 实际字段名：
- 对象组：增加 `src_user_id` / `dst_counterparty_id`
- 时间组：增加 `event_time` / `event_date` / `event_hour`
- 位置组：增加 `station` / `cell`（无 `_id` 后缀的实际字段名）

`roaming_place` 已在位置组。

- [ ] **Step 1: 写失败测试 —— 真实通话边字段名应触发 restricted 升档**

在 `tests/test_sensitivity_rules.py` 找到 `TestClassifyTelecom`（或类似 class）类追加：

```python
def test_real_call_edge_field_names_upgrade_restricted(self):
    """src_user_id + event_time + station 组合应升 restricted (即使全部哈希化)。"""
    level, policy = classify_sensitivity(
        data_type="telecom",
        evidence_unit={
            "text": "call edge",
            "features": {
                "src_user_id": "u_hash_a3f5",
                "event_time": "2024-03-01T10:00:00+08:00",
                "station": "station_hash_42",
            },
        },
    )
    self.assertEqual((level, policy), ("restricted", "restricted"))

def test_real_call_edge_with_cell_upgrade_restricted(self):
    """cell 替代 station 也触发升档。"""
    level, _ = classify_sensitivity(
        data_type="telecom",
        evidence_unit={
            "text": "x",
            "features": {
                "src_user_id": "u_hash",
                "event_date": "2024-03-01",
                "cell": "cell_hash_7",
            },
        },
    )
    self.assertEqual(level, "restricted")
```

如类名不是 `TestClassifyTelecom`，read 文件确认实际类名后追加。

- [ ] **Step 2: 运行测试，确认失败**

Run: `uv run python -m pytest skills/_shared/retrieval_protocol/tests/test_sensitivity_rules.py -k "real_call_edge" -v`
Expected: FAIL（当前三元组没有 `src_user_id / event_time / station / cell / event_date`，会落到 `pii_masked` 而不是 `restricted`）

- [ ] **Step 3: 修改 _OBJECT_TIME_GEO_TRIPLE 常量**

在 `sensitivity_rules.py` 中找到 `_OBJECT_TIME_GEO_TRIPLE`，替换为：

```python
_OBJECT_TIME_GEO_TRIPLE = (
    # 对象组: 包含原有 + telecom 真实哈希字段
    ("target_id", "object_id", "user_id_hash",
     "src_user_id", "dst_counterparty_id"),
    # 时间组: 包含原有 + telecom 真实字段
    ("timestamp", "time_start", "captured_at", "ts",
     "event_time", "event_date", "event_hour"),
    # 位置组: 包含原有 + telecom 真实字段 (无 _id 后缀)
    ("cell_id", "station_id", "geohash", "bbox", "roaming_place",
     "station", "cell"),
)
```

- [ ] **Step 4: 运行测试，确认通过**

Run: `uv run python -m pytest skills/_shared/retrieval_protocol/tests/test_sensitivity_rules.py -k "real_call_edge" -v`
Expected: 两个新测试 PASS

- [ ] **Step 5: 跑全量回归确认无破坏既有规则**

Run: `uv run python -m pytest skills/_shared/retrieval_protocol/tests/ -q`
Expected: 全 PASS

- [ ] **Step 6: 同步更新 Task 1 中 telecom adapter 路径上的端到端验证**

在 `TestTelecom` 中追加（验证 Task 1 + Task 2 联动）：

```python
def test_call_edge_e2e_upgrades_to_restricted(self):
    """通话边 evidence 经过 adapter 后, sensitivity_level 应自动升为 restricted。"""
    hit = {
        "doc_id": "tc-ce-up",
        "summary": "call edge restricted",
        "src_user_id": "u_hash_src",
        "event_time": "2024-03-01T10:00:00+08:00",
        "station": "station_hash_42",
        "score": 0.8,
    }
    wrapper = adapters.adapt_telecom_hit(hit)
    payload = wrapper["payload"]
    self.assertEqual(payload["meta"]["sensitivity_level"], "restricted")
    self.assertEqual(payload["meta"]["access_policy"], "restricted")
```

- [ ] **Step 7: 跑相关测试确认通过**

Run: `uv run python -m pytest skills/_shared/retrieval_protocol/tests/test_new_adapters.py::TestTelecom::test_call_edge_e2e_upgrades_to_restricted -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add skills/_shared/retrieval_protocol/sensitivity_rules.py \
        skills/_shared/retrieval_protocol/tests/test_sensitivity_rules.py \
        skills/_shared/retrieval_protocol/tests/test_new_adapters.py
git commit -m "feat(retrieval_protocol): telecom 三元组扩字段 (src_user_id/event_time/station)

按 5/29 补充回复, 现网 telecom 数据真实字段是 src_user_id /
dst_counterparty_id / event_time / event_date / event_hour /
station / cell, 全部为哈希化稳定标识。组合后仍构成 对象+时间+位置
三元组, 应升 restricted。扩 _OBJECT_TIME_GEO_TRIPLE 覆盖这些字段。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 3：streetview adapter — `metadata.address.*` 展平 + `metadata.latitude/longitude`

**Files:**
- Modify: `skills/_shared/retrieval_protocol/adapters.py`（`adapt_streetview_hit` 函数体）
- Test: `skills/_shared/retrieval_protocol/tests/test_new_adapters.py`（新增 test case）

**实现策略**：
- 接受新的输入形态：hit 顶层有 `metadata` dict，其中含 `latitude / longitude / address` 三个 key；`address` 下又含 `formatted_address / business / country / province / city / district / street / street_number / adcode / sematic_description / pois / roads` 等
- 保持向后兼容旧形态（顶层 `lat / lon / city`），优先取 `metadata.*`
- geo_scope 用 `latitude / longitude / city / district`
- features 包含 `address`（嵌套）+ `pois` + `roads` + `business` + `sematic_description` + `adcode`
- 既有的 `objects / bbox / taken_at / heading / image_uri / target_count / category / source_kind / public / unique_targets` 都保留兼容

- [ ] **Step 1: 写失败测试 —— 新形态 metadata.address.* 应被解析**

在 `TestStreetview` 类追加：

```python
def test_new_format_metadata_address(self):
    """5/29 实际形态: hit.metadata.{latitude, longitude, address.{...}}。"""
    hit = {
        "_id": "EQ8RlaMMjkqWPCy0WoItIg_012_030",
        "source_path": "/mnt/nas/streetview_meta/.../EQ8RlaMMjkqWPCy0WoItIg_012_030.png",
        "metadata": {
            "latitude": 34.261,
            "longitude": 108.946,
            "address": {
                "formatted_address": "陕西省西安市碑林区北大街1号",
                "business": "钟楼",
                "country": "中国",
                "province": "陕西省",
                "city": "西安市",
                "district": "碑林区",
                "street": "北大街",
                "street_number": "1号",
                "adcode": "610103",
                "sematic_description": "钟楼东北侧15米",
                "pois": [
                    {"name": "钟楼", "tag": "旅游景点", "distance": "15", "direction": "东"},
                ],
                "roads": [{"name": "北大街", "distance": "15"}],
            },
        },
        "score": 0.85,
    }
    wrapper = adapters.adapt_streetview_hit(hit, rank=1)
    _assert_valid(self, wrapper)
    payload = wrapper["payload"]
    geo = payload["meta"]["geo_scope"]
    self.assertEqual(geo.get("lat"), 34.261)
    self.assertEqual(geo.get("lon"), 108.946)
    self.assertEqual(geo.get("city"), "西安市")
    self.assertEqual(geo.get("district"), "碑林区")
    feats = payload["meta"]["features"]
    # address dict 应进 features
    self.assertIn("address", feats)
    self.assertEqual(feats["address"]["formatted_address"], "陕西省西安市碑林区北大街1号")
    self.assertEqual(feats["address"]["business"], "钟楼")
    # pois / roads 也应能取到
    self.assertEqual(len(feats["address"]["pois"]), 1)
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `uv run python -m pytest skills/_shared/retrieval_protocol/tests/test_new_adapters.py::TestStreetview::test_new_format_metadata_address -v`
Expected: FAIL（当前 adapter 不读 `metadata.address.*` 也不读 `metadata.latitude/longitude`）

- [ ] **Step 3: 修改 adapt_streetview_hit**

替换 `adapt_streetview_hit` 函数体：

```python
def adapt_streetview_hit(
    hit: dict[str, Any],
    *,
    rank: int | None = None,
    source_id: str = "streetview_index",
) -> dict[str, Any]:
    """streetview 命中映射。

    支持两种输入形态:
    1. 旧形态(顶层): doc_id / caption / objects / bbox / taken_at / lat / lon /
       city / image_uri
    2. 5/29 新形态(嵌套): _id / source_path / metadata.{latitude, longitude,
       address.{formatted_address, business, country, province, city,
       district, street, street_number, adcode, sematic_description,
       pois[], roads[]}}; 无 bbox / 无人脸号牌遮挡

    优先取嵌套形态字段;两种形态可并存。
    """
    metadata = hit.get("metadata") or {}
    address = metadata.get("address") if isinstance(metadata, dict) else None

    # features: 既有字段 + 新增 address 嵌套结构
    features: dict[str, Any] = {}
    for key in (
        "objects", "bbox", "taken_at", "heading", "image_uri",
        "target_count", "category", "source_kind", "public", "unique_targets",
    ):
        if hit.get(key) is not None:
            features[key] = hit[key]
    if isinstance(address, dict):
        features["address"] = address

    # geo_scope: 优先 metadata.* > 顶层
    geo: dict[str, Any] = {}
    lat = metadata.get("latitude") if isinstance(metadata, dict) else None
    if lat is None:
        lat = hit.get("lat")
    lon = metadata.get("longitude") if isinstance(metadata, dict) else None
    if lon is None:
        lon = hit.get("lon")
    if lat is not None:
        geo["lat"] = lat
    if lon is not None:
        geo["lon"] = lon
    city = (address or {}).get("city") if isinstance(address, dict) else hit.get("city")
    if city:
        geo["city"] = city
    district = (address or {}).get("district") if isinstance(address, dict) else hit.get("district")
    if district:
        geo["district"] = district
    if hit.get("bbox"):
        geo["bbox"] = hit["bbox"]

    time_range = None
    if hit.get("taken_at"):
        time_range = {
            "mode": "absolute",
            "start": hit["taken_at"],
            "end": hit["taken_at"],
            "timezone": hit.get("timezone") or "Asia/Shanghai",
        }

    text = _first_nonempty(
        hit.get("caption"),
        hit.get("text"),
        hit.get("summary"),
        (address or {}).get("formatted_address") if isinstance(address, dict) else "",
    )
    level, policy = classify_sensitivity(
        data_type="streetview",
        evidence_unit={"text": text, "features": features},
    )

    payload = build_evidence_unit(
        evidence_id=hit.get("doc_id") or hit.get("evidence_id") or hit.get("_id") or "",
        data_type="streetview",
        text=text,
        source_id=hit.get("source_id") or source_id,
        source_path=hit.get("source_path") or hit.get("image_uri") or None,
        time_range=time_range,
        geo_scope=geo,
        granularity=hit.get("granularity") or "image",
        sensitivity_level=level,
        access_policy=policy,
        features=features,
    )
    return build_retrieval_evidence(
        evidence_ref=hit.get("doc_id") or hit.get("_id") or "",
        rank=rank,
        score=hit.get("score"),
        method="clip_vector",
        matched_fields=["caption", "objects"],
        payload=payload,
    )
```

- [ ] **Step 4: 运行新测试与旧测试，确认全部通过**

Run: `uv run python -m pytest skills/_shared/retrieval_protocol/tests/test_new_adapters.py -k "Streetview" -v`
Expected: 既有 `test_image_geo` 与新 `test_new_format_metadata_address` 都 PASS

- [ ] **Step 5: 跑全量回归**

Run: `uv run python -m pytest skills/_shared/retrieval_protocol/tests/ -q`
Expected: 全 PASS

- [ ] **Step 6: Commit**

```bash
git add skills/_shared/retrieval_protocol/adapters.py \
        skills/_shared/retrieval_protocol/tests/test_new_adapters.py
git commit -m "feat(retrieval_protocol): streetview adapter 兼容 metadata.address.* 嵌套形态

按 5/29 补充回复, streetview 实际返回形态是
metadata.{latitude, longitude, address.{formatted_address, business,
country, province, city, district, street, street_number, adcode,
sematic_description, pois[], roads[]}}, 无 bbox / 无人脸号牌遮挡。
adapter 优先取嵌套字段, 保持对旧顶层字段的向后兼容。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 4：streetview docstring 与文档说明 —— 移除 bbox/人脸号牌假设

**Files:**
- Modify: `skills/_shared/retrieval_protocol/adapters.py`（`adapt_streetview_hit` docstring，Task 3 已合并）
- Modify: `skills/_shared/retrieval_protocol/README.md`（streetview 字段映射章节）

**实现策略**：
Task 3 已经在 docstring 中加了说明"无 bbox / 无人脸号牌遮挡"。本 task 在 README 中补充：

- 在 README 现有 6 类 adapter 字段映射章节追加 "5/29 补充回复对齐说明"
- 说明：streetview 不假设 bbox，因为目标字段不带 bbox；不假设人脸号牌遮挡，所以 `_classify_streetview` 在新形态下不会走 `_has_unmasked_face_plate` 升档分支（除非未来反馈变化）
- 精确 lat/lon 仍由 `_has_struct_id` 的 LATLON 正则覆盖

- [ ] **Step 1: 读 README 找到 streetview 字段映射章节**

Run: `grep -n "streetview" skills/_shared/retrieval_protocol/README.md | head -20`
Expected: 输出 streetview 出现的行号

- [ ] **Step 2: 修改 README streetview 段落，追加 5/29 对齐说明**

定位到 README 中描述 streetview 字段映射的位置，追加一段 markdown：

```markdown
> **5/29 对齐**：实际数据形态是嵌套 `metadata.{latitude, longitude, address.*}`，无 `bbox`，无人脸/号牌遮挡假设。adapter 同时兼容旧顶层字段（`lat`/`lon`/`city`/`objects`/`bbox`/...）。敏感度判定路径：精确经纬度（≥4 位小数）仍由 `_has_struct_id` 的 LATLON 正则升 `restricted`；详细门牌地址（`address.formatted_address` + `street_number`）属字符串，不触发 PII 正则但落进 features，由上层合规检测器二次判定。
```

- [ ] **Step 3: 不需新增代码测试，但跑回归保险**

Run: `uv run python -m pytest skills/_shared/retrieval_protocol/tests/ -q`
Expected: 全 PASS

- [ ] **Step 4: Commit**

```bash
git add skills/_shared/retrieval_protocol/README.md
git commit -m "docs(retrieval_protocol): README 加入 streetview 5/29 对齐说明

按 5/29 补充回复, 明确 streetview 实际数据无 bbox、无人脸号牌遮挡,
敏感度判定的实际路径(精确经纬度走 LATLON 正则、详细地址走上层
合规检测器)。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 5：surveillance adapter — `video_id/raw_segment_uri/labels/object_summary/location` 字段对齐

**Files:**
- Modify: `skills/_shared/retrieval_protocol/adapters.py`（`adapt_surveillance_hit` 函数体）
- Test: `skills/_shared/retrieval_protocol/tests/test_new_adapters.py`（新增 test case）

**实现策略**：
- 新形态字段：`video_id / camera_id / filename / raw_segment_uri / started_at / ended_at / labels / object_summary / location / metadata / score`
- `location` 是 dict（含 city / camera_lat / camera_lon 等），`metadata` 是 dict（任意业务字段）
- time_range 优先 `started_at / ended_at`，回落 `clip_start / clip_end`
- evidence_id 优先 `video_id`，回落 `doc_id`
- source_path 优先 `raw_segment_uri`，回落 `video_uri`
- features 增加新字段：`video_id / camera_id / filename / raw_segment_uri / started_at / ended_at / labels / object_summary / location / metadata`
- 既有字段 `objects / bbox / clip_start / clip_end / behavior / stream_url / ...` 保留兼容

- [ ] **Step 1: 写失败测试 —— 新形态 surveillance hit 字段映射**

在 `TestSurveillance` 类追加：

```python
def test_new_format_video_record(self):
    """5/29 实际形态: video_id / camera_id / raw_segment_uri / started_at /
    ended_at / labels / object_summary / location。"""
    hit = {
        "video_id": "vid_001",
        "camera_id": "cam_42",
        "filename": "20240301_10_42.mp4",
        "raw_segment_uri": "s3://surv/vid_001.mp4",
        "started_at": "2024-03-01T10:00:00+08:00",
        "ended_at": "2024-03-01T10:30:00+08:00",
        "labels": ["traffic", "intersection"],
        "object_summary": {"person": 12, "car": 34},
        "location": {"city": "Shanghai", "camera_lat": 31.235, "camera_lon": 121.505},
        "metadata": {"frame_rate": 25, "resolution": "1920x1080"},
        "score": 0.91,
    }
    wrapper = adapters.adapt_surveillance_hit(hit, rank=1)
    _assert_valid(self, wrapper)
    payload = wrapper["payload"]
    # evidence_id 优先 video_id
    self.assertEqual(payload["evidence_id"], "vid_001")
    # source_path 优先 raw_segment_uri
    self.assertEqual(payload["meta"]["source_path"], "s3://surv/vid_001.mp4")
    # time_range 取 started_at / ended_at
    tr = payload["meta"]["time_range"]
    self.assertEqual(tr["start"], "2024-03-01T10:00:00+08:00")
    self.assertEqual(tr["end"], "2024-03-01T10:30:00+08:00")
    # geo_scope: location.city / camera_lat / camera_lon 展平
    geo = payload["meta"]["geo_scope"]
    self.assertEqual(geo["city"], "Shanghai")
    self.assertEqual(geo["lat"], 31.235)
    self.assertEqual(geo["lon"], 121.505)
    # features 含新字段
    feats = payload["meta"]["features"]
    for key in ("video_id", "camera_id", "filename", "raw_segment_uri",
                "labels", "object_summary", "location", "metadata"):
        self.assertIn(key, feats, msg=f"missing {key}")
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `uv run python -m pytest skills/_shared/retrieval_protocol/tests/test_new_adapters.py::TestSurveillance::test_new_format_video_record -v`
Expected: FAIL（evidence_id 不会用 video_id，source_path 不会用 raw_segment_uri，time_range 不会从 started_at/ended_at 取）

- [ ] **Step 3: 修改 adapt_surveillance_hit**

替换函数体：

```python
def adapt_surveillance_hit(
    hit: dict[str, Any],
    *,
    rank: int | None = None,
    source_id: str = "surveillance_index",
) -> dict[str, Any]:
    """surveillance 命中映射。

    支持两种输入形态:
    1. 旧形态: doc_id / summary / objects / bbox / clip_start / clip_end /
       behavior / camera_id / camera_lat / camera_lon / stream_url / ...
    2. 5/29 新形态: video_id / camera_id / filename / raw_segment_uri /
       started_at / ended_at / labels / object_summary / location.{city,
       camera_lat, camera_lon} / metadata.{...}; 无逐帧 bbox。

    敏感度: 默认 restricted; 已打码 + 无 streaming + 无具体点位才降到
    pii_masked; 仅聚合统计 + k>=10 + 无 streaming/未打码才降到
    aggregated_safe (见 sensitivity_rules._classify_surveillance)。
    """
    location = hit.get("location") or {}
    if not isinstance(location, dict):
        location = {}

    # features: 旧字段 + 新字段一并保留
    feature_keys = (
        # 旧形态
        "objects", "bbox", "clip_start", "clip_end", "behavior",
        "video_uri", "stream_url", "playback_url", "channel_id",
        "camera_location", "target_count", "people_count", "vehicle_count",
        "unique_targets", "source_kind", "public",
        # 5/29 新形态
        "video_id", "camera_id", "filename", "raw_segment_uri",
        "started_at", "ended_at", "labels", "object_summary",
        "location", "metadata",
    )
    features = {key: hit[key] for key in feature_keys if hit.get(key) is not None}

    # geo_scope: 优先 location.* > 顶层
    geo: dict[str, Any] = {}
    city = location.get("city") or hit.get("city")
    if city:
        geo["city"] = city
    camera_lat = location.get("camera_lat", hit.get("camera_lat"))
    if camera_lat is not None:
        geo["lat"] = camera_lat
    camera_lon = location.get("camera_lon", hit.get("camera_lon"))
    if camera_lon is not None:
        geo["lon"] = camera_lon
    if hit.get("landmark"):
        geo["landmark"] = hit["landmark"]

    # time_range: 优先 started_at/ended_at > clip_start/clip_end
    start = hit.get("started_at") or hit.get("clip_start")
    end = hit.get("ended_at") or hit.get("clip_end")
    time_range = None
    if start and end:
        time_range = {
            "mode": "absolute",
            "start": start,
            "end": end,
            "timezone": hit.get("timezone") or "Asia/Shanghai",
        }

    text = _first_nonempty(hit.get("caption"), hit.get("text"), hit.get("summary"))
    level, policy = classify_sensitivity(
        data_type="surveillance",
        evidence_unit={"text": text, "features": features},
    )

    payload = build_evidence_unit(
        evidence_id=hit.get("video_id") or hit.get("doc_id") or hit.get("evidence_id") or "",
        data_type="surveillance",
        text=text,
        source_id=hit.get("source_id") or source_id,
        source_path=hit.get("raw_segment_uri") or hit.get("source_path") or hit.get("video_uri") or None,
        time_range=time_range,
        geo_scope=geo,
        granularity=hit.get("granularity") or "clip",
        sensitivity_level=level,
        access_policy=policy,
        features=features,
    )
    return build_retrieval_evidence(
        evidence_ref=hit.get("video_id") or hit.get("doc_id") or "",
        rank=rank,
        score=hit.get("score"),
        method="clip_vector_temporal",
        matched_fields=["caption", "behavior"],
        payload=payload,
    )
```

- [ ] **Step 4: 运行新测试 + 既有 surveillance 测试**

Run: `uv run python -m pytest skills/_shared/retrieval_protocol/tests/test_new_adapters.py -k "Surveillance" -v`
Expected: 全 PASS（既有 `test_default_restricted` / `test_downgrade_when_masked_no_link` + 新 `test_new_format_video_record`）

- [ ] **Step 5: 跑全量回归**

Run: `uv run python -m pytest skills/_shared/retrieval_protocol/tests/ -q`
Expected: 全 PASS

- [ ] **Step 6: 在 README 追加 surveillance 5/29 对齐说明**

定位到 README 中 surveillance 字段映射位置，追加：

```markdown
> **5/29 对齐**：实际数据形态是 `video_id / camera_id / filename / raw_segment_uri / started_at / ended_at / labels / object_summary / location.{city,camera_lat,camera_lon} / metadata.{...}`，无逐帧 bbox。adapter 同时兼容旧顶层字段（`clip_start`/`clip_end`/`stream_url`/`objects` 等）。`object_summary` 是计数聚合（如 `{"person": 12, "car": 34}`），不是逐目标列表，不会触发 `_has_unmasked_face_plate`。当前形态下默认仍是 `restricted`（无 `objects` 列表 = 无法判定打码 = 保守取顶档），与师兄反馈"yolo 打码理论可做未测试"一致。
```

- [ ] **Step 7: Commit**

```bash
git add skills/_shared/retrieval_protocol/adapters.py \
        skills/_shared/retrieval_protocol/tests/test_new_adapters.py \
        skills/_shared/retrieval_protocol/README.md
git commit -m "feat(retrieval_protocol): surveillance adapter 兼容 video_id/raw_segment_uri/object_summary

按 5/29 补充回复, surveillance 实际形态是 video_id / camera_id /
raw_segment_uri / started_at / ended_at / labels / object_summary /
location, 无逐帧 bbox。adapter 优先取新字段(evidence_id=video_id,
source_path=raw_segment_uri, time_range 取 started_at/ended_at,
geo_scope 取 location.{city,camera_lat,camera_lon}), 同时向后兼容
旧形态。默认仍 restricted(打码状态未测试,保守取顶档)。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 6：remote_sensing adapter — `id/title/content/url/hash/resolution/exif` 字段对齐

**Files:**
- Modify: `skills/_shared/retrieval_protocol/adapters.py`（`adapt_remote_sensing_hit` 函数体）
- Test: `skills/_shared/retrieval_protocol/tests/test_new_adapters.py`（新增 test case）

**实现策略**：
- 新形态字段：`id / title / content / similarity / rank / url / hash / resolution / exif`
- evidence_id 优先 `id`，回落 `doc_id`
- text 优先 `title + content`（拼接）或 `content`，回落 `caption`
- source_path 优先 `url`
- features 增加：`id / title / content / similarity / url / hash / resolution / exif`
- 既有 `objects / bbox / tile_id / change_score / cloud_cover / sensitive_facility / internal_annotation / source_kind / public` 保留
- 合规判定：仅精确地理位置（已由 `_has_struct_id` LATLON 覆盖，无需额外升档逻辑）

- [ ] **Step 1: 写失败测试 —— 新形态 remote_sensing hit**

在 `TestRemoteSensing` 类追加：

```python
def test_new_format_imagery_record(self):
    """5/29 实际形态: id / title / content / similarity / url / hash /
    resolution / exif。"""
    hit = {
        "id": "rs-new-001",
        "title": "瓦片 T08-12 影像",
        "content": "陕西省西安市碑林区上空 0.5m 分辨率",
        "similarity": 0.82,
        "rank": 3,
        "url": "s3://rs/rs-new-001.tif",
        "hash": "sha256:abc123",
        "resolution": "0.5m",
        "exif": {"capture_time": "2024-03-15T10:00:00+08:00"},
    }
    wrapper = adapters.adapt_remote_sensing_hit(hit, rank=1)
    _assert_valid(self, wrapper)
    payload = wrapper["payload"]
    self.assertEqual(payload["evidence_id"], "rs-new-001")
    self.assertEqual(payload["meta"]["source_path"], "s3://rs/rs-new-001.tif")
    # text 应包含 title 与 content
    self.assertTrue(payload["text"])
    self.assertIn("瓦片", payload["text"])
    feats = payload["meta"]["features"]
    for key in ("id", "title", "content", "similarity", "url", "hash",
                "resolution", "exif"):
        self.assertIn(key, feats, msg=f"missing {key}")

def test_new_format_with_precise_coord_in_text_upgrades(self):
    """content 中含明文精确经纬度应升 restricted (struct_id 正则)。"""
    hit = {
        "id": "rs-002",
        "title": "瓦片",
        "content": "中心点 121.4738, 31.2304",  # LATLON 5 位小数命中正则
        "url": "s3://rs/rs-002.tif",
    }
    wrapper = adapters.adapt_remote_sensing_hit(hit)
    payload = wrapper["payload"]
    self.assertEqual(payload["meta"]["sensitivity_level"], "restricted")
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `uv run python -m pytest skills/_shared/retrieval_protocol/tests/test_new_adapters.py::TestRemoteSensing::test_new_format_imagery_record -v`
Expected: FAIL（evidence_id 不会用 `id`、source_path 不会用 `url`、features 不含新字段）

- [ ] **Step 3: 修改 adapt_remote_sensing_hit**

替换函数体：

```python
def adapt_remote_sensing_hit(
    hit: dict[str, Any],
    *,
    rank: int | None = None,
    source_id: str = "remote_sensing_index",
) -> dict[str, Any]:
    """remote_sensing 命中映射。

    支持两种输入形态:
    1. 旧形态: doc_id / caption / objects / bbox / tile_id / taken_at /
       change_score / cloud_cover / image_uri
    2. 5/29 新形态: id / title / content / similarity / rank / url / hash /
       resolution / exif

    合规重点仅"精确地理位置": content 含明文经纬度由 _has_struct_id
    的 LATLON 正则升 restricted。
    """
    feature_keys = (
        # 旧形态
        "objects", "bbox", "tile_id", "taken_at", "change_score",
        "cloud_cover", "image_uri", "sensitive_facility", "internal_annotation",
        "source_kind", "public",
        # 5/29 新形态
        "id", "title", "content", "similarity", "url", "hash",
        "resolution", "exif",
    )
    features = {key: hit[key] for key in feature_keys if hit.get(key) is not None}

    geo: dict[str, Any] = {}
    if hit.get("bbox"):
        geo["bbox"] = hit["bbox"]
    if hit.get("city"):
        geo["city"] = hit["city"]
    if hit.get("district"):
        geo["district"] = hit["district"]

    time_range = None
    if hit.get("taken_at"):
        time_range = {
            "mode": "absolute",
            "start": hit["taken_at"],
            "end": hit.get("taken_at_end") or hit["taken_at"],
            "timezone": hit.get("timezone") or "Asia/Shanghai",
        }

    title = hit.get("title") or ""
    content = hit.get("content") or ""
    combined = (title + "\n" + content).strip() if (title or content) else ""
    text = _first_nonempty(
        combined,
        hit.get("caption"),
        hit.get("text"),
        hit.get("summary"),
    )
    level, policy = classify_sensitivity(
        data_type="remote_sensing",
        evidence_unit={"text": text, "features": features},
    )

    payload = build_evidence_unit(
        evidence_id=hit.get("id") or hit.get("doc_id") or hit.get("evidence_id") or "",
        data_type="remote_sensing",
        text=text,
        source_id=hit.get("source_id") or source_id,
        source_path=hit.get("url") or hit.get("source_path") or hit.get("image_uri") or None,
        time_range=time_range,
        geo_scope=geo,
        granularity=hit.get("granularity") or "tile",
        sensitivity_level=level,
        access_policy=policy,
        features=features,
    )
    return build_retrieval_evidence(
        evidence_ref=hit.get("id") or hit.get("doc_id") or "",
        rank=rank,
        score=hit.get("similarity") or hit.get("score"),
        method="clip_vector",
        matched_fields=["caption", "objects"],
        payload=payload,
    )
```

- [ ] **Step 4: 运行新测试 + 既有测试**

Run: `uv run python -m pytest skills/_shared/retrieval_protocol/tests/test_new_adapters.py -k "RemoteSensing" -v`
Expected: 全 PASS

- [ ] **Step 5: 跑全量回归**

Run: `uv run python -m pytest skills/_shared/retrieval_protocol/tests/ -q`
Expected: 全 PASS

- [ ] **Step 6: 在 README 追加 remote_sensing 5/29 对齐说明**

定位到 README 中 remote_sensing 字段映射位置，追加：

```markdown
> **5/29 对齐**：实际数据形态是 `id / title / content / similarity / rank / url / hash / resolution / exif`。adapter 优先取新字段（`evidence_id=id`，`source_path=url`，`text=title+content`，`score=similarity`），同时向后兼容旧 `doc_id`/`caption`/`image_uri`。合规重点为"精确地理位置"，由 `_has_struct_id` 的 LATLON 正则覆盖（`content` 中含 4 位以上小数的经纬度即升 `restricted`）。
```

- [ ] **Step 7: Commit**

```bash
git add skills/_shared/retrieval_protocol/adapters.py \
        skills/_shared/retrieval_protocol/tests/test_new_adapters.py \
        skills/_shared/retrieval_protocol/README.md
git commit -m "feat(retrieval_protocol): remote_sensing adapter 兼容 id/title/content/url/hash 形态

按 5/29 补充回复, remote_sensing 实际形态是 id / title / content /
similarity / rank / url / hash / resolution / exif。adapter 优先取
id (evidence_id) / url (source_path) / title+content (text) /
similarity (score), 同时向后兼容 doc_id / caption / image_uri。
合规重点仅精确地理位置, 由既有 LATLON 正则覆盖。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 7：code adapter 文档说明 —— 本期不参与 retrieval

**Files:**
- Modify: `skills/_shared/retrieval_protocol/adapters.py`（`adapt_code_hit` docstring）
- Modify: `skills/_shared/retrieval_protocol/README.md`（code 字段映射章节）

**实现策略**：
仅 docstring + README 说明，不动 adapter 函数体（保留接口）。

- [ ] **Step 1: 修改 adapt_code_hit docstring**

定位到 `adapters.py` 中 `adapt_code_hit` 的 docstring，在首段后追加：

```python
    """code 命中映射。预期字段:``doc_id`` / ``snippet`` / ``file_path`` /
    ``line_start`` / ``line_end`` / ``lang`` / ``ast_node_type`` / ``symbol``。

    ``snippet → text``;``file_path + line_start/end → locator``;
    ``lang / ast_node_type / symbol`` 进 ``features``。

    **5/29 备注**: 代码片段 skill 本期仅做敏感词分析,不参与 retrieval。
    本 adapter 接口保留,供未来检索接入。当前调用方应直接调用敏感词分析
    skill, 而不经本 adapter。
    """
```

- [ ] **Step 2: 修改 README code 字段映射章节**

定位到 README 中 code 字段映射位置，追加：

```markdown
> **5/29 对齐**：代码片段 skill 当前仅做敏感词分析（密钥/账号 token 检测），不参与 retrieval。本 adapter 接口保留，未启用。
```

- [ ] **Step 3: 跑全量回归（仅为保险）**

Run: `uv run python -m pytest skills/_shared/retrieval_protocol/tests/ -q`
Expected: 全 PASS

- [ ] **Step 4: Commit**

```bash
git add skills/_shared/retrieval_protocol/adapters.py \
        skills/_shared/retrieval_protocol/README.md
git commit -m "docs(retrieval_protocol): code adapter 标注本期不参与 retrieval

按 5/29 补充回复, 代码片段 skill 当前仅做敏感词分析, 不参与
retrieval。在 docstring 与 README 加注; adapter 接口保留, 供未来
检索接入。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 8：本计划完成记录 + 全量验证

**Files:**
- Modify: `docs/superpowers/plans/2026-05-29-adapter-rebuild-after-feedback.md`（本文件，勾选 task）
- Possibly modify: 此 plan 中的"基线测试数"行（最终改成"完成后测试数"）

- [ ] **Step 1: 全量回归 + 计数**

Run: `uv run python -m pytest skills/_shared/retrieval_protocol/tests/ -q 2>&1 | tail -5`
Expected: 全 PASS，新测试数比基线 +10 左右（Task 1 +4, Task 2 +3, Task 3 +1, Task 5 +1, Task 6 +2 = +11 个新测试方法）

- [ ] **Step 2: 在 plan 文件末尾追加完成记录**

在本文件末尾追加：

```markdown
---

## 完成记录

- **基线测试数**：272（task #18 启动前 main 分支）
- **完成后测试数**：N（task 8 step 1 实测）
- **新增测试**：~11 个（4 个 telecom features 透传 + 2 个 telecom 升档 + 1 个 streetview 新形态 + 1 个 surveillance 新形态 + 2 个 remote_sensing 新形态 + 1 端到端）
- **影响的公开 API**：无（adapter 函数签名不变；sensitivity_rules 公开 API 不变）
- **影响的 SKILL.md / artifacts**：无
- **commits**：T1 `feat(retrieval_protocol): telecom adapter features 改为灵活字典` 起，至 T7 `docs(retrieval_protocol): code adapter 标注本期不参与 retrieval`
- **遗留**：traffic_flow / statistics_yearbook / citybench / network_traffic / road_traffic / policy 6 个 adapter 本计划未触及；如有后续反馈再开新 plan
```

- [ ] **Step 3: 把本 plan 顶部所有 checkbox 标记为已勾选（如 subagent 工作流自动维护可跳过）**

- [ ] **Step 4: Commit 计划完成记录**

```bash
git add docs/superpowers/plans/2026-05-29-adapter-rebuild-after-feedback.md
git commit -m "docs(plan): 标记 adapter-rebuild-after-feedback 完成

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

- [ ] **Step 5: 把 task #18 状态置 completed**

通过 TaskUpdate 工具或对话告知用户。

---

## Self-Review 检查

**1. Spec coverage**：
- telecom features 灵活字典 → Task 1
- telecom 哈希 ID + 时间 + 基站三元组升 restricted → Task 2
- streetview metadata.address.* + latitude/longitude → Task 3
- streetview 移除 bbox / 人脸号牌假设 → Task 4 (docstring + README)
- surveillance video_id / camera_id / raw_segment_uri / started_at / ended_at / labels / object_summary / location → Task 5
- surveillance 移除逐帧 bbox 假设 → Task 5 (含)
- remote_sensing id / title / content / similarity / url / hash / resolution / exif → Task 6
- code 本期不参与 retrieval → Task 7
- statistics_yearbook 不在范围 → 计划开头明确

全部 spec 点都有覆盖任务。

**2. Placeholder scan**：无 TBD / TODO / "fill in later"；每个代码步骤都给了具体代码块或定位说明。

**3. Type / 命名一致性**：
- `_OBJECT_TIME_GEO_TRIPLE` 在 Task 2 步骤中保持小写、下划线、顶层模块常量
- adapter 函数名一律 `adapt_*_hit`，与现有命名一致
- 测试 class 名 `TestTelecom` / `TestStreetview` / `TestSurveillance` / `TestRemoteSensing` 与现有文件一致

---

**Execution Handoff**：本 plan 完成。请 approve 并选择执行模式（subagent-driven 推荐 / inline）。

---

## 完成记录

- **执行模式**：subagent-driven-development（fresh implementer + spec reviewer + code quality reviewer 双段 review，每 task 一组）
- **执行时间**：2026-05-29
- **基线测试数**：272（task #18 启动前 `03dbf92`）
- **完成后测试数**：**284**（+12，全部 PASS）
- **新增测试明细**：
  - T1（telecom features 灵活字典）：+4 (`test_user_node_features_passthrough` / `test_call_edge_features_passthrough` / `test_edge_relation_features_passthrough` / `test_aggregated_stat_features_passthrough`)
  - T2（telecom 三元组扩字段）：+3 (`test_real_call_edge_field_names_upgrade_restricted` / `test_real_call_edge_with_cell_upgrade_restricted` / `test_call_edge_e2e_upgrades_to_restricted`)
  - T3（streetview metadata.address.*）：+1 (`test_new_format_metadata_address`)
  - T3 cleanup：+1 (`test_metadata_address_partial_falls_back_to_top_level`)
  - T4（streetview README）：+0
  - T5（surveillance video_id/raw_segment_uri 等）：+1 (`test_new_format_video_record`)
  - T6（remote_sensing id/title/content 等）：+2 (`test_new_format_imagery_record` / `test_new_format_with_precise_coord_in_text_upgrades`)
  - T6 cleanup：+0
  - T7（code adapter 文档）：+0

- **commits**：
  - `ba785cc` feat(retrieval_protocol): telecom adapter features 改为灵活字典
  - `2c411fd` feat(retrieval_protocol): telecom 三元组扩字段 (src_user_id/event_time/station)
  - `a68f383` feat(retrieval_protocol): streetview adapter 兼容 metadata.address.* 嵌套形态
  - `b89d3f1` refactor(retrieval_protocol): streetview adapter 简化 address/city 回退逻辑（T3 cleanup）
  - `61b9a2b` docs(retrieval_protocol): README 加入 streetview 5/29 对齐说明
  - `f899aa2` feat(retrieval_protocol): surveillance adapter 兼容 video_id/raw_segment_uri/object_summary
  - `73647a4` feat(retrieval_protocol): remote_sensing adapter 兼容 id/title/content/url/hash 形态
  - `2b6a6c5` refactor(retrieval_protocol): remote_sensing evidence_ref 复用 evidence_id chain + 注释 score 选择（T6 cleanup）
  - `f1eaf9a` docs(retrieval_protocol): code adapter 标注本期不参与 retrieval

- **影响的公开 API**：无（adapter 函数签名不变；sensitivity_rules 公开 API 不变）
- **影响的 SKILL.md / artifacts**：无
- **不在本 plan 范围（明确未处理）**：traffic_flow / statistics_yearbook / citybench / network_traffic / road_traffic / policy 6 个既有 adapter；如有后续反馈再开新 plan
- **遗留可选 polish**（reviewer 提出但非阻塞）：
  - T2 minor M1/M2/M3：sensitivity_rules 测试可增加 `event_hour` / `dst_counterparty_id` / 「部分三元组不升档」负向断言
  - T5 minor：surveillance `camera_lat/camera_lon` fallback 与 `city` 行为不一致；新形态 sensitivity 路由未单测断言
  - T6 minor：`matched_fields=["caption", "objects"]` 对新形态不再贴切，可后续按形态动态选

执行过程中所有 spec reviewer 与 code quality reviewer 均 ✅ Approved。两次 reviewer-driven cleanup（T3、T6）已落地。
