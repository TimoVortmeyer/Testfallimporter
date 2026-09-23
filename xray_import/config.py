"""Zentrale Konfiguration für den Xray-Import.

Sensible Werte (PAT) werden ausschliesslich über Umgebungsvariablen gelesen,
niemals hier im Klartext hinterlegt.
"""
import os
import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Config:
    jira_base_url: str
    manual_steps_custom_field: str
    test_type_custom_field: str
    manual_test_type_value: str
    project_key: str
    test_issue_type: str
    personal_access_token: str
    verify_ssl: bool = True
    request_timeout: int = 30
    step_field_mapping: dict[str, str] = field(default_factory=lambda: {
        "system": "System/Komponente",
        "action": "Action",
        "data": "Data",
        "expected_result": "Expected Result",
        "tester": "Tester",
    })
    xray_api_version: str = "1.0"


def load_import_settings(import_config_path: Path) -> dict[str, object]:
    with import_config_path.open("r", encoding="utf-8") as f:
        import_config = json.load(f)
    profile_path = Path(import_config["project_profile"])
    with profile_path.open("r", encoding="utf-8") as f:
        profile = json.load(f)
    return {**import_config, **profile}


def load_config(import_config_path: Path = Path("config/import_config.json")) -> Config:
    import_config = load_import_settings(import_config_path)

    base_url = os.environ.get("JIRA_BASE_URL", import_config["jira_base_url"])
    project_key = os.environ.get("JIRA_PROJECT_KEY", import_config["project_key"])
    test_issue_type = os.environ.get(
        "JIRA_TEST_ISSUE_TYPE", import_config["test_issue_type"]
    )
    pat = os.environ.get("JIRA_PAT")

    if not pat:
        raise RuntimeError(
            "Umgebungsvariable JIRA_PAT ist nicht gesetzt. "
            "Bitte ein Personal Access Token aus Jira hinterlegen."
        )

    return Config(
        jira_base_url=base_url.rstrip("/"),
        manual_steps_custom_field=import_config["manual_steps_custom_field"],
        test_type_custom_field=import_config["test_type_custom_field"],
        manual_test_type_value=import_config["manual_test_type_value"],
        project_key=project_key,
        test_issue_type=test_issue_type,
        personal_access_token=pat,
        step_field_mapping=import_config["step_field_mapping"],
        xray_api_version=import_config["xray_api_version"],
    )
