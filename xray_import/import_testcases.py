"""Hauptskript: liest Testfälle aus JSON, legt sie in Jira/Xray an und hängt Screenshots an.

Nutzung:
    JIRA_PAT=xxxxx python -m xray_import.import_testcases
"""
from __future__ import annotations

import argparse
import getpass
import json
import logging
import sys
from pathlib import Path

import requests

from .config import load_config, load_import_settings
from .jira_client import JiraApiError, JiraClient
from .models import TestCase, TestCaseValidationError, load_testcases
from .progress import ImportProgress
from .run_output import LOG_FORMAT, ResultWriter, attach_log_file, detach_log_file, run_file_paths
from .xray_client import XrayApiError, XrayClient

logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger(__name__)

IMPORT_ERRORS = (JiraApiError, XrayApiError, FileNotFoundError, requests.RequestException)


class PartialImportError(Exception):
    """Das Issue wurde angelegt, ein späterer Importschritt ist aber fehlgeschlagen."""

    def __init__(self, issue_key: str, cause: Exception) -> None:
        super().__init__(
            f"Issue {issue_key} wurde angelegt, der Import ist aber unvollständig: "
            f"{type(cause).__name__}: {cause}"
        )
        self.issue_key = issue_key


def import_testcase(
    testcase: TestCase,
    jira: JiraClient,
    xray: XrayClient,
    screenshots_dir: Path,
) -> str:
    """Legt einen einzelnen Testfall inkl. Steps und Screenshots an. Gibt den Issue-Key zurück."""
    issue_key = jira.create_test_issue(
        summary=testcase.summary,
        description=testcase.description,
        labels=testcase.labels,
        components=testcase.components,
        custom_fields=testcase.custom_fields,
        steps=testcase.steps,
        repository_path=testcase.repository_path,
        reporter_email=testcase.reporter_email,
    )
    logger.info("Test-Issue angelegt: %s (%s)", issue_key, testcase.summary)

    try:
        for filename in sorted(testcase.issue_screenshot_filenames()):
            jira.upload_attachment(issue_key, screenshots_dir / filename)
            logger.info("  Screenshot hochgeladen: %s", filename)

        xray.upload_step_attachments(issue_key, testcase.steps, screenshots_dir)
        for step in testcase.steps:
            for filename in step.attachments:
                logger.info("  Step-Attachment hochgeladen: %s", filename)

        jira.add_import_comment(issue_key)
    except IMPORT_ERRORS as exc:
        raise PartialImportError(issue_key, exc) from exc
    logger.info("  Importkommentar gesetzt: %s", issue_key)
    return issue_key


def run(config_path: Path, overrides: dict[str, object] | None = None) -> int:
    try:
        settings = load_import_settings(config_path, overrides)
    except (KeyError, OSError, json.JSONDecodeError) as exc:
        logger.error("Konfigurations-/Eingabefehler: %s", exc)
        return 1
    log_path, result_path = run_file_paths(Path(str(settings.get("output_dir", "output"))))
    try:
        handler = attach_log_file(log_path)
    except OSError as exc:
        logger.error("Logdatei '%s' konnte nicht angelegt werden: %s", log_path, exc)
        return 1
    try:
        logger.info("Logdatei: %s", log_path)
        return _run(config_path, overrides, result_path)
    finally:
        detach_log_file(handler)


