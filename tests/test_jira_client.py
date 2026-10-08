from __future__ import annotations

import unittest
from unittest.mock import Mock

import requests

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
            repository_path_custom_field="customfield_15909",
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

    def test_issue_without_steps_skips_manual_steps(self) -> None:
        self.client._session.post = Mock(
            return_value=self.response(201, "", json_body={"key": "TEST-9"})
        )
        self.client._session.put = Mock()

        key = self.client.create_test_issue(
            summary="Ohne Schritte",
            description="",
            labels=[],
            components=[],
            custom_fields={},
            steps=[],
        )

        self.assertEqual(key, "TEST-9")
        fields = self.client._session.post.call_args.kwargs["json"]["fields"]
        self.assertNotIn("customfield_15903", fields)
        self.client._session.put.assert_not_called()

    def test_repository_path_is_sent_and_verified(self) -> None:
        repository_path = "/03.02 Einkaufsverwaltung/03.02.001 Pflege Einkaufskonditionen"
        self.client._session.post = Mock(
            return_value=self.response(201, "", json_body={"key": "TEST-3"})
        )
        self.client._session.get = Mock(
            return_value=self.response(
                200, "", json_body={"fields": {"customfield_15909": repository_path}}
            )
        )
        self.client.update_test_steps = Mock()

        key = self.client.create_test_issue(
            summary="Referenztest",
            description="",
            labels=[],
            components=[],
            custom_fields={},
            steps=[self.step],
            repository_path=repository_path,
        )

        self.assertEqual(key, "TEST-3")
        fields = self.client._session.post.call_args.kwargs["json"]["fields"]
        self.assertEqual(fields["customfield_15909"], repository_path)
        self.client._session.get.assert_called_once_with(
            "https://jira.example.test/rest/api/2/issue/TEST-3",
            params={"fields": "customfield_15909"},
            timeout=(10, 60),
        )

    def test_unsaved_repository_path_reports_created_issue(self) -> None:
        self.client._session.post = Mock(
            return_value=self.response(201, "", json_body={"key": "TEST-4"})
        )
        self.client._session.get = Mock(
            return_value=self.response(200, "", json_body={"fields": {"customfield_15909": None}})
        )
        self.client.update_test_steps = Mock()
        with self.assertRaisesRegex(JiraApiError, "wurde nicht gespeichert"):
            self.client.create_test_issue(
                summary="Referenztest",
                description="",
                labels=[],
                components=[],
                custom_fields={},
                steps=[self.step],
                repository_path="/Bereich/Test",
            )
        self.client.update_test_steps.assert_not_called()

    def test_conflicting_repository_fields_do_not_create_issue(self) -> None:
        self.client._session.post = Mock()
        with self.assertRaisesRegex(JiraApiError, "widerspricht"):
            self.client.create_test_issue(
                summary="Referenztest",
                description="",
                labels=[],
                components=[],
                custom_fields={"customfield_15909": "/Anderer/Pfad"},
                steps=[self.step],
                repository_path="/Bereich/Test",
            )
        self.client._session.post.assert_not_called()

    def test_reporter_email_is_resolved_and_sent_as_reporter(self) -> None:
        self.client._session.get = Mock(
            return_value=self.response(
                200,
                "",
                json_body=[
                    {
                        "name": "5662440",
                        "emailAddress": "timo.vortmeyer@example.test",
                    }
                ],
            )
        )
        self.client._session.post = Mock(
            return_value=self.response(201, "", json_body={"key": "TEST-5"})
        )
        self.client.update_test_steps = Mock()

        key = self.client.create_test_issue(
            summary="Referenztest",
            description="",
            labels=[],
            components=[],
            custom_fields={},
            steps=[self.step],
            reporter_email="timo.vortmeyer@example.test",
        )

        self.assertEqual(key, "TEST-5")
        self.client._session.get.assert_called_once_with(
            "https://jira.example.test/rest/api/2/user/search",
            params={"username": "timo.vortmeyer@example.test"},
            timeout=(10, 60),
        )
        fields = self.client._session.post.call_args.kwargs["json"]["fields"]
        self.assertEqual(fields["reporter"], {"name": "5662440"})

    def test_create_issue_does_not_retry_ambiguous_connection_reset(self) -> None:
        self.client._session.post = Mock(
            side_effect=requests.exceptions.ConnectionError("connection reset")
        )

        with self.assertRaisesRegex(JiraApiError, "(?i)unklar"):
            self.client.create_test_issue(
                summary="Referenztest",
                description="",
                labels=[],
                components=[],
                custom_fields={},
                steps=[self.step],
            )

        self.client._session.post.assert_called_once()

    def test_reporter_email_without_exact_match_falls_back_to_pat_user(self) -> None:
        self.client._session.get = Mock(
            side_effect=[
                self.response(
                    200,
                    "",
                    json_body={
                        "name": "pat-user",
                        "emailAddress": "pat@example.test",
                    },
                ),
                self.response(
                    200,
                    "",
                    json_body=[{"name": "5662440", "emailAddress": "other@example.test"}],
                ),
            ]
        )
        self.client._session.post = Mock(
            side_effect=[
                self.response(201, "", json_body={"key": "TEST-7"}),
                self.response(201, "", json_body={"id": "comment-1"}),
            ]
        )
        self.client.update_test_steps = Mock()

        self.client.get_pat_email()
        key = self.client.create_test_issue(
            summary="Referenztest",
            description="",
            labels=[],
            components=[],
            custom_fields={},
            steps=[self.step],
            reporter_email="requested@example.test",
        )

        self.assertEqual(key, "TEST-7")
        fields = self.client._session.post.call_args_list[0].kwargs["json"]["fields"]
        self.assertEqual(fields["reporter"], {"name": "pat-user"})
        self.client.add_import_comment(key, "08.10.2026 12:34:56", "TFB_03.docx")
        comments = self.client._session.post.call_args_list[1:]
        self.assertEqual(len(comments), 1)
        self.assertEqual(self.client._session.post.call_count, 2)
        self.assertEqual(
            comments[0].kwargs["json"]["body"],
            "Importiert von: pat@example.test\nImportzeitstempel: 08.10.2026 12:34:56\n"
            r"Originalworddokument: TFB\_03",
        )

    def test_ambiguous_reporter_email_does_not_create_issue(self) -> None:
        matching_user = {"name": "user", "emailAddress": "same@example.test"}
        self.client._session.get = Mock(
            return_value=self.response(200, "", json_body=[matching_user, matching_user])
        )
        self.client._session.post = Mock()

        with self.assertRaisesRegex(JiraApiError, "nicht eindeutig"):
            self.client.create_test_issue(
                summary="Referenztest",
                description="",
                labels=[],
                components=[],
                custom_fields={},
                steps=[self.step],
                reporter_email="same@example.test",
            )
        self.client._session.post.assert_not_called()

    def test_import_comment_contains_authenticated_user_email(self) -> None:
        email = "timo.vortmeyer@example.test"
        self.client._session.get = Mock(
            return_value=self.response(200, "", json_body={"emailAddress": email})
        )
        self.client._session.post = Mock(
            return_value=self.response(201, "", json_body={"id": "comment-1"})
        )

        self.client.get_pat_email()
        self.client.add_import_comment("TEST-6", "08.10.2026 12:34:56")

        self.client._session.get.assert_called_once_with(
            "https://jira.example.test/rest/api/2/myself",
            timeout=(10, 60),
        )
        self.client._session.post.assert_called_once()
        call = self.client._session.post.call_args
        self.assertEqual(
            call.args[0],
            "https://jira.example.test/rest/api/2/issue/TEST-6/comment",
        )
        body = call.kwargs["json"]["body"]
        self.assertEqual(body, f"Importiert von: {email}\nImportzeitstempel: 08.10.2026 12:34:56")

    def test_import_comment_filename_endings_and_prepared_doc(self) -> None:
        self.client._pat_email = "pat@example.test"
        for filename, expected in (
            (r"C:\private\TFB_1.docx", r"TFB\_1"),
            (r"C:\private\TFB_2.doc", r"TFB\_2"),
            (r"C:\prepared\TFB_3.doc.docx", r"TFB\_3"),
            (r"C:\prepared\TFB_3.v2.docx", r"TFB\_3.v2"),
            (r"C:\private\TFB_[one]*<A>.docx", r"TFB\_\[one\]\*\<A\>"),
            ("TFB_Rückverfolgung_Ä.docx", r"TFB\_Rückverfolgung\_Ä"),
        ):
            with self.subTest(filename=filename):
                self.client._session.post = Mock(
                    return_value=self.response(201, "", json_body={"id": "comment"})
                )
                self.client.add_import_comment("TEST-8", "08.10.2026 12:34:56", filename)
                body = self.client._session.post.call_args.kwargs["json"]["body"]
                self.assertEqual(body.splitlines()[-1], f"Originalworddokument: {expected}")
                self.assertNotIn("private", body)

    def test_import_comment_without_legacy_source_has_only_existing_two_lines(self) -> None:
        email = "timo.vortmeyer@example.test"
        self.client._pat_email = email
        self.client._session.post = Mock(
            return_value=self.response(201, "", json_body={"id": "comment"})
        )
        self.client.add_import_comment("TEST-9", "08.10.2026 12:34:56")
        self.assertEqual(
            self.client._session.post.call_args.kwargs["json"]["body"],
            f"Importiert von: {email}\nImportzeitstempel: 08.10.2026 12:34:56",
        )

    def test_missing_authenticated_user_email_fails(self) -> None:
        self.client._session.get = Mock(
            return_value=self.response(200, "", json_body={"displayName": "Tester"})
        )

        with self.assertRaisesRegex(JiraApiError, "E-Mail-Adresse des PAT-Benutzers"):
            self.client.get_pat_email()


if __name__ == "__main__":
    unittest.main()
