"""6 类 v1.1 新 adapter 单元测试。

覆盖 traffic_flow / telecom / code / streetview / remote_sensing / surveillance。
"""

from __future__ import annotations

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from retrieval_protocol import adapters, validate  # noqa: E402


def _assert_valid(testcase, wrapper):
    issues = validate.validate_evidence(wrapper)
    testcase.assertEqual(issues, [], msg=f"wrapper invalid: {issues}")


class TestTrafficFlow(unittest.TestCase):
    def test_minimal(self):
        w = adapters.adapt_traffic_flow_hit({
            "doc_id": "tf-001",
            "summary": "陆家嘴早高峰流量同比 +18%",
            "city": "Shanghai",
            "geohash": "wtw3s",
            "flow_count": 1280,
            "peak_hour": 8,
            "score": 0.91,
        }, rank=1)
        _assert_valid(self, w)
        payload = w["payload"]
        self.assertEqual(payload["data_type"], "traffic_flow")
        self.assertEqual(payload["meta"]["geo_scope"]["city"], "Shanghai")
        self.assertIn("flow_count", payload["meta"]["features"])

    def test_with_time_range(self):
        w = adapters.adapt_traffic_flow_hit({
            "doc_id": "tf-002",
            "summary": "晚高峰严重拥堵",
            "time_start": "2024-03-01T17:00:00+08:00",
            "time_end": "2024-03-01T19:00:00+08:00",
            "anomaly_flag": True,
            "score": 0.85,
        })
        self.assertEqual(w["payload"]["meta"]["time_range"]["mode"], "absolute")


class TestTelecom(unittest.TestCase):
    def test_default_with_hashed_id(self):
        wrapper = adapters.adapt_telecom_hit({
            "doc_id": "tc1", "summary": "user a3f5 in community_42",
            "community_id": "42",
        })
        payload = wrapper["payload"]
        self.assertEqual(payload["meta"]["sensitivity_level"], "pii_masked")
        self.assertEqual(payload["meta"]["access_policy"], "internal_only")

    def test_upgrade_on_plain_phone(self):
        wrapper = adapters.adapt_telecom_hit({
            "doc_id": "tc2", "summary": "号码 13800138000 通话",
        })
        payload = wrapper["payload"]
        self.assertEqual(payload["meta"]["sensitivity_level"], "restricted")
        self.assertEqual(payload["meta"]["access_policy"], "restricted")

    def test_downgrade_on_aggregated_safe(self):
        wrapper = adapters.adapt_telecom_hit({
            "doc_id": "tc3", "summary": "区间通话量统计",
            "call_count": 1200, "unique_contacts": 25,
        })
        payload = wrapper["payload"]
        self.assertEqual(payload["meta"]["sensitivity_level"], "aggregated_safe")
        self.assertEqual(payload["meta"]["access_policy"], "open")

    def test_geo_scope_is_object(self):
        w = adapters.adapt_telecom_hit({
            "doc_id": "tc-002", "summary": "x", "call_count": 1, "score": 0.5,
        })
        self.assertEqual(w["payload"]["meta"]["geo_scope"], {})


class TestCode(unittest.TestCase):
    def test_locator_and_features(self):
        w = adapters.adapt_code_hit({
            "doc_id": "code-001",
            "snippet": "def _load_landmarks(): ...",
            "file_path": "skills/_shared/retrieval_protocol/adapters.py",
            "line_start": 120, "line_end": 138,
            "lang": "python",
            "ast_node_type": "function_def",
            "symbol": "_load_landmarks",
            "bm25_score": 12.3,
        }, rank=1)
        _assert_valid(self, w)
        payload = w["payload"]
        self.assertEqual(payload["data_type"], "code")
        self.assertEqual(payload["meta"]["locator"]["line_start"], 120)
        self.assertEqual(payload["meta"]["locator"]["symbol"], "_load_landmarks")
        self.assertEqual(payload["meta"]["features"]["lang"], "python")
        self.assertEqual(w["retrieval"]["raw_scores"]["bm25_score"], 12.3)


