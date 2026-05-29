"""planner.py 单元测试 —— split_budget / build_plan。"""

from __future__ import annotations

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from retrieval_protocol import planner  # noqa: E402


class TestSplitBudget(unittest.TestCase):
    def test_equal_split_both_fields(self):
        total = {"max_evidence_count": 30, "max_token_estimate": 9000}
        parts = planner.split_budget(total, 3)
        self.assertEqual(len(parts), 3)
        self.assertEqual(sum(p["max_evidence_count"] for p in parts), 30)
        self.assertEqual(sum(p["max_token_estimate"] for p in parts), 9000)
        # 等分:每份 10 / 3000
        self.assertEqual([p["max_evidence_count"] for p in parts], [10, 10, 10])

    def test_remainder_goes_to_first(self):
        total = {"max_evidence_count": 10}
        parts = planner.split_budget(total, 3)
        # 10 // 3 = 3, 余 1 给第一个 → [4, 3, 3]
        self.assertEqual([p["max_evidence_count"] for p in parts], [4, 3, 3])
        self.assertEqual(sum(p["max_evidence_count"] for p in parts), 10)

    def test_weighted_split(self):
        total = {"max_evidence_count": 100}
        parts = planner.split_budget(total, 2, weights=[3.0, 1.0])
        # 75 / 25
        self.assertEqual(sum(p["max_evidence_count"] for p in parts), 100)
        self.assertGreater(parts[0]["max_evidence_count"], parts[1]["max_evidence_count"])
        self.assertEqual(parts[0]["max_evidence_count"], 75)
        self.assertEqual(parts[1]["max_evidence_count"], 25)

    def test_single_field_only(self):
        total = {"max_token_estimate": 8000}
        parts = planner.split_budget(total, 4)
        self.assertEqual(sum(p["max_token_estimate"] for p in parts), 8000)
        self.assertTrue(all("max_evidence_count" not in p for p in parts))

    def test_fan_out_one_returns_total(self):
        total = {"max_evidence_count": 7, "max_token_estimate": 100}
        parts = planner.split_budget(total, 1)
        self.assertEqual(parts, [{"max_evidence_count": 7, "max_token_estimate": 100}])

    def test_invalid_fan_out_raises(self):
        with self.assertRaises(ValueError):
            planner.split_budget({"max_evidence_count": 5}, 0)

    def test_weights_length_mismatch_raises(self):
        with self.assertRaises(ValueError):
            planner.split_budget({"max_evidence_count": 5}, 3, weights=[1.0, 1.0])


if __name__ == "__main__":
    unittest.main()
