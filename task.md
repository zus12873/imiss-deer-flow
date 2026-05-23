# 统一检索输入与结果证据格式

---

## 1. 设计目标与覆盖范围

- **统一可融合**：不同检索 skill 的命中结果落到同一个 `evidence_unit` 形状，`fuse_spatial_evidence` 等下游可直接按 `evidence_id` 去重、按检索分排序、按 `data_type` 分桶。
- **不污染已实现**：citybench 现有 `sample_evidence.jsonl` 不改字段即合规；network-traffic / road-traffic / policy 只需做一层映射。
- **可扩展**：新增数据类型时只注册新的 `data_type` 取值与 `meta.features` 子字段，外层信封不动。

覆盖 10 类城市数据：时空轨迹、交通流量、统计年鉴、网络流量、电话网络、代码片段、政策法规、街景图像、卫星遥感、视频监控。当前已有落地样例：时空轨迹（citybench-rag-search）、网络流量（network-traffic-analysis）、交通流量年报（road-traffic-analysis RAG）、政策法规（policies-regulations RAG）。

---

## 2. 数据类型分组

分组目的是让同组数据复用同一套召回逻辑，**与 SkillRouter 的 `scenes` 无关**。

| 大类 | data_type 取值 | 物理形态 | 召回方式 |
|---|---|---|---|
| 结构化/表格 | `spatiotemporal_trajectory` `traffic_flow` `gazetteer` `netflow` `telecom` | 行列式，含时间戳、数值指标、实体 ID、空间字段 | 结构化过滤 + BM25 文本字段 + 异常分排序；netflow 走相对时间 |
| 文本 | `code` `policy` | 长文本/结构化文档 | BM25 + 向量 + RRF；code 额外支持 AST/符号匹配 |
| 图像 | `streetview` `remote_sensing` | 单图 + 元数据 | CLIP 向量 + 检测/分类；遥感叠加瓦片索引与变化检测 |
| 视频 | `surveillance` | clip / 关键帧 | 关键帧抽取 + CLIP 向量 + 行为识别；证据粒度 5–15s clip |

---

## 3. 统一检索输入

### 3.1 完整信封

检索 skill 接收的就是标准 Input Envelope。检索专用内容只占用 `input.parameters` 与 `input.filters`：

```json
{
  "schema_version": "1.0",
  "request_id": "uuid-v4",
  "skill_name": "citybench-rag-search",
  "scenario": "spatiotemporal_trajectory",
  "capability": "evidence_search",
  "input": {
    "data_sources": [
      {
        "source_id": "user_upload_1",
        "source_type": "local_file",
        "uri": "/mnt/user-data/outputs/desensitized/evidence.jsonl",
        "media_type": "application/jsonl",
        "data_type": "jsonl",
        "role": "primary"
      }
    ],
    "parameters": {
      "query": "上海早高峰陆家嘴交通流量异常",
      "data_type": "traffic_flow",
      "top_k": 10,
      "mode": "auto",
      "retrieval": {
        "strategy": "hybrid",
        "rerank": true,
        "score_threshold": 0.0
      }
    },
    "filters": {
      "city": "Shanghai",
      "time_range": {
        "mode": "absolute",
        "start": "2024-03-01T00:00:00+08:00",
        "end": "2024-03-31T23:59:59+08:00",
        "timezone": "Asia/Shanghai"
      },
      "geohash": "wtw3s",
      "bbox": null,
      "anomaly_only": true,
      "where": {
        "congestion_level": ["heavy", "severe"]
      }
    },
    "context": {}
  }
}
```

### 3.2 字段定义

| 路径 | 必填 | 适用 | 说明 |
|---|---|---|---|
| `schema_version` `request_id` `skill_name` `scenario` `capability` | 是 | 全部 | Input Envelope 固定头，含义见全队规范 §5.1 |
| `input.parameters.query` | 是 | 全部 | 用户自然语言检索意图，BM25/向量/RRF 的主查询 |
| `input.parameters.data_type` | 是 | 全部 | 数据类型标签（用于结果分桶/校验），**不是路由键** |
| `input.parameters.top_k` | 否 | 全部 | 返回证据条数，默认 10 |
| `input.parameters.mode` | 否 | 全部 | `auto`/`es`/`local`/`demo`，对应 citybench 三档降级 |
| `input.parameters.retrieval.strategy` | 否 | 全部 | `bm25`/`vector`/`hybrid`，默认 `hybrid` |
| `input.parameters.retrieval.rerank` | 否 | 全部 | 是否走 Reranker 精排 |
| `input.parameters.retrieval.score_threshold` | 否 | 全部 | 最低分阈值，低于此分丢弃 |
| `input.filters.city` | 否 | 时空类 | 城市过滤，可由地名/geohash 反查 |
| `input.filters.time_range` | 否 | 时序类 | 见 §3.3 时间语义 |
| `input.filters.geohash` | 否 | 时空类 | geohash 前缀过滤，默认 5 位粗锚 |
| `input.filters.bbox` | 否 | 时空/遥感 | `[min_lon,min_lat,max_lon,max_lat]`，补 geohash 表达不了的矩形 |
| `input.filters.anomaly_only` | 否 | 有异常字段的类型 | 只返回 `meta.features.anomaly_flag=true` 的证据 |
| `input.filters.where` | 否 | 全部 | 类型特化结构化过滤；放不进通用字段的都进这里（对应 network-traffic 的 `filters.where`） |
| `input.data_sources[]` | 否 | local 模式 | 本地 evidence JSONL 路径，对应 citybench `--local-file` |

