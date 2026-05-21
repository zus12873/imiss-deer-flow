"""与现有实现的兼容映射 —— task.md §6。

每个 ``adapt_*_hit`` 函数把一个检索 skill 的**原生命中**转换成 task.md §4.1 的
evidence wrapper（``payload`` 为 §4.2 的 ``evidence_unit``）：

- :func:`adapt_citybench_hit`        —— §6.1 时空轨迹（``source`` 已是合规 evidence_unit，零改动直通）；
- :func:`adapt_network_traffic_hit`  —— §6.2 网络流量（薄映射，相对时间）；
- :func:`adapt_road_traffic_hit`     —— §6.3 交通流量年报 RAG（gazetteer）；
- :func:`adapt_policy_hit`           —— §6.4 政策法规 RAG（policy）。

:func:`build_network_traffic_skill_result` 进一步把 ``rag_search.py`` 的整份结果
字典包成完整 SkillResult，供该 skill 直接调用（task.md §1「薄映射接入」）。

本模块仅依赖 Python 标准库。
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

from .evidence import (
    build_evidence_unit,
    build_key_metric,
    build_locator,
    build_retrieval_evidence,
    build_skill_result,
    build_summary,
)

# build_rag_docs.py 的 relative_hour_bucket 用 3600s 的小时桶；t+<n>s 标签据此还原。
_RELATIVE_BUCKET_RE = re.compile(r"^t\+(\d+(?:\.\d+)?)s$")
_RELATIVE_BUCKET_SECONDS = 3600


def _first_nonempty(*values: Any) -> str:
    """返回第一个非空字符串；都为空则返回空串。"""
    for value in values:
        if isinstance(value, str) and value.strip():
            return value
    return ""


# ---------------------------------------------------------------------------
# §6.1 citybench-rag-search（时空轨迹）
# ---------------------------------------------------------------------------


def adapt_citybench_hit(hit: dict[str, Any], *, rank: int | None = None) -> dict[str, Any]:
    """task.md §6.1：citybench ``search.py`` 的 ``{id, rrf_score, source}``。

    ``source`` 每条已是合规 ``evidence_unit``，**零改动**直通为 ``payload``：
    ``id → evidence_ref``、``rrf_score → score``、``source → payload``。
    """
    return build_retrieval_evidence(
        evidence_ref=hit.get("id") or hit.get("evidence_id") or "",
        rank=rank,
        score=hit.get("rrf_score", hit.get("score")),
        method="bm25_vector_rrf",
        rrf_k=60,
        payload=hit.get("source") or {},
    )


def adapt_citybench_result(hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """把 citybench 的命中列表整体映射成 evidence wrapper 列表。"""
    return [adapt_citybench_hit(hit, rank=index) for index, hit in enumerate(hits, start=1)]


# ---------------------------------------------------------------------------
# §6.2 network-traffic-analysis（网络流量）
# ---------------------------------------------------------------------------


def _network_traffic_time_range(metadata: dict[str, Any]) -> dict[str, Any] | None:
    """从 ``metadata.time_bucket``（如 ``t+3600s``）还原相对时间（task.md §3.3 / §6.2）。

    network-traffic 的桶标签是相对采集起点的偏移，**禁止**被解释成真实日期。
    """
    bucket = str(metadata.get("time_bucket") or "").strip()
    matched = _RELATIVE_BUCKET_RE.match(bucket)
    if not matched:
        return None
    start = int(float(matched.group(1)))
    return {
        "mode": "relative",
        "start_offset_s": start,
        "end_offset_s": start + _RELATIVE_BUCKET_SECONDS,
    }


def adapt_network_traffic_hit(hit: dict[str, Any], *, rank: int | None = None) -> dict[str, Any]:
    """task.md §6.2：network-traffic ``rag_search.py`` 命中映射。

    ``doc_id → evidence_id``、``summary → text``、``dataset_name → meta.source_id``、
    ``source_file → meta.source_path``、``metadata`` 字段字典 ``→ meta.features``。
    时间用 ``mode=relative``；``geo_scope`` 置 ``{}``（无空间属性但保持对象类型）。
    """
    metadata = dict(hit.get("metadata") or {})

    # metadata 即 netflow 字段字典；time_bucket 归入 time_range，不留在 features。
    features = {key: value for key, value in metadata.items() if key != "time_bucket"}
    if "anomaly_flag" not in features:
        risk = str(metadata.get("risk_level") or metadata.get("risk_bucket") or "").lower()
        features["anomaly_flag"] = bool(metadata.get("is_scan_like")) or risk in {"high", "critical", "severe"}

    payload = build_evidence_unit(
        evidence_id=hit.get("doc_id") or "",
        data_type="netflow",
        text=_first_nonempty(hit.get("summary"), hit.get("content"), hit.get("title")),
        source_id=hit.get("dataset_name") or "",
        source_path=hit.get("source_file") or None,
        time_range=_network_traffic_time_range(metadata),
        geo_scope={},  # §6.2：网络流量无空间属性，但 geo_scope 必须是对象（§7 规则 5）。
        granularity=hit.get("doc_type") or "flow_summary",
        features=features,
    )
    return build_retrieval_evidence(
        evidence_ref=hit.get("doc_id") or "",
        rank=rank,
        score=hit.get("score"),
        method="bm25_vector_rrf",
        rrf_k=60,
        matched_fields=["summary", "content"],
        payload=payload,
    )


def adapt_network_traffic_result(hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """把 network-traffic 的命中列表整体映射成 evidence wrapper 列表。"""
    return [adapt_network_traffic_hit(hit, rank=index) for index, hit in enumerate(hits, start=1)]


def build_network_traffic_skill_result(result: dict[str, Any]) -> dict[str, Any]:
    """把 network-traffic ``rag_search.py`` 的整份结果字典包成完整 SkillResult。

    ``result`` 是 ``rag_search.py`` ``--format json`` 的输出（含 ``query`` / ``hits`` /
    ``hit_count`` / ``index_name`` / ``retrieval_strategy`` / ``embedding_model`` 等）。
    """
    hits = result.get("hits") or []
    evidence = adapt_network_traffic_result(hits)
    anomaly_count = sum(
        1 for wrapper in evidence if wrapper["payload"]["meta"]["features"].get("anomaly_flag")
    )
    hit_count = result.get("hit_count", len(hits))
    query = result.get("query", "")

    summary = build_summary(
        title=f"网络流量证据检索：{query}" if query else "网络流量证据检索",
        overview=f"命中 {hit_count} 条证据，其中 {anomaly_count} 条标记异常。",
        key_metrics=[
            build_key_metric(name="result_count", value=hit_count),
            build_key_metric(name="anomaly_count", value=anomaly_count),
        ],
    )
    return build_skill_result(
        skill_name="network-traffic-analysis",
        scenario="netflow",
        capability="evidence_search",
        status="success",
        summary=summary,
        evidence=evidence,
        diagnostics={
            "data_quality": {
                "hit_count": hit_count,
                "retrieval_strategy": result.get("retrieval_strategy", "hybrid-text-plus-vector"),
            },
            "runtime": {
                "mode": "es",
                "index_name": result.get("index_name", ""),
                "embedding_model": result.get("embedding_model", ""),
            },
        },
    )


# ---------------------------------------------------------------------------
# §6.3 road-traffic 年报 RAG（gazetteer）
# ---------------------------------------------------------------------------


def _road_traffic_evidence_id(hit: dict[str, Any]) -> str:
    """稳定 evidence_id：优先用原生 id，否则由 section_path + pages 哈希得出。"""
    explicit = hit.get("evidence_id") or hit.get("doc_id") or hit.get("id")
    if explicit:
        return str(explicit)
    seed = f"{hit.get('section_path', '')}#p{hit.get('pages', '')}"
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:16]
    return f"gazetteer_{digest}"


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
    """
    raw_scores: dict[str, Any] = {}
    if hit.get("distance") is not None:
        raw_scores["distance"] = hit["distance"]
    if hit.get("rerank_score") is not None:
        raw_scores["rerank_score"] = hit["rerank_score"]

    payload = build_evidence_unit(
        evidence_id=_road_traffic_evidence_id(hit),
        data_type="gazetteer",
        text=_first_nonempty(hit.get("preview"), hit.get("text"), hit.get("section_path")),
        source_id=hit.get("source_id") or source_id,
        source_path=hit.get("source_path") or None,
        granularity="paragraph",
        locator=build_locator(section=hit.get("section_path"), page=hit.get("pages")),
        features={
            key: hit[key]
            for key in ("section_path", "pages", "year", "region", "metric_name", "value", "unit")
            if hit.get(key) is not None
        },
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


def adapt_road_traffic_result(hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """把 road-traffic 年报 RAG 的命中列表整体映射成 evidence wrapper 列表。"""
    return [adapt_road_traffic_hit(hit, rank=index) for index, hit in enumerate(hits, start=1)]


# ---------------------------------------------------------------------------
# §6.4 policies-regulations RAG（policy）
# ---------------------------------------------------------------------------


def adapt_policy_hit(
    hit: dict[str, Any],
    *,
    rank: int | None = None,
    source_id: str = "policies_regulations",
) -> dict[str, Any]:
    """task.md §6.4：policies-regulations RAG 命中映射。

    ``doc_id → evidence_id``、``text → text``（必要时裁成摘要）、
    ``title / policy_number / page / paragraph → meta.locator + meta.features``、
    ``bm25_score / vector_score → evidence wrapper.retrieval.raw_scores``、
    ``data_type = "policy"``。
    """
    raw_scores: dict[str, Any] = {}
    if hit.get("bm25_score") is not None:
        raw_scores["bm25_score"] = hit["bm25_score"]
    if hit.get("vector_score") is not None:
        raw_scores["vector_score"] = hit["vector_score"]

    features = {
        key: hit[key]
        for key in ("doc_id", "policy_number", "effective_date", "issuer", "title")
        if hit.get(key) is not None
    }

    payload = build_evidence_unit(
        evidence_id=hit.get("doc_id") or "",
        data_type="policy",
        text=_first_nonempty(hit.get("summary"), hit.get("text"), hit.get("title")),
        source_id=hit.get("source_id") or source_id,
        source_path=hit.get("source_path") or None,
        granularity="paragraph",
        locator=build_locator(page=hit.get("page"), paragraph_id=hit.get("paragraph")),
        features=features,
    )
    return build_retrieval_evidence(
        evidence_ref=hit.get("doc_id") or "",
        rank=rank,
        score=hit.get("score"),
        method="bm25_vector_rrf",
        raw_scores=raw_scores or None,
        matched_fields=["text", "title"],
        payload=payload,
    )


def adapt_policy_result(hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """把 policies-regulations RAG 的命中列表整体映射成 evidence wrapper 列表。"""
    return [adapt_policy_hit(hit, rank=index) for index, hit in enumerate(hits, start=1)]
