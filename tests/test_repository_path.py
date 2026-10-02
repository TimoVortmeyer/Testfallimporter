from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from xray_import.models import TestCaseValidationError, load_testcases


class OptionalTestCaseFieldsInputTest(unittest.TestCase):
    def test_repository_path_is_loaded_from_testcase_json(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            testcases_dir = Path(directory)
            testcase_dir = testcases_dir / "case-1"
            testcase_dir.mkdir()
            (testcase_dir / "testcase.json").write_text(
                json.dumps({
                    "summary": "Testfall",
                    "repository_path": "/Bereich/Unterbereich",
                    "steps": [{
                        "system": "Portal",
                        "action": "Öffnen",
                        "expected_result": "Sichtbar",
                    }],
                }),
                encoding="utf-8",
            )
            schema_path = Path(__file__).resolve().parents[1] / "schema/testcase.schema.json"

            testcases = load_testcases(testcases_dir, schema_path)

            self.assertEqual(testcases[0][0].repository_path, "/Bereich/Unterbereich")

    def test_repository_path_rejects_trailing_slash(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            testcases_dir = Path(directory)
            testcase_dir = testcases_dir / "case-1"
            testcase_dir.mkdir()
            (testcase_dir / "testcase.json").write_text(
                json.dumps({
                    "summary": "Testfall",
                    "repository_path": "/Bereich/",
                    "steps": [{
                        "system": "Portal",
                        "action": "Öffnen",
                        "expected_result": "Sichtbar",
                    }],
                }),
                encoding="utf-8",
            )
            schema_path = Path(__file__).resolve().parents[1] / "schema/testcase.schema.json"

            with self.assertRaises(TestCaseValidationError):
                load_testcases(testcases_dir, schema_path)

    def test_reporter_email_is_loaded_from_testcase_json(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            testcases_dir = Path(directory)
            testcase_dir = testcases_dir / "case-1"
            testcase_dir.mkdir()
            (testcase_dir / "testcase.json").write_text(
                json.dumps({
                    "summary": "Testfall",
                    "reporter_email": "tester@example.test",
                    "steps": [{
                        "system": "Portal",
                        "action": "Öffnen",
                        "expected_result": "Sichtbar",
                    }],
                }),
                encoding="utf-8",
            )
            schema_path = Path(__file__).resolve().parents[1] / "schema/testcase.schema.json"

            testcases = load_testcases(testcases_dir, schema_path)

            self.assertEqual(testcases[0][0].reporter_email, "tester@example.test")