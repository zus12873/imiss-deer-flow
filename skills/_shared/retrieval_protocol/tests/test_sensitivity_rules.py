"""敏感度落档规则单测 —— spec 2026-05-27 §3."""
from __future__ import annotations

import unittest

from retrieval_protocol import sensitivity_rules as sr


class TestDefaultTable(unittest.TestCase):
    def test_six_data_types_present(self):
        expected = {
            "gazetteer":      ("aggregated_safe", "open"),
            "telecom":        ("pii_masked",      "internal_only"),
            "code":           ("pii_masked",      "internal_only"),
            "streetview":     ("pii_masked",      "internal_only"),
            "remote_sensing": ("aggregated_safe", "open"),
            "surveillance":   ("restricted",      "restricted"),
        }
        self.assertEqual(sr.DEFAULT_SENSITIVITY, expected)

    def test_k_threshold(self):
        self.assertEqual(sr.K_THRESHOLD_AGGREGATED_SAFE, 10)


if __name__ == "__main__":
    unittest.main()
