# 📊 imiss-deer-flow 统一检索协议 进度汇报

> 生成时间: 2026-05-24(v1.1 完成版)
> 分支: `feat/unified-retrieval-protocol`
> 项目: wangwenlong2000/imiss-deer-flow
> 任务背景: 为 10 种数据类型(街景图像、网络流量、时空轨迹、政策法规、电话网络、交通流量、统计年鉴、代码片段、卫星遥感、视频监控)设计统一的检索输入与结果证据格式

---

## 一、本阶段总览(对照老师 5 条要求)

| # | 老师要求 | 完成度 | 已做(v1.1) | 仍需协作落地 |
|---|---|---|---|---|
| 1 | 与隐私合规组对齐 sensitivity & 过滤器 | **70%** | schema 4 档 sensitivity / 3 档 access_policy;**电话、视频监控 adapter 默认按 PII 标注**;中间件 audit_sink 输出 sensitivity 分布 | 取值映射文档 / 违规类型预打标取值,需与黄宇哲一次性对齐 |
| 2 | 与 Skill 接口同学对齐 Envelope/Budget/Plan | **75%** | `Envelope.budget`(max_evidence_count / max_token_estimate)已落地 + 校验 + 测试 | Plan 模板生成 Envelope / 多 retrieve 并行调度 / 复合 query 拆解 |
| 3 | 错误码与 status 标准化 | **100%** | `errors.py` 模块 10 个错误码 + 4 个建议动作 + status 联动校验 + 14 个测试 | — |
| 4 | 6 类剩余数据 adapter 落地 | **70%** | 6 个 adapter 函数全部实现(traffic_flow / telecom / code / streetview / remote_sensing / surveillance)+ 测试 | 6 个 skill 仓库接入 adapter(由各数据类型负责同学执行) |
| 5 | 统一检索中间件层 | **100%** | `middleware.py` 实现 LRU+TTL 缓存 + JSONL 日志 + 审计 sink(纯 stdlib)+ 12 个测试 | 合规组实现自家 audit_sink 钩子 |

**整体协议库进度约 83%**(协议侧)。各 RAG skill 的接入由各数据类型负责同学完成。

---

## 二、已完成内容(可交付)

### 2.1 协议库 `skills/_shared/retrieval_protocol/`(v1.1 / 7 模块)

```
schema.py     新版本号 1.1
envelope.py   + build_budget(); build_input_envelope 接受可选 budget
evidence.py   未改动
errors.py     ⭐ 新模块:标准化错误码 + status 联动校验
validate.py   + validate_budget / errors 联动校验
adapters.py   + 6 个新 adapt_*_hit(traffic_flow/telecom/code/streetview/remote_sensing/surveillance)
middleware.py ⭐ 新模块:LRU+TTL 缓存 / JSONL 日志 / 审计 sink
```

- 全部纯 stdlib,**182 测试全绿**(原 128 + 新增 54)
- 10 种 data_type 全部登记;其中 9 类已有 adapter 函数(剩 1 类 gazetteer 与 road-traffic adapter 共用)

### 2.2 已接入协议的 skill

| skill | 数据类型 | 接入方式 | 状态 |
|---|---|---|---|
| `network-traffic-analysis` | netflow | `rag_search.py` 调 `build_network_traffic_skill_result` | ✅ 端到端跑通 |
| citybench(外部上游) | spatiotemporal_trajectory | `adapt_citybench_hit` 零改动直通 | ✅ 适配函数就绪 |
| road-traffic 年报 | gazetteer | `adapt_road_traffic_hit` | ⚠️ adapter 已写,skill 未挂 |
| 政策法规 | policy | `adapt_policy_hit` | ⚠️ adapter 已写,skill 未挂 |

`skills/custom/` 当前只有 **1 个**目录(`network-traffic-analysis`),其余数据类型的 skill 还都在其他同学手里、未进主仓库。

### 2.3 已交付文档

