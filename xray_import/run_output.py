"""Logdatei und Ergebnisdatei eines Importlaufs."""
from __future__ import annotations

import csv
import logging
from datetime import datetime
from pathlib import Path
from types import TracebackType

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(message)s"
RESULT_FIELDS = ("testfall", "ordner", "status", "issue_key", "link", "fehler")


def run_file_paths(output_dir: Path, now: datetime | None = None) -> tuple[Path, Path]:
    """Zeitgestempelte Pfade, damit Läufe sich nicht gegenseitig überschreiben."""
    stamp = (now or datetime.now()).strftime("%Y%m%d-%H%M%S")
    return output_dir / f"import_{stamp}.log", output_dir / f"import_ergebnis_{stamp}.csv"


def attach_log_file(path: Path) -> logging.Handler:
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(path, encoding="utf-8")
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    root = logging.getLogger()
    root.addHandler(handler)
    if root.getEffectiveLevel() > logging.INFO:
        root.setLevel(logging.INFO)
    return handler


def detach_log_file(handler: logging.Handler) -> None:
    logging.getLogger().removeHandler(handler)
    handler.close()


class ResultWriter:
    """Schreibt je Testfall eine Zeile; jede Zeile wird sofort gespeichert."""

    def __init__(self, path: Path, jira_base_url: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._browse_url = f"{jira_base_url.rstrip('/')}/browse/"
        self._file = path.open("w", encoding="utf-8-sig", newline="")
        self._writer = csv.DictWriter(self._file, fieldnames=RESULT_FIELDS, delimiter=";")
        self._writer.writeheader()
        self._file.flush()
        self.created = 0
        self.failed = 0

    def success(self, testcase: str, folder: str, issue_key: str) -> None:
        self.created += 1
        self._write(testcase, folder, "angelegt", issue_key, "")

    def failure(self, testcase: str, folder: str, error: str, issue_key: str | None = None) -> None:
        self.failed += 1
        self._write(testcase, folder, "fehler", issue_key or "", error)

    def _write(self, testcase: str, folder: str, status: str, issue_key: str, error: str) -> None:
        self._writer.writerow(
            {
                "testfall": testcase,
                "ordner": folder,
                "status": status,
                "issue_key": issue_key,
                "link": f"{self._browse_url}{issue_key}" if issue_key else "",
                "fehler": error,
            }
        )
        self._file.flush()

    def close(self) -> None:
        self._file.close()

    def __enter__(self) -> ResultWriter:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()