> ⚠️ type-specific 过滤统一进 `input.filters.where`，与 network-traffic 已实现的 `filters.where` 对齐，避免两套过滤约定。

### 3.3 时间语义

`time_range.mode` 必填，取值二选一：

- `absolute`：真实墙钟时间。字段 `start`/`end`（ISO 8601）+ `timezone`。时空轨迹、交通流量、政策、视频用此。
- `relative`：相对抓包/采集起点。字段 `start_offset_s`/`end_offset_s`（整数秒）。**network-traffic 必须用此**，对应其 `time_is_relative=true`、`relative_time_s`、桶标签 `t+0s` / `t+3600s`。相对时间数据**禁止**被解释成真实日期。

```json
// 网络流量（相对时间）
"time_range": { "mode": "relative", "start_offset_s": 0, "end_offset_s": 3600 }
```

### 3.4 不同查询示例

```json
// 视频监控
{"input":{"parameters":{"query":"西二旗到中关村下午6点附近奔跑人群","data_type":"surveillance","top_k":8},
 "filters":{"city":"Beijing","time_range":{"mode":"absolute","start":"2024-03-15T18:00:00+08:00","end":"2024-03-15T19:00:00+08:00"},
 "where":{"objects.label":"person","objects.behavior":"running","camera_region":["西二旗","中关村"]}}}}
```

```json
// 代码片段（无时空字段，不伪造 city/time）
{"input":{"parameters":{"query":"_load_landmarks 调用位置","data_type":"code","top_k":20},
 "filters":{"where":{"lang":"python","ast_node_type":"function_call"}}}}
```

非时空数据不需要填 `city/time_range/geohash`；时空数据保留全部空间时间过滤能力——这正是统一的价值。

---

## 4. 统一结果证据

### 4.1 在 SkillResult 中的位置

检索 skill 的最终输出仍是标准 SkillResult。每条命中是 `result.evidence[]` 中一条 `retrieval` 型 evidence，其 `payload` 即 `evidence_unit`：

```json
{
  "schema_version": "1.0",
  "request_id": "uuid-v4",
  "skill_name": "citybench-rag-search",
  "scenario": "spatiotemporal_trajectory",
  "capability": "evidence_search",
  "status": "success",
  "result": {
    "summary": {
      "title": "陆家嘴早高峰交通异常检索",
      "overview": "命中 10 条证据，其中 4 条标记异常。",
      "key_metrics": [{"name": "result_count", "value": 10}]
    },
    "findings": [],
    "evidence": [
      {
        "evidence_ref": "e-001",
        "type": "retrieval",
        "rank": 1,
        "score": 0.92,
        "retrieval": {
          "method": "bm25_vector_rrf",
          "raw_scores": {"bm25_rank": 1, "knn_rank": 2},
          "rrf_k": 60,
          "matched_fields": ["text", "meta.features.top_categories"]
        },
        "payload": { /* ↓ evidence_unit ↓ */ }
      }
    ],
    "artifacts": [
      {"artifact_id": "a-001", "type": "file", "title": "热力图",
       "uri": "/mnt/user-data/outputs/heatmap.png", "media_type": "image/png"}
    ]
  },
  "diagnostics": {
    "data_quality": {"channel_a_filtered": 84, "channel_b_bm25_hits": 31},
    "runtime": {"mode": "demo", "duration_ms": 142}
  },
  "errors": []
}
```

> 约定：检索分 `score`/`rank`/`method` 放在 **evidence wrapper**（与 citybench `search.py` 的 `{"id","rrf_score","source"}` 一一对应：`evidence_ref↔id`、`score↔rrf_score`、`payload↔source`），**不进 `evidence_unit` 本体**。citybench 现有 `sample_evidence.jsonl` 因此无需改动字段即合规。

### 4.2 `evidence_unit` 标准结构

与 citybench 现有 JSONL **完全兼容**，新增字段全部可选：

