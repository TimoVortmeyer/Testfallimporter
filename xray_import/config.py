"""Zentrale Konfiguration für den Xray-Import.

Sensible Werte (PAT) kommen aus ``--pat`` oder der Umgebungsvariable JIRA_PAT,
niemals aus Konfigurationsdateien.
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
    request_timeout: int = 60
    connect_timeout: int = 10
    step_field_mapping: dict[str, str] = field(default_factory=lambda: {
        "system": "System/Komponente",
        "action": "Action",
        "expected_result": "Expected Result",
        "tester": "Tester",
    })
    xray_api_version: str = "1.0"
    repository_path_custom_field: str | None = None

    @property
    def request_timeout_pair(self) -> tuple[int, int]:
        """Connect-/Response-Timeout; Response-Zeit bleibt unabhängig begrenzt auf 60 s."""
        return (min(max(self.connect_timeout, 1), 10), min(max(self.request_timeout, 1), 60))


def load_import_settings(
    import_config_path: Path,
    overrides: dict[str, object] | None = None,
) -> dict[str, object]:
    """Lädt Import-Konfiguration und Projektprofil; ``overrides`` haben Vorrang vor beiden."""
    overrides = overrides or {}
    with import_config_path.open("r", encoding="utf-8") as f:
        import_config = json.load(f)
    profile_path = Path(overrides.get("project_profile", import_config["project_profile"]))
    with profile_path.open("r", encoding="utf-8") as f:
        profile = json.load(f)
    return {**import_config, **profile, **overrides}


def _setting(
    settings: dict[str, object],
    overrides: dict[str, object],
    key: str,
    env_var: str,
) -> str:
    """Reihenfolge: Kommandozeile > Umgebungsvariable > Konfigurationsdatei."""
    if key in overrides:
        return str(overrides[key])
    return os.environ.get(env_var, str(settings[key]))


def load_config(
    import_config_path: Path = Path("config/import_config.json"),
    overrides: dict[str, object] | None = None,
) -> Config:
    overrides = overrides or {}
    import_config = load_import_settings(import_config_path, overrides)

    base_url = _setting(import_config, overrides, "jira_base_url", "JIRA_BASE_URL")
    project_key = _setting(import_config, overrides, "project_key", "JIRA_PROJECT_KEY")
    test_issue_type = _setting(
        import_config, overrides, "test_issue_type", "JIRA_TEST_ISSUE_TYPE"
    )
    pat = overrides.get("personal_access_token") or os.environ.get("JIRA_PAT")

    if not pat:
        raise RuntimeError(
            "Kein Jira-PAT angegeben. Bitte --pat verwenden oder die "
            "Umgebungsvariable JIRA_PAT setzen."
        )

    return Config(
        jira_base_url=base_url.rstrip("/"),
        manual_steps_custom_field=import_config["manual_steps_custom_field"],
        test_type_custom_field=import_config["test_type_custom_field"],
        manual_test_type_value=import_config["manual_test_type_value"],
        project_key=project_key,
        test_issue_type=test_issue_type,
        personal_access_token=pat,
        request_timeout=int(import_config.get("request_timeout", 60)),
        connect_timeout=int(import_config.get("connect_timeout", 10)),
        step_field_mapping=import_config["step_field_mapping"],
        xray_api_version=import_config["xray_api_version"],
        repository_path_custom_field=import_config.get("repository_path_custom_field"),
    )
