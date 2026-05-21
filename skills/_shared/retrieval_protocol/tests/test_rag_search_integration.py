"""集成测试 —— network-traffic ``rag_search.py`` 的 ``--format skillresult`` 接入。

直接加载真实的 ``rag_search.py``，调用其 ``_build_skill_result_output`` 辅助函数，
验证它经 ``retrieval_protocol`` 产出的 SkillResult 通过 §7 校验。Elasticsearch 端到端
检索无法在此环境运行，故只覆盖映射 / 包装这一段（rag_search.py 的薄接入层）。
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from retrieval_protocol import validate_skill_result  # noqa: E402

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]
_RAG_SEARCH = _REPO_ROOT / "skills" / "custom" / "network-traffic-analysis" / "scripts" / "rag_search.py"


def _load_rag_search():
    """以模块方式加载真实 rag_search.py（仅执行模块级代码，不跑 main）。"""
    spec = importlib.util.spec_from_file_location("rag_search_under_test", _RAG_SEARCH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fake_rag_search_result() -> dict:
    """模拟 rag_search.py ``--format json`` 的结果字典。"""
    return {
        "query": "Virut 数据集是否存在扫描行为",
        "index_name": "network-traffic-rag",
        "hit_count": 2,
        "retrieval_strategy": "hybrid-text-plus-vector",
        "embedding_provider": "dashscope",
        "embedding_model": "text-embedding-v3-large",
        "hits": [
            {
                "score": 0.0312, "doc_id": "virut__anomaly__001", "doc_type": "anomaly_summary",
                "title": "scan-like burst", "summary": "10.0.0.5 probes many destinations over TCP.",
                "dataset_name": "Virut", "source_file": "processed/Virut/Virut.flow.csv",
                "keywords": ["scan", "tcp"],
                "metadata": {"src_ip": "10.0.0.5", "protocol": "TCP", "is_scan_like": True,
                             "time_bucket": "t+0s", "risk_level": "high"},
            },
            {
                "score": 0.0208, "doc_id": "virut__flow__002", "doc_type": "flow_summary",
                "title": "normal TLS", "summary": "Routine TLS session to a CDN endpoint.",
                "dataset_name": "Virut", "source_file": "processed/Virut/Virut.flow.csv",
                "keywords": ["tls"],
                "metadata": {"src_ip": "10.0.0.9", "protocol": "TCP", "is_scan_like": False,
                             "time_bucket": "t+3600s", "risk_level": "low"},
            },
        ],
    }


class TestRagSearchSkillResultOutput(unittest.TestCase):
    def setUp(self):
        self.assertTrue(_RAG_SEARCH.exists(), f"rag_search.py not found at {_RAG_SEARCH}")
        self.rag_search = _load_rag_search()

    def test_helper_exists(self):
        self.assertTrue(hasattr(self.rag_search, "_build_skill_result_output"))

    def test_skillresult_is_a_choice_in_parser(self):
        parser = self.rag_search.build_parser()
        fmt_action = next(a for a in parser._actions if a.dest == "format")
        self.assertIn("skillresult", fmt_action.choices)
        # 不破坏既有格式。
        self.assertIn("json", fmt_action.choices)
        self.assertIn("text", fmt_action.choices)

    def test_build_skill_result_output_passes_validation(self):
        skill_result = self.rag_search._build_skill_result_output(_fake_rag_search_result())
        self.assertEqual(validate_skill_result(skill_result), [])

    def test_skill_result_carries_evidence_and_metrics(self):
        skill_result = self.rag_search._build_skill_result_output(_fake_rag_search_result())
        self.assertEqual(skill_result["skill_name"], "network-traffic-analysis")
        self.assertEqual(skill_result["capability"], "evidence_search")
        self.assertEqual(len(skill_result["result"]["evidence"]), 2)
        metrics = {m["name"]: m["value"] for m in skill_result["result"]["summary"]["key_metrics"]}
        self.assertEqual(metrics["result_count"], 2)
        self.assertEqual(metrics["anomaly_count"], 1)

    def test_first_evidence_payload_is_protocol_compliant_netflow(self):
        skill_result = self.rag_search._build_skill_result_output(_fake_rag_search_result())
        payload = skill_result["result"]["evidence"][0]["payload"]
        self.assertEqual(payload["data_type"], "netflow")
        self.assertEqual(payload["meta"]["geo_scope"], {})
        # t+0s 桶 → 相对时间，禁止解释成真实日期。
        self.assertEqual(payload["meta"]["time_range"]["mode"], "relative")


if __name__ == "__main__":
    unittest.main()
