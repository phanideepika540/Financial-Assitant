from __future__ import annotations

import logging
import time
from collections.abc import Callable
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import TypeVar

T = TypeVar("T")

_MAX_ATTEMPTS = 3
_MAX_RETRY_DELAY_SECONDS = 2.0
logger = logging.getLogger(__name__)


def retry_request(
    operation: Callable[[], T],
    *,
    is_retryable: Callable[[Exception], bool],
) -> T:
    for attempt in range(_MAX_ATTEMPTS):
        try:
            return operation()
        except Exception as exc:
            if attempt == _MAX_ATTEMPTS - 1 or not is_retryable(exc):
                raise
            logger.warning(
                "Transient provider request failure; retrying attempt %s/%s (%s)",
                attempt + 2,
                _MAX_ATTEMPTS,
                type(exc).__name__,
            )
            time.sleep(_retry_delay(exc, attempt))
    raise RuntimeError("Retry loop exited without returning or raising.")


def _retry_delay(exc: Exception, attempt: int) -> float:
    headers = getattr(exc, "headers", None)
    if headers is None:
        response = getattr(exc, "response", None)
        headers = getattr(response, "headers", None)
    retry_after = headers.get("Retry-After") if headers is not None else None
    if retry_after:
        try:
            delay = float(retry_after)
        except ValueError:
            try:
                retry_at = parsedate_to_datetime(retry_after)
                if retry_at.tzinfo is None:
                    retry_at = retry_at.replace(tzinfo=timezone.utc)
                delay = (retry_at - datetime.now(timezone.utc)).total_seconds()
            except (TypeError, ValueError, OverflowError):
                delay = 0.25 * (2**attempt)
    else:
        delay = 0.25 * (2**attempt)
    return max(0.0, min(delay, _MAX_RETRY_DELAY_SECONDS))