def _run(config_path: Path, overrides: dict[str, object] | None, result_path: Path) -> int:
    try:
        settings = load_import_settings(config_path, overrides)
        testcases_dir = Path(settings["testcases_dir"])
        schema_path = Path(settings["schema_path"])
        testcases = load_testcases(
            testcases_dir,
            schema_path,
            settings.get("required_step_fields"),
            str(settings["testcase_filename"]),
            str(settings["screenshots_dirname"]),
        )
        config = load_config(config_path, overrides)
    except (KeyError, OSError, json.JSONDecodeError, TestCaseValidationError, RuntimeError) as exc:
        logger.error("Konfigurations-/Eingabefehler: %s", exc)
        return 1

    jira = JiraClient(config)
    xray = XrayClient(config)
    try:
        jira.preflight()
        xray.preflight()
    except (JiraApiError, XrayApiError, requests.RequestException) as exc:
        logger.error("Preflight fehlgeschlagen: %s", exc)
        return 1
    created_keys: list[str] = []
    try:
        results = ResultWriter(result_path, config.jira_base_url)
    except OSError as exc:
        logger.error("Ergebnisdatei '%s' konnte nicht angelegt werden: %s", result_path, exc)
        return 1
    progress = ImportProgress(len(testcases))
    progress.update(0)
    with results:
        for position, (testcase, testcase_dir) in enumerate(testcases, start=1):
            try:
                screenshots_dir = testcase_dir / str(settings["screenshots_dirname"])
                key = import_testcase(testcase, jira, xray, screenshots_dir)
                created_keys.append(key)
                results.success(testcase.summary, testcase_dir.name, key)
                status = key
            except (PartialImportError, *IMPORT_ERRORS) as exc:
                error = f"{type(exc).__name__}: {exc}"
                logger.error(
                    "Fehler bei Testfall '%s' (%s): %s",
                    testcase.summary,
                    testcase_dir / str(settings["testcase_filename"]),
                    error,
                )
                results.failure(testcase.summary, testcase_dir.name, error, getattr(exc, "issue_key", None))
                status = "Fehler"
            progress.update(position, current=testcase_dir.name, status=status)

    logger.info("Fertig. Angelegte Test-Issues: %s", ", ".join(created_keys) or "keine")
    logger.info(
        "Ergebnis: %d angelegt, %d fehlgeschlagen. Ergebnisdatei: %s",
        results.created,
        results.failed,
        results.path,
    )
    return 1 if results.failed else 0


# (CLI-Option, Konfigurationsschlüssel, Hilfetext)
CONFIG_OVERRIDE_OPTIONS = (
    ("--jira-base-url", "jira_base_url", "Basis-URL der Jira-Instanz"),
    ("--project-profile", "project_profile", "Pfad zum Projektprofil"),
    ("--testcases-dir", "testcases_dir", "Verzeichnis mit den Testfall-Ordnern"),
    ("--testcase-filename", "testcase_filename", "Dateiname der Testfall-JSON"),
    ("--screenshots-dirname", "screenshots_dirname", "Name des Screenshot-Ordners"),
    ("--schema", "schema_path", "Pfad zum JSON Schema der Testfälle"),
    ("--project-key", "project_key", "Jira-Projektschlüssel"),
    ("--test-issue-type", "test_issue_type", "Name des Test-Issue-Typs"),
    ("--output-dir", "output_dir", "Ordner für Logdatei und Ergebnisdatei (CSV)"),
)
PROMPT_FOR_PAT = object()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Import von Testfällen nach Jira/Xray",
        epilog="Kommandozeilenwerte haben Vorrang vor Umgebungsvariablen "
        "und Werten aus der Konfigurationsdatei.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config/import_config.json"),
        help="Zentrale Import-Konfiguration",
    )
    for option, key, help_text in CONFIG_OVERRIDE_OPTIONS:
        parser.add_argument(
            option,
            dest=key,
            default=None,
            help=f"{help_text} (überschreibt '{key}' aus der Konfiguration)",
        )
    parser.add_argument(
        "--pat",
        nargs="?",
        const=PROMPT_FOR_PAT,
        default=None,
        help="Jira Personal Access Token (überschreibt JIRA_PAT). Ohne Wert "
        "wird das Token verdeckt abgefragt; ein direkt angegebener Wert ist "
        "im Shell-Verlauf und in der Prozessliste sichtbar.",
    )
    args = parser.parse_args()
    overrides: dict[str, object] = {
        key: getattr(args, key)
        for _, key, _ in CONFIG_OVERRIDE_OPTIONS
        if getattr(args, key) is not None
    }
    if args.pat == PROMPT_FOR_PAT:
        overrides["personal_access_token"] = getpass.getpass("Jira PAT: ")
    elif args.pat is not None:
        logger.warning(
            "PAT wurde als Argument übergeben und ist im Shell-Verlauf sichtbar. "
            "Sicherer: --pat ohne Wert (verdeckte Eingabe) oder JIRA_PAT."
        )
        overrides["personal_access_token"] = args.pat
    return run(args.config, overrides)


if __name__ == "__main__":
    sys.exit(main())