class TestStreetview(unittest.TestCase):
    def test_image_geo(self):
        w = adapters.adapt_streetview_hit({
            "doc_id": "sv-001",
            "caption": "陆家嘴中环夜间街景,有 1 处违停",
            "objects": ["car", "truck", "pedestrian"],
            "bbox": [121.50, 31.23, 121.51, 31.24],
            "taken_at": "2024-03-01T22:30:00+08:00",
            "city": "Shanghai",
            "lat": 31.235, "lon": 121.505,
            "image_uri": "s3://streetview/sv-001.jpg",
            "score": 0.88,
        }, rank=1)
        _assert_valid(self, w)
        payload = w["payload"]
        self.assertEqual(payload["data_type"], "streetview")
        self.assertEqual(payload["meta"]["geo_scope"]["lat"], 31.235)
        self.assertIn("objects", payload["meta"]["features"])
        self.assertEqual(payload["meta"]["features"]["image_uri"], "s3://streetview/sv-001.jpg")


class TestRemoteSensing(unittest.TestCase):
    def test_change_detection(self):
        w = adapters.adapt_remote_sensing_hit({
            "doc_id": "rs-001",
            "caption": "瓦片 T08-12 检出新增建筑 2 处",
            "objects": ["building_new"],
            "bbox": [121.4, 31.2, 121.5, 31.3],
            "tile_id": "T08-12",
            "taken_at": "2024-03-15T10:00:00+08:00",
            "change_score": 0.72,
            "cloud_cover": 0.1,
            "score": 0.81,
        }, rank=1)
        _assert_valid(self, w)
        payload = w["payload"]
        self.assertEqual(payload["data_type"], "remote_sensing")
        self.assertEqual(payload["meta"]["features"]["tile_id"], "T08-12")
        self.assertAlmostEqual(payload["meta"]["features"]["change_score"], 0.72)


class TestSurveillance(unittest.TestCase):
    def test_default_restricted(self):
        wrapper = adapters.adapt_surveillance_hit({
            "doc_id": "sv1", "summary": "frame summary",
            "stream_url": "rtsp://10.0.0.1/cam",
        })
        payload = wrapper["payload"]
        self.assertEqual(payload["meta"]["sensitivity_level"], "restricted")
        self.assertEqual(payload["meta"]["access_policy"], "restricted")

    def test_downgrade_when_masked_no_link(self):
        wrapper = adapters.adapt_surveillance_hit({
            "doc_id": "sv2", "summary": "blurred crowd",
            "objects": [{"label": "face", "masked": True}],
        })
        payload = wrapper["payload"]
        self.assertEqual(payload["meta"]["sensitivity_level"], "pii_masked")
        self.assertEqual(payload["meta"]["access_policy"], "internal_only")


class TestBatchAdapters(unittest.TestCase):
    """逐 adapter 的 *_result 接口应当对齐 rank 编号(从 1 开始)。"""

    def test_traffic_flow_rank_numbering(self):
        wrappers = adapters.adapt_traffic_flow_result([
            {"doc_id": f"tf-{i}", "summary": "x", "score": 0.5, "flow_count": 1}
            for i in range(3)
        ])
        self.assertEqual([w["rank"] for w in wrappers], [1, 2, 3])

    def test_all_six_have_batch_helpers(self):
        # 仅做存在性检查 —— 每个 *_result 函数都应可调用且返回 list。
        for fn_name in (
            "adapt_traffic_flow_result", "adapt_telecom_result", "adapt_code_result",
            "adapt_streetview_result", "adapt_remote_sensing_result", "adapt_surveillance_result",
        ):
            fn = getattr(adapters, fn_name)
            self.assertTrue(callable(fn), fn_name)
            self.assertEqual(fn([]), [])


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


if __name__ == "__main__":
    unittest.main()
