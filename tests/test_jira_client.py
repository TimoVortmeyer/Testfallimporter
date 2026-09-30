from __future__ import annotations

import unittest
from unittest.mock import Mock

from xray_import.config import Config
from xray_import.jira_client import JiraApiError, JiraClient
from xray_import.models import TestStep


class JiraClientDiagnosticsTest(unittest.TestCase):
    def setUp(self) -> None:
        config = Config(
            jira_base_url="https://jira.example.test",
            manual_steps_custom_field="customfield_15903",
            test_type_custom_field="customfield_15900",
            manual_test_type_value="Manual",
            project_key="TEST",
            test_issue_type="Test",
            personal_access_token="test-token",
        )
        self.client = JiraClient(config)
        self.step = TestStep(
            system="Portal",
            action="Aktion",
            expected_result="Ergebnis",
        )

    @staticmethod
    def response(
        status_code: int,
        text: str,
        headers: dict[str, str] | None = None,
        json_body: object | None = None,
    ) -> Mock:
        response = Mock(status_code=status_code, text=text, headers=headers or {})
        if json_body is not None:
            response.json.return_value = json_body
        return response

    def test_silent_step_rejection_contains_actionable_diagnostics(self) -> None:
        update_response = self.response(
            204,
            "",
            {"X-AREQUESTID": "request-123"},
        )
        verify_response = self.response(
            200,
            "field response",
            json_body={"fields": {"customfield_15903": {"steps": []}}},
        )
        xray_response = self.response(200, "[]")
        self.client._session.put = Mock(return_value=update_response)
        self.client._session.get = Mock(
            side_effect=[verify_response, xray_response]
        )

        with self.assertRaises(JiraApiError) as raised:
            self.client.update_test_steps("TEST-1", [self.step])

        message = str(raised.exception)
        self.assertIn("0 von 1 Manual-Step(s)", message)
        self.assertIn("Request-ID: request-123", message)
        self.assertIn("Xray-Gegenprüfung: HTTP 200", message)
        self.assertIn("Antwort: []", message)
        self.assertIn("System/Komponente (6 Zeichen)", message)
        self.assertIn("Action (6 Zeichen)", message)
        self.assertIn("step_field_mapping", message)
        self.assertNotIn("Aktion", message)
        self.assertNotIn("Ergebnis", message)

    def test_failed_update_contains_server_response_and_payload_shape(self) -> None:
        update_response = self.response(
            400,
            '{"errorMessages":["Ungültiges Step-Feld"]}',
            {"X-Request-ID": "request-400"},
        )
        self.client._session.put = Mock(return_value=update_response)

        with self.assertRaises(JiraApiError) as raised:
            self.client.update_test_steps("TEST-2", [self.step])

        message = str(raised.exception)
        self.assertIn("HTTP 400", message)
        self.assertIn("request-400", message)
        self.assertIn("Ungültiges Step-Feld", message)
        self.assertIn("Step 1", message)


if __name__ == "__main__":
    unittest.main()