```json
{
  "schema_version": "1.0",
  "evidence_id": "traj_ev_20120601_0700_beijing_wx4g0",
  "data_type": "spatiotemporal_trajectory",
  "text": "2012年6月1日早高峰(7:00-9:00)，Beijing(geohash:wx4g0)区域，签到944次，活跃用户563人，较前周上升146.8%，存在显著异常波动。",
  "meta": {
    "source_id": "citybench_checkins_beijing",
    "source_path": "data_lake/Beijing_filtered_checkins.csv",
    "time_range": {
      "mode": "absolute",
      "start": "2012-06-01T07:00:00",
      "end": "2012-06-01T09:00:00",
      "timezone": "Asia/Shanghai"
    },
    "geo_scope": {
      "city": "Beijing",
      "geohash": "wx4g0",
      "landmark": "国贸-CBD核心区",
      "district": "朝阳区",
      "lat": 39.9087,
      "lon": 116.45,
      "tags": ["CBD", "通勤目的地"]
    },
    "granularity": "hourly_district",
    "sensitivity_level": "aggregated_safe",
    "access_policy": "open",
    "locator": {},
    "features": {
      "checkin_count": 944,
      "unique_users": 563,
      "top_categories": ["便利店", "早餐店", "写字楼"],
      "wow_change_pct": 146.78,
      "anomaly_flag": true
    }
  }
}
```

### 4.3 字段定义

| 路径 | 必填 | 适用 | 说明 |
|---|---|---|---|
| `schema_version` | 建议 | 全部 | 协议版本 |
| `evidence_id` | 是 | 全部 | 稳定唯一 ID。非时空数据可用 doc_id/哈希/索引 ID，不强制日期+城市+geohash |
| `data_type` | 是 | 全部 | 数据类型标签，用于分桶/校验 |
| `text` | 是 | 全部 | 可读摘要，大模型生成报告首选读取字段 |
| `meta.source_id` | 是 | 全部 | 数据源标识，溯源用 |
| `meta.source_path` | 否 | 全部 | 原始路径 |
| `meta.time_range` | 否 | 时序类 | 含 `mode`；`absolute` 用 `start/end/timezone`，`relative` 用 `start_offset_s/end_offset_s` |
| `meta.geo_scope` | 否 | 时空类 | `city/geohash/bbox/landmark/district/lat/lon/tags`；非时空数据置 `{}` 但类型须为对象 |
| `meta.granularity` | 否 | 全部 | `hourly_district`/`flow`/`paragraph`/`clip`/`frame` 等 |
| `meta.sensitivity_level` | 隐私数据必填 | 全部 | `open`/`aggregated_safe`/`pii_masked`/`restricted` |
| `meta.access_policy` | 隐私数据必填 | 全部 | `open`/`restricted`/`internal_only` |
| `meta.locator` | 否 | 文本/代码/政策 | `file_path`/`line_start`/`line_end`/`page`/`paragraph_id`/`section` |
| `meta.features` | 是 | 全部 | 类型特化字典，新增类型只扩展此对象 |

> 检索分、附件**不进** `evidence_unit`：检索分进 §4.1 evidence wrapper；图片/热力图/视频帧进 `SkillResult.result.artifacts[]`（不要塞进 `text`）。

### 4.4 各 data_type 的 features 注册建议

| data_type | features 字段 |
|---|---|
| `spatiotemporal_trajectory` | `checkin_count` `unique_users` `top_categories` `wow_change_pct` `anomaly_flag` |
| `traffic_flow` | `flow_count` `peak_hour` `avg_speed` `congestion_level` `wow_change_pct` `anomaly_flag` |
| `gazetteer` | `metric_name` `value` `unit` `year` `region` |
| `netflow` | `src_ip` `dst_ip` `protocol` `bytes` `packets` `flow_duration` `ja3_hash` `anomaly_flag` |
| `telecom` | `call_count` `unique_contacts` `community_id` `duration_sum` |
| `code` | `doc_id` `snippet` `lang` `ast_node_type` `symbol`（定位进 `meta.locator`） |
| `policy` | `doc_id` `snippet` `policy_number` `effective_date` `issuer`（段落/页进 `meta.locator`） |
| `streetview` | `objects` `bbox` `taken_at`（图进 artifacts） |
| `remote_sensing` | `objects` `bbox` `tile_id` `taken_at` `change_score` |
| `surveillance` | `objects` `bbox` `clip_start` `clip_end` `behavior`（帧/clip 进 artifacts） |

---

## 5. 检索 → 融合 → 报告链路

