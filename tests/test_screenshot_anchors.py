from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from xray_import.models import TestCaseValidationError, load_testcases

SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schema/testcase.schema.json"


def _write_case(root: Path, action: str, screenshots: list[str]) -> None:
    case_dir = root / "case-1"
    (case_dir / "screenshots").mkdir(parents=True)
    for name in screenshots:
        (case_dir / "screenshots" / name).write_bytes(b"png")
    (case_dir / "testcase.json").write_text(
        json.dumps({
            "summary": "Testfall",
            "steps": [{"system": "Portal", "action": action, "expected_result": "OK", "attachments": screenshots}],
        }),
        encoding="utf-8",
    )


class ScreenshotAnchorTest(unittest.TestCase):
    def test_exclamation_mark_before_anchor_is_text(self) -> None:
        action = "Gleiche Vorgehensweise wie bei der EDEKA WG!\n!0031.png!\nNoch ein Hinweis!\n\n!0032.png!"
        with tempfile.TemporaryDirectory() as directory:
            _write_case(Path(directory), action, ["0031.png", "0032.png"])

            testcase = load_testcases(Path(directory), SCHEMA_PATH)[0][0]

        self.assertEqual(testcase.all_screenshot_filenames(), {"0031.png", "0032.png"})

    def test_missing_anchor_file_is_still_reported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            _write_case(Path(directory), "Klick !0001.png!", [])

            with self.assertRaises(TestCaseValidationError) as raised:
                load_testcases(Path(directory), SCHEMA_PATH)

        self.assertIn("0001.png", str(raised.exception))
