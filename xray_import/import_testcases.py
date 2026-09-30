"""Hauptskript: liest Testfälle aus JSON, legt sie in Jira/Xray an und hängt Screenshots an.

Nutzung:
    JIRA_PAT=xxxxx python -m xray_import.import_testcases
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import requests

from .config import load_config, load_import_settings
from .jira_client import JiraApiError, JiraClient
from .models import TestCase, TestCaseValidationError, load_testcases
from .xray_client import XrayApiError, XrayClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


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
    )
    logger.info("Test-Issue angelegt: %s (%s)", issue_key, testcase.summary)

    for filename in sorted(testcase.issue_screenshot_filenames()):
        jira.upload_attachment(issue_key, screenshots_dir / filename)
        logger.info("  Screenshot hochgeladen: %s", filename)

    xray.upload_step_attachments(issue_key, testcase.steps, screenshots_dir)
    for step in testcase.steps:
        for filename in step.attachments:
            logger.info("  Step-Attachment hochgeladen: %s", filename)

    return issue_key


def run(config_path: Path) -> int:
    try:
        with config_path.open("r", encoding="utf-8") as f:
            import_config = json.load(f)
        settings = load_import_settings(config_path)
        testcases_dir = Path(settings["testcases_dir"])
        schema_path = Path(settings["schema_path"])
        testcases = load_testcases(
            testcases_dir,
            schema_path,
            settings.get("required_step_fields"),
            str(settings["testcase_filename"]),
            str(settings["screenshots_dirname"]),
        )
        config = load_config(config_path)
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
    had_error = False
    for testcase, testcase_dir in testcases:
        try:
            screenshots_dir = testcase_dir / str(settings["screenshots_dirname"])
            key = import_testcase(testcase, jira, xray, screenshots_dir)
            created_keys.append(key)
        except (
            JiraApiError,
            XrayApiError,
            FileNotFoundError,
            requests.RequestException,
        ) as exc:
            had_error = True
            logger.error(
                "Fehler bei Testfall '%s' (%s): %s: %s",
                testcase.summary,
                testcase_dir / str(settings["testcase_filename"]),
                type(exc).__name__,
                exc,
            )

    logger.info("Fertig. Angelegte Test-Issues: %s", ", ".join(created_keys) or "keine")
    return 1 if had_error else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Import von Testfällen nach Jira/Xray")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config/import_config.json"),
        help="Zentrale Import-Konfiguration",
    )
    parser.add_argument(
        "--schema",
        type=Path,
        default=None,
        help="Optionales Überschreiben des in der Konfiguration angegebenen JSON Schemas",
    )
    args = parser.parse_args()
    if args.schema is not None:
        with args.config.open("r", encoding="utf-8") as f:
            import_config = json.load(f)
        import_config["schema_path"] = str(args.schema)
        temporary_config = args.config.with_name(".import_config.runtime.json")
        temporary_config.write_text(json.dumps(import_config), encoding="utf-8")
        try:
            return run(temporary_config)
        finally:
            temporary_config.unlink(missing_ok=True)
    return run(args.config)


if __name__ == "__main__":
    sys.exit(main())
