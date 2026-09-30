"""Sichere, kompakte Diagnoseinformationen für Jira-/Xray-Antworten."""
from __future__ import annotations

import requests


def response_diagnostics(response: requests.Response) -> str:
    body = response.text.strip() or "<leer>"
    if len(body) > 1000:
        body = f"{body[:1000]}..."
    request_id = next(
        (
            response.headers[name]
            for name in (
                "X-AREQUESTID",
                "X-Request-ID",
                "X-Atlassian-Request-ID",
            )
            if name in response.headers
        ),
        "nicht geliefert",
    )
    return f"HTTP {response.status_code}, Request-ID: {request_id}, Antwort: {body}"
