"""Wrapper um die Xray Server/DC REST API zum Anlegen manueller Testschritte."""
from __future__ import annotations

import base64
import logging
from pathlib import Path
from typing import Any

import requests

from .config import Config
from .diagnostics import response_diagnostics
from .models import TestStep

logger = logging.getLogger(__name__)


class XrayApiError(Exception):
    """Wird bei einer fehlgeschlagenen Xray-API-Antwort geworfen."""


class XrayClient:
    def __init__(self, config: Config):
        self._config = config
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {config.personal_access_token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            }
        )
        self._session.verify = config.verify_ssl

    def preflight(self) -> None:
        """Prüft, ob der konfigurierte Xray-REST-Endpunkt erreichbar ist."""
        response = self._session.get(
            f"{self._config.jira_base_url}/rest/raven/{self._config.xray_api_version}"
            "/api/settings/teststepstatuses",
            timeout=self._config.request_timeout,
        )
        if response.status_code != 200:
            raise XrayApiError(
                f"Xray-API {self._config.xray_api_version} nicht erreichbar "
                f"({response_diagnostics(response)})"
            )
        logger.info("Xray-Preflight erfolgreich: API %s", self._config.xray_api_version)

    def upload_step_attachments(
        self,
        test_issue_key: str,
        steps: list[TestStep],
        screenshots_dir: Path,
    ) -> None:
        """Hängt die in den Steps genannten Dateien direkt an Xray-Steps."""
        if not any(step.attachments for step in steps):
            return

        response = self._session.get(
            f"{self._config.jira_base_url}/rest/raven/{self._config.xray_api_version}/api/test/"
            f"{test_issue_key}/step",
            timeout=self._config.request_timeout,
        )
        if response.status_code != 200:
            raise XrayApiError(
                f"Steps für {test_issue_key} konnten nicht gelesen werden "
                f"({response_diagnostics(response)})"
            )

        response_body = response.json()
        if isinstance(response_body, dict):
            step_items = response_body.get("value", [])
        elif isinstance(response_body, list):
            step_items = response_body
        else:
            step_items = []
        step_ids = {item.get("index"): item.get("id") for item in step_items}
        for step_index, step in enumerate(steps, start=1):
            step_id = step_ids.get(step_index)
            if not step.attachments or not step_id:
                if step.attachments:
                    raise XrayApiError(
                        f"Xray-Step {step_index} bei {test_issue_key} wurde nicht gefunden"
                    )
                continue
            for filename in step.attachments:
                file_path = screenshots_dir / filename
                with file_path.open("rb") as file_handle:
                    payload: dict[str, Any] = {
                        "data": base64.b64encode(file_handle.read()).decode("ascii"),
                        "filename": filename,
                        "contentType": "image/png",
                    }
                upload_response = self._session.post(
                    f"{self._config.jira_base_url}/rest/raven/{self._config.xray_api_version}/api/test/"
                    f"{test_issue_key}/step/{step_id}",
                    json={"attachments": {"add": [payload]}},
                    timeout=self._config.request_timeout,
                )
                if upload_response.status_code not in (200, 201):
                    raise XrayApiError(
                        f"Attachment '{filename}' konnte nicht an Step {step_index} "
                        f"von {test_issue_key} angehängt werden "
                        f"({response_diagnostics(upload_response)})"
                    )
