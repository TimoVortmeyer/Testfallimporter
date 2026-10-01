"""Datenmodelle für Testfälle, Testschritte und Screenshots."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import json
import re
from copy import deepcopy
from typing import Any

from jsonschema import Draft202012Validator


class TestCaseValidationError(Exception):
    """Wird geworfen, wenn die Eingabe-JSON nicht dem erwarteten Schema entspricht."""


@dataclass
class TestStep:
    action: str
    system: str
    data: str = ""
    expected_result: str = ""
    tester: str = ""
    attachments: list[str] = field(default_factory=list)

    @staticmethod
    def from_dict(raw: dict[str, Any], index: int) -> "TestStep":
        return TestStep(
            system=raw.get("system", ""),
            action=raw["action"],
            data=raw.get("data", ""),
            expected_result=raw.get("expected_result", ""),
            tester=raw.get("tester", ""),
            attachments=raw.get("attachments", []),
        )


@dataclass
class TestCase:
    summary: str
    description: str = ""
    repository_path: str | None = None
    labels: list[str] = field(default_factory=list)
    components: list[str] = field(default_factory=list)
    custom_fields: dict[str, Any] = field(default_factory=dict)
    screenshots: list[str] = field(default_factory=list)
    steps: list[TestStep] = field(default_factory=list)

    @staticmethod
    def from_dict(raw: dict[str, Any]) -> "TestCase":
        steps = [
            TestStep.from_dict(step_raw, i + 1)
            for i, step_raw in enumerate(raw.get("steps", []))
        ]
        return TestCase(
            summary=raw["summary"],
            description=raw.get("description", ""),
            repository_path=raw.get("repository_path"),
            labels=raw.get("labels", []),
            components=raw.get("components", []),
            custom_fields=raw.get("custom_fields", {}),
            screenshots=raw.get("screenshots", []),
            steps=steps,
        )

    def all_screenshot_filenames(self) -> set[str]:
        """Liest alle Wiki-Markup-Bildreferenzen aus den Testfalltexten."""
        names = set(re.findall(r"!([^!]+)!", self.description))
        names.update(self.screenshots)
        texts = []
        for step in self.steps:
            texts.extend((step.system, step.action, step.data, step.expected_result, step.tester))
        names.update(
            filename
            for text in texts
            for filename in re.findall(r"!([^!]+)!", text)
        )
        for step in self.steps:
            names.update(step.attachments)
        return names

    def issue_screenshot_filenames(self) -> set[str]:
        """Dateien, die als Anhänge am Jira-Test-Issue gespeichert werden."""
        names = set(self.screenshots)
        names.update(re.findall(r"!([^!]+)!", self.description))
        return names


def load_testcases(
    testcases_dir: Path,
    schema_path: Path,
    required_step_fields: list[str] | None = None,
    testcase_filename: str = "testcase.json",
    screenshots_dirname: str = "screenshots",
) -> list[tuple[TestCase, Path]]:
    with schema_path.open("r", encoding="utf-8") as f:
        schema = json.load(f)
    schema = deepcopy(schema)
    if required_step_fields is not None:
        schema["$defs"]["step"]["required"] = required_step_fields
    validator = Draft202012Validator(schema)
    loaded: list[tuple[TestCase, Path]] = []

    for json_path in sorted(testcases_dir.glob(f"*/{testcase_filename}")):
        with json_path.open("r", encoding="utf-8") as f:
            raw = json.load(f)
        errors = sorted(validator.iter_errors(raw), key=lambda error: list(error.path))
        if errors:
            details = "; ".join(
                f"{json_path}: {'/'.join(map(str, error.path)) or '<root>'}: {error.message}"
                for error in errors
            )
            raise TestCaseValidationError(details)
        testcase = TestCase.from_dict(raw)
        screenshots_dir = json_path.parent / screenshots_dirname
        for filename in testcase.all_screenshot_filenames():
            screenshot_path = Path(filename)
            if screenshot_path.name != filename:
                raise TestCaseValidationError(
                    f"{json_path}: Ungültige Screenshot-Referenz '{filename}'"
                )
            if not (screenshots_dir / filename).is_file():
                raise TestCaseValidationError(
                    f"{json_path}: Screenshot nicht gefunden: {screenshots_dir / filename}"
                )
        loaded.append((testcase, json_path.parent))

    if not loaded:
        raise TestCaseValidationError(
            f"Keine testcase.json unterhalb von '{testcases_dir}' gefunden"
        )
    return loaded