1. 用户自然语言问题进入 lead agent。
2. **SkillRouter**（非本协议）按 `scenes`+`task_types` 把问题切分并路由到一个或多个检索 skill。跨类型问题被 SkillRouter 拆成多 segment。
3. 每个检索 skill 收到 §3 的 Input Envelope，执行检索。
4. 每个 skill 返回 §4 的 SkillResult；其 `result.evidence[]` 即标准化命中。
5. `fuse_spatial_evidence` 等融合 skill 读取各 SkillResult 的 evidence：按 `payload.evidence_id` 去重、按 wrapper `score` 排序、按 `payload.data_type` 分桶截断。跨 skill 交换用 JSONL，每行 = 一条 §4.1 evidence wrapper。
6. 大模型读取 `payload.text`、`payload.meta.geo_scope.landmark`、`payload.meta.features`、`payload.meta.locator` 和 `artifacts[]` 生成报告。地点优先用 `landmark`，首次出现写"业务地名(geohash)"，之后只用业务地名。

跨类型问题（"陆家嘴 3 月 15 日早高峰交通异常 + 同时段监控异常 + 相关交通管制政策"）由 SkillRouter 拆成 `traffic_flow` / `surveillance` / `policy` 三个并行检索请求，报告按证据类型分节组织。

---

## 6. 与现有实现的兼容映射

### 6.1 citybench-rag-search（时空轨迹，已落地）

- `sample_evidence.jsonl` 每条 = 合规 `evidence_unit`，**零改动**。
- `search.py` 输出 `{"id","rrf_score","source"}` → 包成 §4.1 wrapper：`id→evidence_ref`、`rrf_score→score`、`source→payload`。
- 需补：顶层 `SkillResult` 信封；`time_range.mode`；`landmark/district/lat/lon` 由 `landmarks.enrich_evidence` 在输出前注入（已有）；热力图登记进 `result.artifacts`。

### 6.2 network-traffic-analysis（已落地）

- 已是 SkillResult 原生输出，检索类结果映射：`doc_id→evidence_id`、`summary/content→text`、`dataset_name→meta.source_id`、`source_file→meta.source_path`、字段字典里的 `src_ip/dst_ip/bytes/...→meta.features`。
- 时间必须 `time_range.mode=relative`（`time_is_relative=true` 时），用 `start_offset_s/end_offset_s`，桶标签沿用 `t+3600s`。
- `geo_scope={}`（无空间属性，但保持对象类型）。

### 6.3 road-traffic 年报 RAG（已落地）

`rag_xian2024_min.py` 输出 `section_path/pages/preview/distance/rerank_score` → 映射：`preview→text`、`section_path+pages→meta.locator`、`distance/rerank_score→evidence wrapper.retrieval.raw_scores`、`data_type="gazetteer"`。

### 6.4 policies-regulations RAG（已落地）

`doc_id→evidence_id`、`text→text`（必要时裁成摘要）、`title/policy_number/page/paragraph→meta.locator`+`meta.features`、`bm25_score/vector_score→evidence wrapper.retrieval.raw_scores`、`data_type="policy"`。

---

## 7. 校验规则

融合前每条 evidence wrapper + payload 必须满足：

1. wrapper 含 `type="retrieval"`、`score`（或 `retrieval.raw_scores`）、`payload`。
2. `payload` 含 `evidence_id`、`data_type`、`text`、`meta.source_id`、`meta.features`。
3. `evidence_id` 在同一 SkillResult / 同一 JSONL 内唯一。
4. `data_type` 必须取自第 2 节登记取值，禁止临时造别名。
5. 非时空数据允许 `meta.geo_scope={}`，但必须是对象类型，不得为 `null` 或字符串。
6. 有时间属性的数据必须填 `meta.time_range.mode`，并据此填对应字段组（绝对/相对二选一）。
7. 隐私敏感数据必须填 `meta.sensitivity_level` 与 `meta.access_policy`。
8. 附件（图片/视频帧/热力图/报告文件）必须进 `SkillResult.result.artifacts[]`，禁止混进 `text` 或 `evidence_unit`。
9. 检索 skill 的机器可消费输出必须是 `SkillResult` JSON，禁止返回纯自然语言（与全队规范 §9 一致）。
10. 检索 skill 的路由仍走 SkillRouter（`scenes`+`task_types`），本协议不引入任何 `data_type` 路由分支。

---

## 8. 结论

本协议把"统一检索输入 / 统一结果证据"定义为全队 **Input Envelope** 与 **SkillResult** 两个信封的一个 RAG 剖面：检索请求 = Input Envelope（检索参数进 `input.parameters/filters`），检索结果 = SkillResult（每条命中是 `retrieval` 型 evidence，载荷为兼容 citybench 的 `evidence_unit`，检索分由 evidence wrapper 携带）。路由统一交由 SkillRouter（`scenes`+`task_types`），`data_type` 仅作数据/证据标签；时间语义按绝对/相对二选一显式声明。该剖面使 citybench、network-traffic、road-traffic、policy 四个已落地实现以无改动或薄映射方式接入，并为后续街景、遥感、视频检索提供稳定接入面。