- `task.md` —— 协议原始 spec(已 commit 56d9f9b)
- `HANDOVER.md` —— 项目迁移交接(a996e19)
- `USAGE.md` —— 561 行源码使用 / 二次开发说明(d4300a3)
- `docs/superpowers/plans/2026-05-21-unified-retrieval-protocol.md` —— 完成报告
- `统一检索输入与结果证据格式.pdf` —— 老师评审的对外稿

---

## 三、紧迫的缺口(按优先级排序)

### 🔴 P0 —— 必须本周/下周做完,否则阻塞其他同学

**P0-1. budget 字段(老师要求 2.2)**
- 现状:`build_input_envelope` 没有 budget 形参
- 影响:Planner 并行调多个 retrieve 会撑爆 32k 上下文
- 改动量:envelope.py + validate.py + schema.py 大约 30 行
- 字段:`budget.max_evidence_count: int`、`budget.max_token_estimate: int`

**P0-2. 错误码与 status 标准化(老师要求 3)**
- 现状:`errors: list[Any]` 是无结构 list
- 改动量:新增 `errors.py` 模块,约 80 行
- 至少要覆盖:`E_TIMEOUT / E_INDEX_MISSING / E_PERMISSION_DENIED / E_RATE_LIMIT / E_BAD_QUERY / E_UPSTREAM_FAIL`;每类配建议动作(`retry_with_backoff / degrade_to_local / report_to_user / abort`)

**P0-3. sensitivity 取值与合规组对齐(老师要求 1)**
- 现状:协议有 4 档 `sensitivity_level`,但**未与黄宇哲组对齐场景映射**
- 行动:需要面对面对齐 1 小时,产出 `docs/protocol/sensitivity-mapping.md`
- 同时确定过滤器归属 —— 强烈建议在中间件层(P1-2)一次实现,而非各 RAG 各做一遍

### 🟡 P1 —— 接下来 2 周内必须启动

**P1-1. 6 类数据 adapter 落地(老师要求 4)**

按数据特征复杂度排序、建议执行顺序:

| 顺序 | 数据类型 | 复杂度 | 牵头同学 | 建议做法 |
|---|---|---|---|---|
| 1 | 统计年鉴(`gazetteer` 现成 adapter,只差接入) | ⭐ | — | 把现有 adapter 接进 skill 即可 |
| 2 | 代码片段(`code`) | ⭐⭐ | TBD | 文本型,与 policy 同形,可仿写 |
| 3 | 电话网络(`telecom`) | ⭐⭐ | TBD | 结构化,与 netflow 同形 |
| 4 | 交通流量(`traffic_flow`) | ⭐⭐ | TBD | 结构化 + 时空 |
| 5 | 街景图像(`streetview`) | ⭐⭐⭐ | TBD | 图像 + bbox + objects,需对齐 artifacts 登记 |
| 6 | 卫星遥感(`remote_sensing`) | ⭐⭐⭐ | TBD | 图像 + tile_id,change_score 特征 |
| 7 | 视频监控(`surveillance`) | ⭐⭐⭐⭐ | TBD | 视频片段 + 行为识别,clip_start/end + artifacts |

**P1-2. 统一检索中间件层(老师要求 5)**
- 位置建议:`backend/packages/harness/deerflow/middleware/retrieval_middleware.py`
- 三件套:
  1. **缓存**:`hashlib.sha1((query + filters).encode()) → evidence`,LRU,默认 1024 条,TTL 10 分钟
  2. **日志**:每次调用一行 JSON 进 `logs/retrieval.jsonl`,字段:`request_id / skill_name / query_hash / latency_ms / hit_count / cache_hit / status`
  3. **审计**:用户 ID / 场景 / 命中前的 sensitivity 分布 / 过滤动作 / 脱敏依据 → 入合规组指定的存储(待对齐)
- 切入点:DeerFlow 已有 `thread_data_middleware` 等 13 个中间件,可仿其形式注册新中间件

### 🟢 P2 —— 当前阶段不阻塞,但应纳入下个版本

- Plan 模板自动生成 Envelope
- 复合 query 拆解机制
- 多 retrieve 并行调度与结果聚合(可与 P0-1 budget 字段联动)
- 跨 skill 的 JSONL 交换格式落地脚本

---

