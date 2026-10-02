"""Schlanker Wrapper um die Jira REST API v2 (Issue anlegen, Attachments hochladen)."""
from __future__ import annotations

from pathlib import Path
from typing import Any
import logging

import requests

from .config import Config
from .diagnostics import response_diagnostics
from .models import TestStep

logger = logging.getLogger(__name__)


class JiraApiError(Exception):
    """Wird bei einer fehlgeschlagenen Jira-API-Antwort geworfen."""


class JiraClient:
    def __init__(self, config: Config):
        self._config = config
        self._pat_email: str | None = None
        self._pat_username: str | None = None
        self._reporter_fallback_email: str | None = None
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {config.personal_access_token}",
                "Accept": "application/json",
            }
        )
        self._session.verify = config.verify_ssl

    def preflight(self) -> None:
        """Prüft Zielprojekt, Issue-Typ und konfigurierte Jira-Felder."""
        project_response = self._session.get(
            f"{self._config.jira_base_url}/rest/api/2/project/{self._config.project_key}",
            timeout=self._config.request_timeout,
        )
        if project_response.status_code != 200:
            raise JiraApiError(
                f"Zielprojekt {self._config.project_key} nicht erreichbar "
                f"({response_diagnostics(project_response)})"
            )

        meta_response = self._session.get(
            f"{self._config.jira_base_url}/rest/api/2/issue/createmeta",
            params={
                "projectKeys": self._config.project_key,
                "expand": "projects.issuetypes",
            },
            timeout=self._config.request_timeout,
        )
        if meta_response.status_code == 200:
            projects = meta_response.json().get("projects", [])
            issue_types = [
                issue_type.get("name")
                for project in projects
                for issue_type in project.get("issuetypes", [])
            ]
        elif meta_response.status_code == 404:
            type_response = self._session.get(
                f"{self._config.jira_base_url}/rest/api/2/issuetype",
                timeout=self._config.request_timeout,
            )
            if type_response.status_code != 200:
                raise JiraApiError(
                    f"Issue-Typ {self._config.test_issue_type} konnte nicht geprüft werden "
                    f"({response_diagnostics(type_response)})"
                )
            issue_types = [issue_type.get("name") for issue_type in type_response.json()]
            logger.warning(
                "Jira-createmeta nicht verfügbar; Issue-Typ wird global geprüft"
            )
        else:
            raise JiraApiError(
                f"Issue-Typ {self._config.test_issue_type} konnte nicht geprüft werden "
                f"({response_diagnostics(meta_response)})"
            )
        if self._config.test_issue_type not in issue_types:
            raise JiraApiError(
                f"Issue-Typ '{self._config.test_issue_type}' ist im Projekt "
                f"'{self._config.project_key}' nicht verfügbar"
            )

        fields_response = self._session.get(
            f"{self._config.jira_base_url}/rest/api/2/field",
            timeout=self._config.request_timeout,
        )
        if fields_response.status_code != 200:
            raise JiraApiError(
                f"Jira-Felder konnten nicht geprüft werden "
                f"({response_diagnostics(fields_response)})"
            )
        field_ids = {field.get("id") for field in fields_response.json()}
        for field_id in (
            self._config.manual_steps_custom_field,
            self._config.test_type_custom_field,
            self._config.repository_path_custom_field,
        ):
            if field_id and field_id not in field_ids:
                raise JiraApiError(f"Konfiguriertes Jira-Feld nicht gefunden: {field_id}")

        self.get_pat_email()

        logger.info(
            "Jira-Preflight erfolgreich: Projekt %s, Issue-Typ %s",
            self._config.project_key,
            self._config.test_issue_type,
        )

    def create_test_issue(
        self,
        summary: str,
        description: str,
        labels: list[str],
        components: list[str],
        custom_fields: dict[str, Any],
        steps: list[TestStep],
        repository_path: str | None = None,
        reporter_email: str | None = None,
    ) -> str:
        """Legt einen neuen Test-Issue an und gibt den Issue-Key zurück."""
        self._reporter_fallback_email = None
        fields: dict[str, Any] = {
            "project": {"key": self._config.project_key},
            "issuetype": {"name": self._config.test_issue_type},
            "summary": summary,
            "description": description,
            "labels": labels,
        }
        if components:
            fields["components"] = [{"name": component} for component in components]
        fields.update(custom_fields)
        if repository_path is not None:
            field_id = self._config.repository_path_custom_field
            if not field_id:
                raise JiraApiError("Kein repository_path_custom_field im Projektprofil konfiguriert")
            if field_id in custom_fields and custom_fields[field_id] != repository_path:
                raise JiraApiError(
                    f"repository_path widerspricht custom_fields.{field_id}"
                )
            fields[field_id] = repository_path
        if reporter_email is not None:
            email = reporter_email.strip()
            if not email:
                raise JiraApiError("reporter_email darf nicht leer sein")
            fields["reporter"] = {"name": self._resolve_reporter(email)}
        fields.setdefault(
            self._config.test_type_custom_field,
            {"value": self._config.manual_test_type_value},
        )
        steps_value = self._steps_value(steps)
        fields[self._config.manual_steps_custom_field] = steps_value

        response = self._session.post(
            f"{self._config.jira_base_url}/rest/api/2/issue",
            json={"fields": fields},
            timeout=self._config.request_timeout,
        )
        if response.status_code != 201:
            raise JiraApiError(
                f"Anlegen des Test-Issues fehlgeschlagen ({response_diagnostics(response)})"
            )
        issue_key = response.json()["key"]
        if repository_path is not None:
            self.verify_repository_path(issue_key, repository_path)
        self.update_test_steps(issue_key, steps)
        return issue_key

    def _resolve_reporter(self, email: str) -> str:
        response = self._session.get(
            f"{self._config.jira_base_url}/rest/api/2/user/search",
            params={"username": email},
            timeout=self._config.request_timeout,
        )
        if response.status_code != 200:
            raise JiraApiError(
                "Reporter konnte über die E-Mail-Adresse nicht in Jira gesucht werden "
                f"({response_diagnostics(response)})"
            )

        users = response.json()
        matches = [
            user
            for user in users
            if isinstance(user, dict)
            and isinstance(user.get("emailAddress"), str)
            and user["emailAddress"].casefold() == email.casefold()
        ]
        if not matches:
            if not self._pat_username:
                raise JiraApiError(
                    "Reporter-E-Mail nicht auffindbar und Jira-Benutzername des PAT-Kontos "
                    "nicht verfügbar; Reporter kann nicht gesetzt werden"
                )
            logger.warning(
                "Reporter-E-Mail nicht exakt auffindbar; verwende PAT-Benutzer als Reporter"
            )
            self._reporter_fallback_email = email
            return self._pat_username
        if len(matches) > 1:
            raise JiraApiError(
                "Mehrere Jira-Benutzer haben dieselbe E-Mail-Adresse; Reporter ist nicht eindeutig"
            )
        username = matches[0].get("name")
        if not isinstance(username, str) or not username:
            raise JiraApiError(
                "Jira lieferte für den gefundenen Reporter keinen verwendbaren Benutzernamen"
            )
        return username

    def get_pat_email(self) -> str:
        response = self._session.get(
            f"{self._config.jira_base_url}/rest/api/2/myself",
            timeout=self._config.request_timeout,
        )
        if response.status_code != 200:
            raise JiraApiError(
                "E-Mail-Adresse des PAT-Benutzers konnte nicht abgefragt werden "
                f"({response_diagnostics(response)})"
            )
        user = response.json()
        email = user.get("emailAddress")
        if not isinstance(email, str) or not email.strip():
            raise JiraApiError(
                "E-Mail-Adresse des PAT-Benutzers ist in Jira nicht sichtbar; "
                "Import wird vor dem Anlegen von Issues abgebrochen"
            )
        self._pat_email = email.strip()
        username = user.get("name")
        self._pat_username = username.strip() if isinstance(username, str) and username.strip() else None
        return self._pat_email

    def add_import_comment(self, issue_key: str) -> None:
        if self._pat_email is None:
            raise JiraApiError(
                "E-Mail-Adresse des PAT-Benutzers wurde vor dem Import nicht abgefragt"
            )
        body = f"Importiert von: {self._pat_email}"
        self._post_comment(issue_key, body, "Importkommentar")
        if self._reporter_fallback_email is not None:
            fallback_body = (
                "Ersteller in Jira als User nicht gefunden. Emailadresse Ersteller: "
                f"{self._reporter_fallback_email}"
            )
            self._post_comment(issue_key, fallback_body, "Hinweis zum nicht gefundenen Ersteller")
            self._reporter_fallback_email = None

    def _post_comment(self, issue_key: str, body: str, comment_description: str) -> None:
        response = self._session.post(
            f"{self._config.jira_base_url}/rest/api/2/issue/{issue_key}/comment",
            json={"body": body},
            timeout=self._config.request_timeout,
        )
        if response.status_code != 201:
            raise JiraApiError(
                f"{comment_description} für bereits angelegten Issue {issue_key} konnte nicht "
                f"gesetzt werden ({response_diagnostics(response)}). "
                "Issue vor einem erneuten Import prüfen."
            )

    def verify_repository_path(self, issue_key: str, expected_path: str) -> None:
        field_id = self._config.repository_path_custom_field
        response = self._session.get(
            f"{self._config.jira_base_url}/rest/api/2/issue/{issue_key}",
            params={"fields": field_id},
            timeout=self._config.request_timeout,
        )
        if response.status_code != 200:
            raise JiraApiError(
                f"Repository-Pfad für angelegten Issue {issue_key} konnte nicht geprüft werden "
                f"({response_diagnostics(response)})"
            )
        stored_path = response.json().get("fields", {}).get(field_id)
        if stored_path != expected_path:
            raise JiraApiError(
                f"Repository-Pfad für angelegten Issue {issue_key} wurde nicht gespeichert "
                f"(Feld {field_id}). Jira/Xray muss das Feld beim Anlegen unterstützen; "
                "bitte den Issue vor einem erneuten Import prüfen."
            )

    def _steps_value(self, steps: list[TestStep]) -> dict[str, Any]:
        return {
            "steps": [
                {
                    "index": index,
                    "fields": self._step_fields(step),
                }
                for index, step in enumerate(steps, start=1)
            ]
        }

    def _step_fields(self, step: TestStep) -> dict[str, str]:
        mapping = self._config.step_field_mapping
        fields = {
            mapping["system"]: step.system,
            mapping["action"]: step.action,
            mapping["expected_result"]: step.expected_result,
        }
        if step.data and mapping.get("data"):
            fields[mapping["data"]] = step.data
        if step.tester and mapping.get("tester"):
            fields[mapping["tester"]] = step.tester
        return fields

    @staticmethod
    def _payload_diagnostics(steps_value: dict[str, Any]) -> str:
        details = []
        for item in steps_value["steps"]:
            fields = ", ".join(
                f"{name} ({len(value)} Zeichen)"
                for name, value in item["fields"].items()
            )
            details.append(f"Step {item['index']}: {fields}")
        return "; ".join(details)

    def update_test_steps(self, issue_key: str, steps: list[TestStep]) -> None:
        """Schreibt die Manual-Steps nach dem Issue-Create über Jira REST."""
        steps_value = self._steps_value(steps)
        response = self._session.put(
            f"{self._config.jira_base_url}/rest/api/2/issue/{issue_key}",
            json={
                "update": {
                    self._config.manual_steps_custom_field: [
                        {"set": steps_value}
                    ]
                }
            },
            timeout=self._config.request_timeout,
        )
        logger.info(
            "Manual-Steps-Update für %s: HTTP %s",
            issue_key,
            response.status_code,
        )
        logger.debug("Manual-Steps-Payload für %s: %s", issue_key, steps_value)
        if response.status_code not in (200, 204):
            raise JiraApiError(
                f"Schritte für {issue_key} konnten nicht gespeichert werden "
                f"({response_diagnostics(response)}). "
                f"Payload-Struktur: {self._payload_diagnostics(steps_value)}"
            )

        verify_response = self._session.get(
            f"{self._config.jira_base_url}/rest/api/2/issue/{issue_key}",
            params={"fields": self._config.manual_steps_custom_field},
            timeout=self._config.request_timeout,
        )
        logger.info(
            "Manual-Steps-Verifikation für %s: HTTP %s",
            issue_key,
            verify_response.status_code,
        )
        if verify_response.status_code != 200:
            raise JiraApiError(
                f"Schritte für {issue_key} konnten nicht verifiziert werden "
                f"({response_diagnostics(verify_response)})"
            )

        try:
            verify_body = verify_response.json()
        except requests.exceptions.JSONDecodeError as exc:
            raise JiraApiError(
                f"Jira lieferte bei der Verifikation von {issue_key} kein gültiges JSON "
                f"({response_diagnostics(verify_response)})"
            ) from exc

        stored_field = verify_body.get("fields", {}).get(
            self._config.manual_steps_custom_field, {}
        )
        stored_steps = stored_field.get("steps", []) if isinstance(stored_field, dict) else []
        logger.info("Manual-Steps-Verifikation für %s: %d Schritt(e)", issue_key, len(stored_steps))
        if len(stored_steps) < len(steps):
            xray_response = self._session.get(
                f"{self._config.jira_base_url}/rest/raven/"
                f"{self._config.xray_api_version}/api/test/{issue_key}/step",
                timeout=self._config.request_timeout,
            )
            raise JiraApiError(
                f"Jira/Xray hat für {issue_key} nur {len(stored_steps)} von "
                f"{len(steps)} Manual-Step(s) gespeichert. Das Jira-Update wurde akzeptiert "
                f"({response_diagnostics(response)}), aber das Manual-Steps-Feld "
                f"'{self._config.manual_steps_custom_field}' enthält danach zu wenige Schritte. "
                f"Xray-Gegenprüfung: {response_diagnostics(xray_response)}. "
                f"Gesendete Payload-Struktur: {self._payload_diagnostics(steps_value)}. "
                "Wahrscheinliche Ursache: Xray hat mindestens einen Feldnamen oder Feldwert "
                "des Step-Payloads abgelehnt. Jira Data Center liefert bei diesem Fehler "
                "häufig keinen konkreteren Fehlertext. Prüfe step_field_mapping und vergleiche "
                "die genannten Felder mit einem funktionierenden Referenztestfall."
            )

    def upload_attachment(self, issue_key: str, file_path: Path) -> None:
        """Hängt eine Datei als Attachment an einen bestehenden Issue."""
        if not file_path.is_file():
            raise FileNotFoundError(f"Screenshot nicht gefunden: {file_path}")

        with file_path.open("rb") as f:
            response = self._session.post(
                f"{self._config.jira_base_url}/rest/api/2/issue/{issue_key}/attachments",
                headers={"X-Atlassian-Token": "no-check"},
                files={"file": (file_path.name, f)},
                timeout=self._config.request_timeout,
            )
        if response.status_code != 200:
            raise JiraApiError(
                f"Upload von '{file_path.name}' an {issue_key} fehlgeschlagen "
                f"({response_diagnostics(response)})"
            )
