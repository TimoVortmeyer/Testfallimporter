from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

import pytest

from xray_import.import_testcases import PartialImportError, import_testcase
from xray_import.jira_client import JiraApiError
from xray_import.models import TestCase as ImportedTestCase


def test_original_word_comment_follows_import_comment_and_failure_keeps_issue_key(tmp_path: Path) -> None:
    testcase = ImportedTestCase(summary="TFB_1", source_word_filename="TFB_1.docx")
    jira = Mock()
    jira.create_test_issue.return_value = "TEST-1"
    jira.add_import_comment.side_effect = JiraApiError("Kommentar abgelehnt")
    xray = Mock()

    with pytest.raises(PartialImportError) as raised:
        import_testcase(testcase, jira, xray, tmp_path, "08.10.2026 12:34:56")

    assert raised.value.issue_key == "TEST-1"
    jira.add_import_comment.assert_called_once_with("TEST-1", "08.10.2026 12:34:56", "TFB_1.docx")


def test_older_testcase_without_source_filename_does_not_post_extra_comment(tmp_path: Path) -> None:
    testcase = ImportedTestCase(summary="TFB_legacy")
    jira = Mock()
    jira.create_test_issue.return_value = "TEST-2"
    xray = Mock()

    assert import_testcase(testcase, jira, xray, tmp_path, "08.10.2026 12:34:56") == "TEST-2"

    jira.add_import_comment.assert_called_once_with("TEST-2", "08.10.2026 12:34:56", None)
