# retrieval_protocol —— 统一检索输入与结果证据格式

`task.md`《统一检索输入与结果证据格式》的参考实现。把检索请求统一成 **Input
Envelope**（task.md §3），把检索结果统一成 **SkillResult**（task.md §4，每条命中
是 `retrieval` 型 evidence，载荷为兼容 citybench 的 `evidence_unit`），并提供
§7 融合前校验器与 §6 兼容映射适配器。

**仅依赖 Python 标准库**，可直接拷贝进任意检索 skill 的运行环境。

## 目录结构

| 文件 | 对应 task.md | 内容 |
|---|---|---|
| `schema.py` | §2 / §4.4 | `DATA_TYPES`（10 类登记取值）、`FEATURES_REGISTRY`、各类枚举 |
| `envelope.py` | §3 | Input Envelope 构造器 |
| `evidence.py` | §4 | `evidence_unit` / evidence wrapper / SkillResult 构造器 |
| `validate.py` | §7 | 融合前十条校验规则 |
| `adapters.py` | §6 | citybench / network-traffic / road-traffic / policy 兼容映射 |
| `tests/` | §7 测试清单 | `unittest` 用例，零依赖运行 |

## 快速上手

### 1. 构造统一检索输入（task.md §3）

```python
from retrieval_protocol import (
    build_input_envelope, build_filters, build_retrieval_params,
    build_time_range_absolute,
)

envelope = build_input_envelope(
    skill_name="citybench-rag-search",
    scenario="spatiotemporal_trajectory",   # SkillRouter 的 scene，不是 data_type 路由键
    capability="evidence_search",
    query="上海早高峰陆家嘴交通流量异常",
    data_type="traffic_flow",               # 数据类型标签，用于结果分桶 / 校验
    retrieval=build_retrieval_params(strategy="hybrid", rerank=True),
    filters=build_filters(
        city="Shanghai",
        time_range=build_time_range_absolute(
            start="2024-03-01T00:00:00+08:00", end="2024-03-31T23:59:59+08:00"),
        anomaly_only=True,
    ),
)
```

### 2. 构造统一结果证据（task.md §4）

```python
from retrieval_protocol import (
    build_evidence_unit, build_geo_scope, build_retrieval_evidence,
    build_skill_result, build_summary, build_key_metric,
)

unit = build_evidence_unit(
    evidence_id="traj_ev_20120601_0700_beijing_wx4g0",
    data_type="spatiotemporal_trajectory",
    text="2012年6月1日早高峰，Beijing(geohash:wx4g0)签到944次，较前周上升146.8%。",
    source_id="citybench_checkins_beijing",
    geo_scope=build_geo_scope(city="Beijing", geohash="wx4g0", landmark="国贸-CBD核心区"),
    features={"checkin_count": 944, "wow_change_pct": 146.78, "anomaly_flag": True},
)

# 检索分由 evidence wrapper 携带，不进 evidence_unit 本体。
wrapper = build_retrieval_evidence(
    evidence_ref="e-001", rank=1, score=0.92,
    method="bm25_vector_rrf", rrf_k=60, payload=unit,
)

skill_result = build_skill_result(
    skill_name="citybench-rag-search",
    scenario="spatiotemporal_trajectory",
    capability="evidence_search",
    summary=build_summary(
        title="陆家嘴早高峰交通异常检索", overview="命中 1 条证据。",
        key_metrics=[build_key_metric(name="result_count", value=1)]),
    evidence=[wrapper],
)
```

### 3. 融合前校验（task.md §7）

```python
from retrieval_protocol import validate_skill_result, validate_evidence, is_valid_evidence

errors = validate_skill_result(skill_result)   # 空列表 = 合规
assert errors == [], errors

if not is_valid_evidence(wrapper):
    ...  # 丢弃或修复
```

校验函数一览：

| 函数 | 校验对象 | 覆盖规则 |
|---|---|---|
| `validate_evidence(wrapper)` | 一条 evidence wrapper + payload | 规则 1–8 |
| `validate_evidence_unit(payload)` | 一个 evidence_unit | 规则 2、4、5、6、7、8 |
| `validate_evidence_list(wrappers)` | 一组 evidence wrapper | 规则 1–8 + 3（唯一性） |
| `validate_skill_result(sr)` | 完整 SkillResult | 规则 9、8、3 + 逐条 1–8 |
| `validate_jsonl_lines(text_or_list)` | 跨 skill 交换的 JSONL | 规则 3 + 逐条 |
| `validate_input_envelope(env)` | Input Envelope | task.md §3.2 / §3.3 |

> 规则 10（路由经 SkillRouter，不引入 `data_type` 路由分支）是设计约束，无逐条
> 数据校验项。规则 6 / 7 依赖语义判断，采用「字段给出即从严校验」策略。

## §6 兼容映射适配器

把已落地实现的**原生命中**转换成标准 evidence wrapper：

```python
from retrieval_protocol import (
    adapt_citybench_result,        # §6.1 时空轨迹（source 零改动直通）
    adapt_network_traffic_result,  # §6.2 网络流量（薄映射，相对时间）
    adapt_road_traffic_result,     # §6.3 交通流量年报 RAG（gazetteer）
    adapt_policy_result,           # §6.4 政策法规 RAG（policy）
    build_network_traffic_skill_result,  # network-traffic 整份结果 → SkillResult
)

wrappers = adapt_network_traffic_result(rag_search_result["hits"])
skill_result = build_network_traffic_skill_result(rag_search_result)
```

## 在检索 skill 中接入

skill 脚本把本包父目录加入 `sys.path` 即可 import（按脚本所在层级调整 `parents[N]`）：

```python
import sys
from pathlib import Path

# 例：skills/custom/<skill>/scripts/x.py —— parents[3] 即 skills/
_SHARED = Path(__file__).resolve().parents[3] / "_shared"
if str(_SHARED) not in sys.path:
    sys.path.insert(0, str(_SHARED))

from retrieval_protocol import build_network_traffic_skill_result
```

`network-traffic-analysis/scripts/rag_search.py` 已据此接入：`--format skillresult`
会输出符合本协议的 SkillResult JSON（`--format text` / `json` 行为不变）。

## 运行测试

零依赖，标准库 `unittest` 即可：

```bash
cd skills/_shared
python3 -m unittest discover -s retrieval_protocol/tests -t . -v
```
