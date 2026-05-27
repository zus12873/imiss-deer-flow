# Adapter 敏感度预标规则 + Audit Sink 字段扩展 —— 设计文档

- **状态**：📝 草稿 v2（待用户 review）
- **设计日期**：2026-05-27
- **分支**：当前 `feat/unified-retrieval-protocol`（v1.1 已落地）→ 本设计目标分支
  `feat/sensitivity-and-audit`（待开）
- **触发反馈**：仓库 `docs/new_tasks/task.md` 第 42–48 行三条反馈 + 师兄
  2026-05-27 在 review v1 时给出的"敏感度落档 + audit 字段补充"补充说明
- **本次交付范围**：S1（敏感度落档规则 + 6 类 adapter 预标）+ S2（audit_sink
  字段扩展 + 默认 JSONL 落盘）。Planner / Aggregator stdlib + LangGraph
  middleware 接入均拆下一分支，本次不做。

---

## 1. 背景

`retrieval_protocol` v1.1 已落地：Input Envelope（§3）、SkillResult（§4）、
§7 校验器、§6 适配器、v1.1 增补的 budget / errors / 中间件三件套。`task.md` 反馈
三条原文：

> ① `Input Envelope` 和 `SkillResult` 不应该被设计成另一套独立协议，而是放进
>   `Skill Schema` 的 retrieval profile 里。
>
> ② `budget` 建议放在 `Envelope` 顶层，可选。Planner 主动拆，聚合层兜底裁剪。
>
> ③ Plan 模板承担拆解和编排职责，聚合层按 `query_id` 对齐 / 去重 / 排序 / 裁剪。

v1 spec 把反馈①理解成"SKILL.md frontmatter 加 retrieval_profile YAML 段 / Skill
类加字段 / Gateway 加字段"。师兄 review 时纠正：反馈①的落地工作**不是 schema
字段收敛**，而是 —— 在统一检索侧 **明确 evidence 初始敏感等级的落档标准**，并给 6
类新 adapter 配置**默认级别 + 升 / 降级条件**。adapter 在构造 evidence 时按字段
内容做**保守预标**；最终是否命中违规、是否过滤 / 脱敏 / 聚合 / 人工复核，仍由
合规检测器和处置矩阵统一决策。

同时，audit_sink 的现有字段不足以回答"具体哪条 evidence 被处理、命中了哪类违规、
风险字段在哪里、执行了什么动作、为什么过滤 / 脱敏 / 降级"。需要补一组字段。

反馈②的"顶层 budget" v1.1 已就绪；反馈②的"聚合层兜底裁剪" + 反馈③的 Planner /
聚合层 / middleware 接入，统一拆到下一分支。

## 2. 范围

| Section | 内容 | 本次 |
|---|---|---|
| S1 | 敏感度落档规则 + 6 类 adapter 预标 | ✅ |
| S2 | audit_sink 字段扩展 + 默认 JSONL 落盘 | ✅ |
| S3 | Planner / Aggregator stdlib | ❌ 下分支 |
| S4 | LangGraph PlannerMiddleware / AggregatorMiddleware 接入 | ❌ 下分支 |

明确**不做**：

- 不动 `SKILL.md` frontmatter；不加 retrieval_profile YAML 段。
- 不动 `deerflow.skills.types.Skill` dataclass；不加字段。
- 不动 `app.gateway.routers.skills.SkillResponse`；不加字段。
- 不引入 Planner、Aggregator、子问题拆解、并行编排、预算兜底裁剪。
- 不接 LangGraph middleware 链。

## 3. Section 1 —— 敏感度落档规则 + 6 类 adapter 预标

### 3.1 四档落档标准

师兄给出的初版规则原文锚定（落进 `schema.py` 注释 + 常量；后续按实际数据集
迭代）：

