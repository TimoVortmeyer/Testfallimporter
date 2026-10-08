from __future__ import annotations

import logging
import unittest

from urllib3.exceptions import ConnectTimeoutError, MaxRetryError, ProtocolError

from xray_import.config import Config
from xray_import.http_session import MAX_RETRIES, RETRYABLE_METHODS, RETRY_STATUS_CODES, create_retry_session


class HttpRetryPolicyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.session = create_retry_session()
        self.addCleanup(self.session.close)
        self.retry = self.session.get_adapter("https://").max_retries

    def test_retry_count_methods_and_statuses_are_bounded(self) -> None:
        self.assertEqual(self.retry.total, MAX_RETRIES)
        self.assertEqual(self.retry.connect, MAX_RETRIES)
        self.assertEqual(self.retry.read, MAX_RETRIES)
        self.assertEqual(self.retry.status_forcelist, RETRY_STATUS_CODES)
        self.assertEqual(self.retry.allowed_methods, RETRYABLE_METHODS)
        self.assertNotIn("POST", self.retry.allowed_methods)

    def test_post_connect_timeout_is_retried_but_reset_after_send_is_not(self) -> None:
        next_retry = self.retry.increment(
            method="POST",
            url="/rest/api/2/issue",
            error=ConnectTimeoutError(None, "connect timeout"),
        )
        self.assertEqual(next_retry.total, MAX_RETRIES - 1)

        with self.assertRaises(ProtocolError):
            self.retry.increment(
                method="POST",
                url="/rest/api/2/issue",
                error=ProtocolError("connection reset"),
            )

    def test_get_connection_reset_is_retried_and_logged(self) -> None:
        with self.assertLogs("xray_import.http_session", level=logging.WARNING) as captured:
            next_retry = self.retry.increment(
                method="GET",
                url="/rest/api/2/project/TEST",
                error=ProtocolError("connection reset"),
            )
        self.assertEqual(next_retry.total, MAX_RETRIES - 1)
        self.assertIn("HTTP-Retry: GET", captured.output[0])

    def test_effective_timeout_has_ten_second_connect_and_sixty_second_response_cap(self) -> None:
        config = Config(
            jira_base_url="https://jira.example.test",
            manual_steps_custom_field="customfield_1",
            test_type_custom_field="customfield_2",
            manual_test_type_value="Manual",
            project_key="TEST",
            test_issue_type="Test",
            personal_access_token="token",
            request_timeout=300,
            connect_timeout=30,
        )
        self.assertEqual(config.request_timeout_pair, (10, 60))