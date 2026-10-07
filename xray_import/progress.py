"""Fortschrittsanzeige für den Import.

Der Importer protokolliert je Testfall mehrere Logzeilen. Damit die Anzeige nicht
mit diesen Zeilen kollidiert, wird der Fortschritt als eigene Zeile ausgegeben
statt eine Zeile per Wagenrücklauf zu überschreiben.
"""
from __future__ import annotations

import sys
import time
from collections.abc import Callable
from typing import TextIO

_BAR_WIDTH = 24


class ImportProgress:
    def __init__(
        self,
        total: int,
        *,
        label: str = "Import",
        stream: TextIO | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.total = total
        self.label = label
        self._stream = stream or sys.stdout
        self._clock = clock
        self._started = clock()

    def update(self, completed: int, *, current: str = "", status: str = "") -> None:
        if self.total <= 0:
            return
        completed = min(max(completed, 0), self.total)
        elapsed = max(0.0, self._clock() - self._started)
        ratio = completed / self.total
        filled = round(_BAR_WIDTH * ratio)
        bar = "#" * filled + "-" * (_BAR_WIDTH - filled)
        if completed:
            estimated_total = elapsed / completed * self.total
            remaining = max(0.0, estimated_total - elapsed)
            estimates = f"Gesamt ~{_format_duration(estimated_total)} | Rest ~{_format_duration(remaining)}"
        else:
            estimates = "Gesamt --:-- | Rest --:--"
        line = (
            f"{self.label} [{bar}] {completed}/{self.total} ({ratio:.0%}) | "
            f"Laufzeit {_format_duration(elapsed)} | {estimates}"
        )
        details = " | ".join(part for part in (status, _shorten(current, 56)) if part)
        if details:
            line += f" | {details}"
        self._stream.write(line + "\n")
        self._stream.flush()


def _format_duration(seconds: float) -> str:
    total_seconds = max(0, round(seconds))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


def _shorten(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return f"…{value[-(limit - 1):]}"
