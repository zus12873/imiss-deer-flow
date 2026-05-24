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
    def test_pii_defaults(self):
        w = adapters.adapt_telecom_hit({
            "doc_id": "tc-001",
            "summary": "用户 X 与社区 12 联系最密",
            "call_count": 32,
            "community_id": 12,
            "score": 0.78,
        })
        payload = w["payload"]
        # 电话数据默认 PII 敏感。
        self.assertEqual(payload["meta"]["sensitivity_level"], "pii_masked")
        self.assertEqual(payload["meta"]["access_policy"], "restricted")
        _assert_valid(self, w)

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
    def test_clip_and_pii_defaults(self):
        w = adapters.adapt_surveillance_hit({
            "doc_id": "sv-cam-001",
            "caption": "摄像头 A01 检出聚集事件",
            "objects": ["pedestrian"],
            "clip_start": "2024-03-01T20:15:00+08:00",
            "clip_end": "2024-03-01T20:15:30+08:00",
            "behavior": "gathering",
            "camera_id": "A01",
            "video_uri": "s3://surveillance/A01-20240301-2015.mp4",
            "city": "Shanghai",
            "camera_lat": 31.23, "camera_lon": 121.50,
            "score": 0.93,
        })
        _assert_valid(self, w)
        payload = w["payload"]
        self.assertEqual(payload["data_type"], "surveillance")
        # 视频监控默认 PII 敏感。
        self.assertEqual(payload["meta"]["sensitivity_level"], "pii_masked")
        self.assertEqual(payload["meta"]["access_policy"], "restricted")
        self.assertEqual(payload["meta"]["time_range"]["mode"], "absolute")
        self.assertEqual(payload["meta"]["features"]["behavior"], "gathering")


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


if __name__ == "__main__":
    unittest.main()