| 档位 | 适用 | `access_policy` |
|---|---|---|
| `open` | 已公开、普通、基本不敏感的 evidence。例：公开政策法规、公开年鉴说明、公开指标解释、普通公开文本。**不包含**个人标识 / 设备标识 / 账号 / 车辆 / 精确位置 / 通道链接 / 凭证密钥 / 内部研判 / 对象级风险标签 | `open` |
| `aggregated_safe` | 只含聚合统计、不能定位到单个对象的 evidence。例：count / sum / avg / ratio / flow_count / unique_count / duration_sum / change_score。**第一阶段建议 k ≥ 10** 才认为是安全聚合（k = 该统计覆盖的可区分主体数：用户 / 号码 / 车辆 / 设备 / 目标 / 点位 / 社区成员 / 统计样本）。仅有记录数无法确认主体数量时，不可单凭记录数判定 `aggregated_safe`；k < 10 或统计结合具体位置 / 时间 / 人群特征 / 风险标签 → 升 `restricted` 或人工复核 | `open` |
| `pii_masked` | 含对象 / 设备 / 车辆 / 图像目标 / 代码符号等敏感字段，但**字段值已经哈希 / 脱敏 / 泛化 / 匿名化 / 打码**。例：哈希 user_id / imei、community_id、对象 A / 设备 X、已打码手机号 / 车牌、已模糊化人脸、只保留 bbox 的街景目标、内部代码 doc_id/symbol/ast_node_type 但无密钥。"已脱敏但建议内部使用"，不是公开安全 | `internal_only` |
| `restricted` | 高敏 evidence，不能直接进 LLM 或直接输出。例：明文身份证 / 手机号 / 银行卡 / 邮箱 / 护照号 / IMEI / IP / MAC / 设备号、精确经纬度、详细门牌、对象+时间+位置组合、通话内容、单对象通信明细、对象级 risk/purefraud/mutation 标签、涉诈重点对象清单、内部协查、处置优先级、内部研判、视频 stream_url/playback_url/channel_id/camera_id、具体监控点位、未打码人脸 / 车牌、人员轨迹、clip/frame 级或对象级行为识别结果、代码中 password/token/api_key/secret/private_key/数据库连接串/内部服务地址、敏感设施点位、内部遥感标注、重点区域变化研判 | `restricted` |

注：`SENSITIVE_LEVELS = {"pii_masked", "restricted"}`（已存在）不变；middleware 仍按
这两档统计敏感命中数。

### 3.2 新增模块 `sensitivity_rules.py`

文件 `skills/_shared/retrieval_protocol/sensitivity_rules.py`（stdlib only）。

#### 3.2.1 默认级别表

```python
# 本次按师兄规则锁默认级别的 6 个 data_type
# (其中 gazetteer 由 adapt_road_traffic_hit 输出 —— task.md §6.3 已实现)
DEFAULT_SENSITIVITY: dict[str, tuple[str, str]] = {
    "gazetteer":      ("aggregated_safe", "open"),
    "telecom":        ("pii_masked",      "internal_only"),
    "code":           ("pii_masked",      "internal_only"),
    "streetview":     ("pii_masked",      "internal_only"),
    "remote_sensing": ("aggregated_safe", "open"),
    "surveillance":   ("restricted",      "restricted"),
}
# 本次不改的 4 类(保持现有 adapter 硬编码默认):
# - spatiotemporal_trajectory(adapt_citybench)
# - netflow(adapt_network_traffic)
# - policy(adapt_policy)
# - traffic_flow(adapt_traffic_flow) —— 师兄未给规则,待下一版
K_THRESHOLD_AGGREGATED_SAFE = 10
```

#### 3.2.2 升 / 降级规则（按 data_type 分派）

每类一个 classifier。共享底层判定基元：

- `_has_struct_id(unit)`：是否含**明文**结构化 ID（明文 user_id / phone / id_card / imei / ip / mac / 银行卡 / 邮箱 / 护照 / 设备号、精确经纬度、详细门牌）。`evidence_unit.text` + `features` 字段两路扫描。
- `_has_aggregated_k_ge(unit, k)`：features 中是否含 `unique_users` / `unique_contacts` / `unique_devices` / `unique_targets` / `sample_count` / `community_size` 等可表达 k 的字段且 ≥ k。
- `_has_secret_token(unit)`：text 中是否含 password / token / api_key / secret / private_key / 数据库连接串 / 内部 IP / 内部服务地址（保守正则）。
- `_has_object_time_geo_combo(unit)`：features / locator 中是否同时给出对象标识 + 时间 + 位置三元组。
- `_has_risk_label(unit)`：features 中是否含 `risk_label` / `purefraud_flag` / `mutation_flag` / `case_priority` 等对象级风险标签。
- `_has_streaming_link(unit)`：features / artifact 中是否含 `stream_url` / `playback_url` / `channel_id` / `camera_id`。
- `_has_unmasked_face_plate(unit)`：features 中 `objects` 含 face / license_plate 且未声明 `masked=True`。
- `_marked_public(unit)`：source 或 features 中明确 `public=True` / `source_kind="public"`。