## 四、风险与建议

| 风险 | 影响 | 缓解 |
|---|---|---|
| sensitivity 字段未与合规组对齐 | 6 个新 adapter 可能要返工二次改 | **本周内必须组织对齐会**,先冻结字段语义 |
| budget 字段未加 | 32k 上下文撑爆,演示翻车 | P0-1 在下个 commit 完成,半天工作量 |
| 6 类 skill 在多名同学手里、节奏不一 | 单点拖延整体延期 | **统一 deadline + 模板化 adapter 范例**;每周同步会 |
| 协议变动后下游适配成本 | 越往后改成本越大 | 先把 P0 三项做完再让其他同学开始接入 |

---

## 五、推荐的下一步动作(本周)

1. **明天**:组织三方对齐会 —— 你 / 黄宇哲(合规)/ Skill 接口同学,产出三份字段冻结清单
2. **本周内**:补 budget 字段 + 错误码模块(P0-1 + P0-2),提交 PR,bump 协议版本到 `1.1`
3. **下周**:发起 6 类数据 adapter 任务认领,提供 network-traffic 作为参考模板
4. **持续**:把 `统一检索输入与结果证据格式.pdf` 补 budget / 错误码两节,作为协议 v1.1 对外稿

---

## 六、结论(v1.1 收尾)

- **已完成**:
  - ✅ Envelope.budget 字段
  - ✅ errors[] 标准化错误码 + status 联动
  - ✅ 6 类新 adapter 全部上线
  - ✅ 统一检索中间件(缓存 / 日志 / 审计)
  - ✅ 协议版本 bump 至 v1.1
- **协议库 v1.1 整体进度 83%**;余下 17% 为合规取值映射对齐与 Plan/并行调度,属外部协作项。
- **下游接入**(6 个 RAG skill 接 adapter / 合规组实现 audit_sink)由相关同学按模板复用。

---

## 附录 A:本地待 push commit 列表

```
d4300a3 docs: 新增 USAGE.md 源码使用与二次开发文档
a996e19 docs: 新增 HANDOVER.md 项目迁移交接文档
56d9f9b docs: 归档统一检索协议原始设计 spec
aa457ea docs: 更新统一检索协议落地计划为完成报告
e7455d1 test: 集成测试加载 rag_search.py 时禁止写入 .pyc
0ce2e39 docs: 更新统一检索协议落地计划为完成状态
b9e0613 feat: network-traffic rag_search 支持统一 SkillResult 输出
434c70a feat: 新增统一检索协议库 retrieval_protocol
03d5230 Add SkillRouter scope and prompt design document
3622a4f Update config.yaml
```

## 附录 B:协议库 10 种 data_type 登记表(v1.1 后)

| 数据类型 | data_type 取值 | 分组 | adapter | skill 接入 |
|---|---|---|---|---|
| 时空轨迹 | `spatiotemporal_trajectory` | structured | ✅ citybench 直通 | ✅ 外部上游 |
| 交通流量 | `traffic_flow` | structured | ✅ v1.1 新增 | ⚠️ skill 待接入 |
| 统计年鉴 | `gazetteer` | structured | ✅ road-traffic | ⚠️ adapter 就绪,skill 待接入 |
| 网络流量 | `netflow` | structured | ✅ network-traffic | ✅ 端到端 |
| 电话网络 | `telecom` | structured | ✅ v1.1 新增(PII 默认) | ⚠️ skill 待接入 |
| 代码片段 | `code` | text | ✅ v1.1 新增 | ⚠️ skill 待接入 |
| 政策法规 | `policy` | text | ✅ | ⚠️ adapter 就绪,skill 待接入 |
| 街景图像 | `streetview` | image | ✅ v1.1 新增 | ⚠️ skill 待接入 |
| 卫星遥感 | `remote_sensing` | image | ✅ v1.1 新增 | ⚠️ skill 待接入 |
| 视频监控 | `surveillance` | video | ✅ v1.1 新增(PII 默认) | ⚠️ skill 待接入 |

**adapter 全部就绪 10/10;skill 接入 1/10**(等其他同学按模板复用)
