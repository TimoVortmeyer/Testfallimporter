"""Schlanker Wrapper um die Jira REST API v2 (Issue anlegen, Attachments hochladen)."""
from __future__ import annotations

from pathlib import Path
from typing import Any
import logging

import requests

from .config import Config
from .models import TestStep

logger = logging.getLogger(__name__)


class JiraApiError(Exception):
    """Wird bei einer fehlgeschlagenen Jira-API-Antwort geworfen."""


class JiraClient:
    def __init__(self, config: Config):
        self._config = config
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
                f"({project_response.status_code}): {project_response.text}"
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
                    f"({type_response.status_code}): {type_response.text}"
                )
            issue_types = [issue_type.get("name") for issue_type in type_response.json()]
            logger.warning(
                "Jira-createmeta nicht verfügbar; Issue-Typ wird global geprüft"
            )
        else:
            raise JiraApiError(
                f"Issue-Typ {self._config.test_issue_type} konnte nicht geprüft werden "
                f"({meta_response.status_code}): {meta_response.text}"
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
                f"({fields_response.status_code}): {fields_response.text}"
            )
        field_ids = {field.get("id") for field in fields_response.json()}
        for field_id in (
            self._config.manual_steps_custom_field,
            self._config.test_type_custom_field,
        ):
            if field_id not in field_ids:
                raise JiraApiError(f"Konfiguriertes Jira-Feld nicht gefunden: {field_id}")

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
    ) -> str:
        """Legt einen neuen Test-Issue an und gibt den Issue-Key zurück."""
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
                f"Anlegen des Test-Issues fehlgeschlagen ({response.status_code}): {response.text}"
            )
        issue_key = response.json()["key"]
        self.update_test_steps(issue_key, steps)
        return issue_key

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
                f"({response.status_code}): {response.text}"
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
                f"({verify_response.status_code}): {verify_response.text}"
            )

        stored_field = verify_response.json().get("fields", {}).get(
            self._config.manual_steps_custom_field, {}
        )
        stored_steps = stored_field.get("steps", []) if isinstance(stored_field, dict) else []
        logger.info("Manual-Steps-Verifikation für %s: %d Schritt(e)", issue_key, len(stored_steps))
        if len(stored_steps) < len(steps):
            raise JiraApiError(
                f"Jira hat für {issue_key} nur {len(stored_steps)} von "
                f"{len(steps)} Manual-Step(s) gespeichert"
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
                f"({response.status_code}): {response.text}"
            )
