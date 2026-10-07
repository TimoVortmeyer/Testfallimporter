from __future__ import annotations

import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from xray_import.models import TestCaseValidationError, load_testcases


class LabelSchemaTest(unittest.TestCase):
    def test_steps_are_optional(self) -> None:
        schema_path = Path(__file__).resolve().parents[1] / "schema" / "testcase.schema.json"
        validator = Draft202012Validator(json.loads(schema_path.read_text(encoding="utf-8")))
        self.assertEqual(list(validator.iter_errors({"summary": "Test"})), [])

    def test_labels_require_non_whitespace_and_max_255_characters(self) -> None:
        schema_path = Path(__file__).resolve().parents[1] / "schema" / "testcase.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        validator = Draft202012Validator(schema)
        testcase = {
            "summary": "Test",
            "steps": [{"system": "Portal", "action": "Öffnen", "expected_result": "Sichtbar"}],
        }

        for label in ("RWWS-GH", "Größe", "東", "a" * 255):
            with self.subTest(label=label[:20]):
                testcase["labels"] = [label]
                self.assertEqual(list(validator.iter_errors(testcase)), [])

        for label in ("", "mit Leerzeichen", "a" * 256):
            with self.subTest(label=label[:20]):
                testcase["labels"] = [label]
                self.assertTrue(list(validator.iter_errors(testcase)))

    def test_label_regressionsdateien(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        schema_path = project_root / "schema" / "testcase.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        validator = Draft202012Validator(schema)
        expected = {
            "01_hyphen": "test-label",
            "02_underscore": "test_label",
            "03_mixed_alphanumeric": "TestLabel123",
            "04_umlaut": "größe",
            "05_japanese": "日本語",
            "06_cyrillic": "тест",
            "08_comma": "test,label",
            "09_at": "test@label",
            "10_hash": "test#1",
            "11_slash": "test/label",
            "12_parentheses": "test(1)",
            "13_dot": "test.label",
            "14_ampersand": "test&label",
            "15_exclamation": "test!",
            "16_digits": "12345",
            "17_starts_digit": "1label",
            "18_starts_hyphen": "-label",
            "19_starts_underscore": "_label",
            "20_hyphens_only": "---",
            "21_one_letter": "a",
            "24_emoji": "test😀label",
            "25_backslash": "test\\label",
            "26_double_quote": 'test"label',
            "27_single_quote": "test'label",
            "28_percent": "test%label",
        }
        case_root = project_root / "input" / "label_regex_cases"
        actual = {}
        for folder in case_root.iterdir():
            testcase_path = folder / "testcase.json"
            if not testcase_path.is_file():
                continue
            testcase = json.loads(testcase_path.read_text(encoding="utf-8"))
            errors = list(validator.iter_errors(testcase))
            if folder.name in expected:
                self.assertEqual(errors, [], folder.name)
                actual[folder.name] = testcase["labels"][0]
            else:
                self.assertTrue(errors, folder.name)
        self.assertEqual(actual, expected)

        with self.assertRaisesRegex(TestCaseValidationError, "labels/0"):
            load_testcases(project_root / "input" / "label_regex_schema_rejected", schema_path)