按 data_type 分派的规则原文（直接对齐师兄给出的表）：

| data_type | 默认 | 升级 → `restricted+restricted` | 降级 |
|---|---|---|---|
| `gazetteer` | `aggregated_safe+open` | 小样本（k<10） / 内部统计口径 / 精细点位统计 / 可定位到具体对象或设施 | `_marked_public=True` 且无敏感字段 → `open+open` |
| `telecom` | `pii_masked+internal_only` | 对象+时间+station/cell/roaming_place 组合 / 含对象级 risk/purefraud/mutation 标签 / 含明文 phone/imei | 仅 call_count / unique_contacts / duration_sum 等聚合 + 不绑定单对象 + k≥10 → `aggregated_safe+open` |
| `code` | `pii_masked+internal_only` | 含 password / token / api_key / secret / private_key / 内部 IP / 数据库连接串 | `_marked_public=True` 且无密钥 → `open+open` |
| `streetview` | `pii_masked+internal_only` | 未打码人脸 / 车牌 / 详细门牌 / 精确拍摄位置 / 可识别个人或车辆 | 仅目标数量 / 类别统计 + 无可识别对象 + 无精确位置 → `aggregated_safe+open` |
| `remote_sensing` | `aggregated_safe+open` | 精确坐标 / 敏感设施点位 / 内部标注 / 重点区域变化研判 / 城市治理敏感设施 | `_marked_public=True` 且低敏 → `open+open` |
| `surveillance` | `restricted+restricted` | （已是顶档） | ① 已打码 / 模糊化 + 无 streaming link + 无具体点位 → `pii_masked+internal_only`；② 仅人数 / 车流量 / 目标数量聚合 + k≥10 → `aggregated_safe+open` |

#### 3.2.3 统一入口

```python
def classify_sensitivity(
    *,
    data_type: str,
    evidence_unit: dict,
    k_threshold: int = K_THRESHOLD_AGGREGATED_SAFE,
) -> tuple[str, str]:
    """根据 data_type 与 evidence_unit 字段保守预标。

    返回 (sensitivity_level, access_policy)。未登记 data_type 抛 ValueError。
    `evidence_unit` 至少应含 `text` / `features`;缺字段按 "无信号" 处理,
    走该 data_type 默认级别。
    """
```

实现要点：

- **保守原则**：判定不确定时**升一档**而非降级。
- **不记原值**：判定基元只读，不复制敏感原值到日志或返回值。
- **`k_threshold` 参数化**：方便测试与未来按场景调档。

### 3.3 6 类 adapter 改造

`adapters.py` 中以下 6 个 adapter（按 data_type 对应），构造 `evidence_unit` 时
把现有硬编码默认 → 改为调用 `classify_sensitivity`：

| data_type | adapter | 当前默认 | 改造后 |
|---|---|---|---|
| `gazetteer` | `adapt_road_traffic_hit`（task.md §6.3 既有实现） | 硬编码 | 改 classify |
| `telecom` | `adapt_telecom_hit` | `pii_masked` 硬编码 | 改 classify |
| `code` | `adapt_code_hit` | `pii_masked` 硬编码 | 改 classify |
| `streetview` | `adapt_streetview_hit` | `pii_masked` 硬编码 | 改 classify |
| `remote_sensing` | `adapt_remote_sensing_hit` | `aggregated_safe` 硬编码 | 改 classify |
| `surveillance` | `adapt_surveillance_hit` | `restricted` 硬编码 | 改 classify |

**本次不改的 adapter**：

- `adapt_citybench_hit` (data_type=spatiotemporal_trajectory)
- `adapt_network_traffic_hit` (data_type=netflow)
- `adapt_policy_hit` (data_type=policy)
- `adapt_traffic_flow_hit` (data_type=traffic_flow) —— 师兄未给规则，待下一版

以上 4 个行为保持不变，避免回归。`adapt_road_traffic` 虽属 task.md §6 原 4
类，但它的输出 data_type 是 `gazetteer`，包含在本次师兄给出的 6 类规则范围内，
因此本次改造。

### 3.4 测试

新增 `tests/test_sensitivity_rules.py`，覆盖：

