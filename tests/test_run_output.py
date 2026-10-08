from __future__ import annotations

import csv
import json
import logging
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from xray_import import import_testcases
from xray_import.jira_client import JiraApiError

SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schema/testcase.schema.json"


class RunOutputTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        root = Path(self._tmp.name)
        self.output_dir = root / "out"
        testcases_dir = root / "testcases"
        for folder, summary in (("a_ok", "TF OK"), ("b_teilweise", "TF Teilweise"), ("c_fehler", "TF Fehler")):
            (testcases_dir / folder).mkdir(parents=True)
            (testcases_dir / folder / "testcase.json").write_text(json.dumps({"summary": summary}), encoding="utf-8")
        profile = root / "profile.json"
        profile.write_text(
            json.dumps({
                "project_key": "TEST",
                "test_issue_type": "Test",
                "test_type_custom_field": "customfield_1",
                "manual_steps_custom_field": "customfield_2",
                "manual_test_type_value": "Manual",
                "step_field_mapping": {"action": "Action"},
                "xray_api_version": "1.0",
                "schema_path": str(SCHEMA_PATH),
            }),
            encoding="utf-8",
        )
        self.config_path = root / "import_config.json"
        self.config_path.write_text(
            json.dumps({
                "jira_base_url": "https://jira.example.test/",
                "project_profile": str(profile),
                "testcases_dir": str(testcases_dir),
                "testcase_filename": "testcase.json",
                "screenshots_dirname": "screenshots",
                "output_dir": str(self.output_dir),
            }),
            encoding="utf-8",
        )

    def test_writes_log_and_result_file_with_links_and_errors(self) -> None:
        timestamps = []

        def fake_import(testcase, jira, xray, screenshots_dir, import_timestamp):
            timestamps.append(import_timestamp)
            if testcase.summary == "TF OK":
                return "TEST-1"
            if testcase.summary == "TF Teilweise":
                raise import_testcases.PartialImportError("TEST-2", JiraApiError("Kommentar fehlgeschlagen"))
            raise JiraApiError("Anlegen fehlgeschlagen (HTTP 400)")

        with (
            patch.dict(os.environ, {"JIRA_PAT": "token"}, clear=True),
            patch.object(import_testcases, "JiraClient", Mock()),
            patch.object(import_testcases, "XrayClient", Mock()),
            patch.object(import_testcases, "import_testcase", side_effect=fake_import),
            patch("sys.stdout"),
        ):
            result = import_testcases.run(self.config_path)

        self.assertEqual(result, 1)
        self.assertEqual(len(timestamps), 3)
        self.assertEqual(len(set(timestamps)), 1)
        self.assertRegex(timestamps[0], r"^\d{2}\.\d{2}\.\d{4} \d{2}:\d{2}:\d{2}$")
        log_files = list(self.output_dir.glob("import_*.log"))
        result_files = list(self.output_dir.glob("import_ergebnis_*.csv"))
        self.assertEqual(len(log_files), 1)
        self.assertEqual(len(result_files), 1)
        log_text = log_files[0].read_text(encoding="utf-8")
        self.assertIn("Anlegen fehlgeschlagen (HTTP 400)", log_text)
        self.assertIn("Ergebnis: 1 angelegt, 2 fehlgeschlagen", log_text)
        self.assertNotIn("token", log_text)
        self.assertFalse(
            any(
                isinstance(h, logging.FileHandler) and Path(h.baseFilename).parent == self.output_dir
                for h in logging.getLogger().handlers
            )
        )

        with result_files[0].open(encoding="utf-8-sig", newline="") as source:
            rows = list(csv.DictReader(source, delimiter=";"))
        self.assertEqual(
            [(row["testfall"], row["status"], row["issue_key"], row["link"]) for row in rows],
            [
                ("TF OK", "angelegt", "TEST-1", "https://jira.example.test/browse/TEST-1"),
                ("TF Teilweise", "fehler", "TEST-2", "https://jira.example.test/browse/TEST-2"),
                ("TF Fehler", "fehler", "", ""),
            ],
        )
        self.assertEqual(rows[0]["fehler"], "")
        self.assertIn("Kommentar fehlgeschlagen", rows[1]["fehler"])
        self.assertEqual(rows[2]["fehler"], "JiraApiError: Anlegen fehlgeschlagen (HTTP 400)")
        self.assertEqual(rows[2]["ordner"], "c_fehler")
