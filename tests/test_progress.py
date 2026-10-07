from __future__ import annotations

import io
import unittest

from xray_import.progress import ImportProgress


class ImportProgressTest(unittest.TestCase):
    def test_writes_one_line_per_update_with_estimates(self) -> None:
        stream = io.StringIO()
        times = iter([0.0, 0.0, 10.0, 20.0])
        progress = ImportProgress(2, stream=stream, clock=lambda: next(times))

        progress.update(0)
        progress.update(1, current="TF_A", status="TEST-1")
        progress.update(2, current="TF_B", status="Fehler")

        lines = stream.getvalue().splitlines()
        self.assertEqual(len(lines), 3)
        self.assertIn("Import [------------------------] 0/2 (0%)", lines[0])
        self.assertIn("Gesamt --:-- | Rest --:--", lines[0])
        self.assertIn("Import [############------------] 1/2 (50%)", lines[1])
        self.assertIn("Gesamt ~00:20 | Rest ~00:10 | TEST-1 | TF_A", lines[1])
        self.assertIn("Import [########################] 2/2 (100%)", lines[2])
        self.assertIn("Rest ~00:00 | Fehler | TF_B", lines[2])

    def test_no_output_without_testcases(self) -> None:
        stream = io.StringIO()
        ImportProgress(0, stream=stream).update(0)
        self.assertEqual(stream.getvalue(), "")