- 6 类 × {默认 / 升级触发 / 降级触发} = 18 例基础
- 边界：telecom 聚合但 k=8 → 不降级；street 仅目标数 + 含精确位置 → 升 restricted；
  code `_marked_public=True` 但仍含 token → 升 restricted（保守原则验证）
- `surveillance` 双降级路径
- 未登记 data_type → ValueError

合计 **≥ 25 unit**。同时扩展 `tests/test_adapters.py` 中 6 类 adapter 的现有
单测：覆盖调用 classify 后的级别变化 + 校验 §7 仍过。

## 4. Section 2 —— audit_sink 字段扩展 + 默认 JSONL 落盘

### 4.1 `RetrievalMiddleware.call` 入参扩展

`middleware.py` 中 `RetrievalMiddleware.call` 当前签名：

```python
def call(self, envelope, *, retrieve_fn, user_id=None) -> dict: ...
```

扩展为：

```python
def call(
    self,
    envelope,
    *,
    retrieve_fn,
    user_id: str | None = None,
    gate: str | None = None,             # InputGate / ContextGate / OutputGate
    scene: str | None = None,            # self_use / internal_org / cross_org / public_release / research_anon
    policy_version: str | None = None,
    detector_version: str | None = None,
    evidence_actions: list[dict] | None = None,
) -> dict: ...
```

所有新字段**可选**，缺省视为 `None` 不写入审计。完全向后兼容。

`data_type` 不入参 —— 从 `envelope.input.parameters.data_type` 自动抽取（task.md
§3.2 已规定该字段必填，retrieval_protocol 已校验）。

### 4.2 audit record 字段补全

`_emit_audit` 当前字段：

```
ts / request_id / user_id / skill_name / scenario / cache_hit /
sensitivity_distribution / sensitive_hit_count / filters
```

补全后字段（追加，不替换）：

```
gate
scene
data_type
policy_version
detector_version
evidence_actions[]
```

其中 `evidence_actions[]` 每条结构（新增 `build_evidence_action` 构造器 +
`validate_evidence_action` 校验器到 `errors.py` 或新建 `audit.py`）：

```python
@dataclass(frozen=True)
class EvidenceAction:
    evidence_id: str
    action: str                # allow / warn / desensitize / aggregate / rewrite / filter / refuse / manual_review
    action_status: str         # applied / pending / failed
    triggered_violation_types: list[str]   # 违规分类编码
    risk_locations: list[dict]             # 每条 {field_path: str, risk_type: str}; 禁含原值
    reason_code: str           # struct_id_detected / geo_loc_with_object_time / re_identify_combo_risk / ...
    sensitivity_before: str    # open / aggregated_safe / pii_masked / restricted
    sensitivity_after: str
```

枚举常量在新建模块 `audit.py` 集中登记（与 `errors.py` 风格一致）。

### 4.3 风险值脱敏护栏

`build_evidence_action` / `validate_evidence_action` 必须在写入前断言：

- `risk_locations[*]` 只含 `field_path` 与 `risk_type` 两个键，**任何**其它键
  视为可能漏敏，直接拒绝。
- 任一字段的字符串值长度 > 128 字符 → 拒绝（防误塞 evidence 原文）。
- `evidence_id` / `field_path` 不接受空字符串。

校验函数返回错误信息列表（与既有 validate_* 函数风格一致）。

### 4.4 默认 sink：复用 `JsonlSink`

```python
mw = RetrievalMiddleware(
    cache=LRUCache(...),
    log_sink=JsonlSink("logs/retrieval.log.jsonl"),
    audit_sink=JsonlSink("logs/retrieval.audit.jsonl").emit,  # 默认 JSONL
)
```

约定：

- `JsonlSink.emit(record)` 已实现，签名匹配 `AuditSink = Callable[[dict], None]`，
  直接复用；落盘失败吞掉、不阻塞。
- 文档中给出 ES sink 接入示意（合规组实现）：实现 `Callable[[dict], None]`，
  内部写 `bulk` 即可。

### 4.5 测试

新增 `tests/test_audit.py`，覆盖：

- 字段齐全：扩展入参全部正确写入 audit record
- 缺省入参：`gate=None` 等不写入
- `build_evidence_action` 正反例 ≥ 6
- 风险值脱敏护栏：`risk_locations` 含原值 / 含第三键 / 超长字符串 → 拒绝
- `JsonlSink` 落盘后可逐行 JSON 解析
- 自定义 audit sink 抛异常 → 主路径不破

