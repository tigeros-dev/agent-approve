"""Approval requests.

A request is a plain JSON object::

    {"id": "...", "action": "free text", "target": "/path/to/file",
     "sha256": "<sha256 of the target content when the request was made>",
     "created": "2026-01-01T00:00:00Z"}

The action is free text for the human to read. Nothing in it is ever treated
as evidence of an approval.
"""
from __future__ import annotations

import hashlib
import os
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

FIELDS = ("id", "action", "target", "sha256", "created")
_ID_PATTERN = re.compile(r"[A-Za-z0-9_-]{1,64}")
_SHA_PATTERN = re.compile(r"[0-9a-f]{64}")


class InvalidRequest(ValueError):
    """The request does not have the expected shape."""


def utc_text(at: float) -> str:
    """Format Unix seconds as an ISO 8601 UTC timestamp."""
    return datetime.fromtimestamp(at, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def file_sha256(path) -> str:
    """Return the sha256 hex digest of the file at ``path``."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def create(action: str, target, now: Optional[float] = None) -> dict:
    """Create a request for ``action`` on the file ``target``.

    The checksum is taken from the file as it is right now; this is the
    content the human is asked to approve.
    """
    if not isinstance(action, str) or not action.strip():
        raise InvalidRequest("action must be a non-empty string")
    path = os.path.abspath(os.fspath(target))
    if not Path(path).is_file():
        raise InvalidRequest("target is not a regular file")
    return {
        "id": uuid.uuid4().hex,
        "action": action,
        "target": path,
        "sha256": file_sha256(path),
        "created": utc_text(time.time() if now is None else now),
    }


def validate(request) -> dict:
    """Return ``request`` if it has the expected shape, else raise InvalidRequest."""
    if not isinstance(request, dict):
        raise InvalidRequest("request is not an object")
    missing = [name for name in FIELDS if name not in request]
    if missing:
        raise InvalidRequest("request lacks: %s" % ", ".join(missing))
    if not isinstance(request["id"], str) or not _ID_PATTERN.fullmatch(request["id"]):
        raise InvalidRequest("request id is malformed")
    if not isinstance(request["sha256"], str) or not _SHA_PATTERN.fullmatch(request["sha256"]):
        raise InvalidRequest("request sha256 is malformed")
    if not isinstance(request["target"], str) or not request["target"]:
        raise InvalidRequest("request target is malformed")
    return request
