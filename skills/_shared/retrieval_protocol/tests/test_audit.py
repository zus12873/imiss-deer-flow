"""审计字段单测 —— spec 2026-05-27 §4."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from retrieval_protocol import audit


class TestAuditEnums(unittest.TestCase):
    def test_actions_set(self):
        expected = {
            "allow", "warn", "desensitize", "aggregate",
            "rewrite", "filter", "refuse", "manual_review",
        }
        self.assertEqual(audit.AUDIT_ACTIONS, frozenset(expected))

    def test_action_statuses(self):
        self.assertEqual(audit.AUDIT_ACTION_STATUSES, frozenset({"applied", "pending", "failed"}))

    def test_gates(self):
        self.assertEqual(audit.AUDIT_GATES, frozenset({"InputGate", "ContextGate", "OutputGate"}))

    def test_scenes(self):
        expected = {"self_use", "internal_org", "cross_org", "public_release", "research_anon"}
        self.assertEqual(audit.AUDIT_SCENES, frozenset(expected))

    def test_reason_codes_include_three_examples(self):
        # spec §4.2 例:struct_id_detected / geo_loc_with_object_time / re_identify_combo_risk
        self.assertIn("struct_id_detected", audit.AUDIT_REASON_CODES)
        self.assertIn("geo_loc_with_object_time", audit.AUDIT_REASON_CODES)
        self.assertIn("re_identify_combo_risk", audit.AUDIT_REASON_CODES)


if __name__ == "__main__":
    unittest.main()
