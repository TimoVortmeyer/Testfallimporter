"""Gemeinsame Session-Konfiguration mit begrenzten Retries für transiente Netzwerkfehler."""
from __future__ import annotations

import requests
from requests.adapters import HTTPAdapter
from urllib3.exceptions import MaxRetryError, ProtocolError, ReadTimeoutError
from urllib3.util.retry import Retry
import logging

MAX_RETRIES = 2
RETRY_STATUS_CODES = frozenset({502, 503, 504})
RETRYABLE_METHODS = frozenset({"HEAD", "GET", "PUT", "OPTIONS"})
logger = logging.getLogger(__name__)


class LoggingRetry(Retry):
    def increment(self, method=None, url=None, response=None, error=None, *_args, **_kwargs):
        if isinstance(error, ProtocolError):
            if method not in self.allowed_methods:
                raise error
            error = ReadTimeoutError(url, method, error)
        try:
            updated = super().increment(method, url, response, error, *_args, **_kwargs)
        except MaxRetryError:
            logger.warning("HTTP-Retry ausgeschöpft: %s %s (%s)", method, url, error or response)
            raise
        reason = error if error is not None else f"HTTP {response.status}"
        logger.warning(
            "HTTP-Retry: %s %s nach %s; verbleibende Wiederholungen: %s",
            method,
            url,
            reason,
            updated.total,
        )
        return updated


def create_retry_session() -> requests.Session:
    retry = LoggingRetry(
        total=MAX_RETRIES,
        connect=MAX_RETRIES,
        read=MAX_RETRIES,
        status=MAX_RETRIES,
        other=0,
        allowed_methods=RETRYABLE_METHODS,
        status_forcelist=RETRY_STATUS_CODES,
        backoff_factor=0.5,
        backoff_max=2,
        raise_on_status=False,
        respect_retry_after_header=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session = requests.Session()
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session