扩展 `tests/test_middleware.py`：扩展入参向后兼容（旧调用零修改通过）。

合计 **≥ 12 unit**。

## 5. 推后内容（下分支）

仅记录意图，本次不实现：

- **Planner stdlib** (`planner.py`)：`RetrievalTask` / `Plan` / `split_budget` /
  `build_plan`。
- **Aggregator stdlib** (`aggregator.py`)：默认 dedup/sort/clip 策略 +
  `AggregatorHooks` 三个 hook + 裁剪追加 `E_OUT_OF_BUDGET`。
- **LangGraph middleware 接入**：`PlannerMiddleware`（before_model 拆子问题）+
  `AggregatorMiddleware`（after_model 聚合 retrieve 型 SkillResult）。挂在
  `TodoListMiddleware` 之后、`MemoryMiddleware` 之前，由
  `config.configurable.retrieval_planning_enabled`（默认 False）开关。

## 6. 向后兼容

| 项 | 影响 |
|---|---|
| `SKILL.md` / `Skill` / `SkillResponse` | 不动 |
| `adapt_citybench / network_traffic / policy / traffic_flow_*` | 不动 |
| 6 类受改 adapter (`gazetteer` 走 `adapt_road_traffic`、`telecom` / `code` / `streetview` / `remote_sensing` / `surveillance`) | 默认级别与 v1.1 现有硬编码一致；含敏感字段时**升档**，纯聚合 + k≥10 时**降档** —— 行为对老调用者更严或更松均可解释；现有 `tests/test_adapters.py` 中针对这 6 类的级别断言需同步更新 |
| `RetrievalMiddleware.call` 旧调用 | 新增字段全可选，旧调用零修改通过 |
| `_emit_audit` 字段 | 仅**追加**，不动既有字段名与语义；旧 sink 收到的 record 多几个键不影响 |
| `JsonlSink` | 现有用法不变 |

## 7. 测试与验证策略

- 全部测试用 Python `unittest`，与现有 retrieval_protocol 测试风格一致。
- 重跑命令：
  ```bash
  cd skills/_shared && python3 -m unittest discover -s retrieval_protocol/tests -t . -v
  ```
- 落地完成前：
  - retrieval_protocol 测试 ≥ 当前 182 + 新增 ≥ 37 = **≥ 219 个 unittest 全绿**；
  - `backend tests` 不受影响（本次不动 backend）；
  - `tests/test_harness_boundary.py` 不受影响（本次不动 backend）。

## 8. 开放问题

- `_has_struct_id` 等启发式判定基元用**保守正则**（如手机号 `1\d{10}`、身份证
  `\d{17}[\dXx]`），命中率与漏报率第一阶段够用即可；后续根据真实数据集回归
  迭代。该判定不发生在主推理路径，可接受少量误升档。
- `k_threshold=10` 暂走默认；待师兄给出按 scene 调档的细则（如
  `public_release` 场景 k≥30）后再做 scene-aware 版本。
- `triggered_violation_types` 的取值表合规组未给最终版；本次按 **空数组**
  允许 + 字段格式校验，待合规组下发后约束枚举。

## 9. 实施顺序

1. `sensitivity_rules.py` + 单测（`test_sensitivity_rules.py`）
2. `adapters.py` 6 类改造 + 扩展现有 `test_adapters.py`
3. `audit.py`（新建：`EvidenceAction` + `build_evidence_action` +
   `validate_evidence_action` + 枚举常量）+ 单测（`test_audit.py`）
4. `middleware.py`：`call` 扩展入参 + `_emit_audit` 字段补全 + 扩展
   `test_middleware.py`
5. `__init__.py` 公开新 API
6. `README.md` 更新（新章节：敏感度落档 + audit 字段）
7. 全量测试矩阵全绿后分步 commit

## 10. 不做的事（明确 YAGNI）

- 不动 `SKILL.md` frontmatter / `Skill` dataclass / `SkillResponse`。
- 不引入 Planner / Aggregator / LangGraph middleware（推下分支）。
- 不引入第三方 token 估计器、tiktoken、ES 客户端等任何非 stdlib 依赖。
- 不修改 task.md 协议设计（v1.1 已对齐反馈②的协议侧）。
- 不重写或合并老 4 类 adapter（保持回归安全；如需统一另开 issue）。
- 不在审计日志中写入任何敏感原值；只写 `field_path` + `risk_type`。
