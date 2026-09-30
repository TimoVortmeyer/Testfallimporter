from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from xray_import.config import load_config, load_import_settings


class ConfigOverrideTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        tmp = Path(self._tmp.name)
        self.profile_path = self._write(tmp / "profile.json", self._profile("PROFILE"))
        self.other_profile_path = self._write(tmp / "other.json", self._profile("OTHER"))
        self.config_path = self._write(
            tmp / "import_config.json",
            {
                "jira_base_url": "https://file.example.test",
                "project_profile": str(self.profile_path),
                "testcases_dir": "input/testcases",
                "testcase_filename": "testcase.json",
                "screenshots_dirname": "screenshots",
            },
        )

    @staticmethod
    def _write(path: Path, content: dict[str, object]) -> Path:
        path.write_text(json.dumps(content), encoding="utf-8")
        return path

    @staticmethod
    def _profile(project_key: str) -> dict[str, object]:
        return {
            "project_key": project_key,
            "test_issue_type": "Test",
            "test_type_custom_field": "customfield_1",
            "manual_steps_custom_field": "customfield_2",
            "manual_test_type_value": "Manual",
            "step_field_mapping": {"action": "Action"},
            "xray_api_version": "1.0",
            "schema_path": "schema/testcase.schema.json",
        }

    def test_overrides_take_precedence_over_file_and_profile(self) -> None:
        settings = load_import_settings(
            self.config_path,
            {"testcases_dir": "andere/testcases", "schema_path": "anderes.schema.json"},
        )
        self.assertEqual(settings["testcases_dir"], "andere/testcases")
        self.assertEqual(settings["schema_path"], "anderes.schema.json")
        self.assertEqual(settings["testcase_filename"], "testcase.json")

    def test_project_profile_override_loads_other_profile(self) -> None:
        settings = load_import_settings(
            self.config_path, {"project_profile": str(self.other_profile_path)}
        )
        self.assertEqual(settings["project_key"], "OTHER")

    def test_cli_overrides_environment_and_environment_overrides_file(self) -> None:
        env = {"JIRA_PAT": "token", "JIRA_BASE_URL": "https://env.example.test"}
        with patch.dict(os.environ, env, clear=True):
            from_env = load_config(self.config_path)
            from_cli = load_config(
                self.config_path,
                {"jira_base_url": "https://cli.example.test/", "project_key": "CLI"},
            )
        self.assertEqual(from_env.jira_base_url, "https://env.example.test")
        self.assertEqual(from_env.project_key, "PROFILE")
        self.assertEqual(from_cli.jira_base_url, "https://cli.example.test")
        self.assertEqual(from_cli.project_key, "CLI")

    def test_cli_pat_overrides_environment(self) -> None:
        with patch.dict(os.environ, {"JIRA_PAT": "env-token"}, clear=True):
            config = load_config(
                self.config_path, {"personal_access_token": "cli-token"}
            )
        self.assertEqual(config.personal_access_token, "cli-token")

    def test_missing_pat_raises(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(RuntimeError):
                load_config(self.config_path)


if __name__ == "__main__":
    unittest.main()
