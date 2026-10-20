"""Approve a request with a one-time code, and check it again before the effect.

``approve(request, code)`` checks, in this order:

1. the code check is not locked,
2. the TOTP code is valid and its step has not been spent,
3. the request id has not been approved before,
4. the sha256 of the target, read fresh from disk, equals the request.

Only if all four hold, an approval record {request_id, sha256, approved_at}
is written to the store (AGENT_APPROVE_STORE, default ./.agent-approve).

``verify_before_effect(request)`` must be called right before the effect. It
rejects with ``no_approval`` when there is no record for this id, whatever the
request or its action text claims, and with ``content_changed`` when the
target is no longer exactly what was approved.

Every decision appends one JSON line to AGENT_APPROVE_LOG (default
./agent-approve.log.jsonl). Codes and keys are never logged.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from . import totp
from .files import create_json_once, read_json
from .request import InvalidRequest, file_sha256, utc_text, validate

STORE_ENV = "AGENT_APPROVE_STORE"
LOG_ENV = "AGENT_APPROVE_LOG"
DEFAULT_STORE = ".agent-approve"
DEFAULT_LOG = "agent-approve.log.jsonl"
SHORT_SHA = 12
MAX_TARGET_IN_LOG = 60

APPROVED = "approved"
REJECTED = "rejected"


@dataclass(frozen=True)
class Decision:
    """The result of approve or verify. ``reason`` is ``ok`` when approved."""

    ok: bool
    reason: str

    def __bool__(self) -> bool:
        return self.ok


def store_dir() -> Path:
    return Path(os.environ.get(STORE_ENV) or DEFAULT_STORE)


def log_path() -> Path:
    return Path(os.environ.get(LOG_ENV) or DEFAULT_LOG)


def short_target(target: str) -> str:
    """Shorten long paths for the log, keeping the end where the file name is."""
    if len(target) <= MAX_TARGET_IN_LOG:
        return target
    return "..." + target[-(MAX_TARGET_IN_LOG - 3):]


def _record_path(store: Path, request_id: str) -> Path:
    return store / "approvals" / (request_id + ".json")


def _log(event: str, request, ok: bool, reason: str, at: float) -> None:
    request = request if isinstance(request, dict) else {}
    sha = request.get("sha256")
    target = request.get("target")
    line = {
        "time": utc_text(at),
        "event": event,
        "request_id": request.get("id") if isinstance(request.get("id"), str) else None,
        "target": short_target(target) if isinstance(target, str) else None,
        "sha": sha[:SHORT_SHA] if isinstance(sha, str) else None,
        "verdict": APPROVED if ok else REJECTED,
        "reason": reason,
    }
    path = log_path()
    if path.parent != Path(""):
        path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(line, sort_keys=True) + "\n")


def _decide(event: str, request, ok: bool, reason: str, at: float) -> Decision:
    _log(event, request, ok, reason, at)
    return Decision(ok, reason)


def _current_sha(target: str) -> Optional[str]:
    try:
        return file_sha256(target)
    except OSError:
        return None


def approve(
    request: dict,
    code: str,
    now: Optional[float] = None,
    secret: Optional[Callable[[], str]] = None,
) -> Decision:
    """Approve ``request`` with the one-time ``code``. See the module docstring."""
    at = time.time() if now is None else now
    try:
        validate(request)
    except InvalidRequest:
        return _decide("approve", request, False, "bad_request", at)
    store = store_dir()
    if totp.is_locked(store):
        return _decide("approve", request, False, "locked", at)
    passed, reason = totp.check(code, at, store, secret)
    if not passed:
        return _decide("approve", request, False, reason, at)
    record_path = _record_path(store, request["id"])
    if record_path.exists():
        return _decide("approve", request, False, "id_used", at)
    current = _current_sha(request["target"])
    if current is None:
        return _decide("approve", request, False, "target_missing", at)
    if current != request["sha256"]:
        return _decide("approve", request, False, "content_changed", at)
    record = {
        "request_id": request["id"],
        "sha256": current,
        "target": request["target"],
        "approved_at": utc_text(at),
    }
    if not create_json_once(record_path, record):
        return _decide("approve", request, False, "id_used", at)
    return _decide("approve", request, True, "ok", at)


def verify_before_effect(request: dict, now: Optional[float] = None) -> Decision:
    """Allow the effect only for an approved, unchanged target.

    Only the approval record counts. Fields in the request such as
    ``approved`` or an action text saying "already approved" are ignored.
    """
    at = time.time() if now is None else now
    try:
        validate(request)
    except InvalidRequest:
        return _decide("verify", request, False, "bad_request", at)
    record = read_json(_record_path(store_dir(), request["id"]), None)
    if not isinstance(record, dict) or record.get("request_id") != request["id"]:
        return _decide("verify", request, False, "no_approval", at)
    if record.get("sha256") != request["sha256"] or record.get("target") != request["target"]:
        return _decide("verify", request, False, "content_changed", at)
    current = _current_sha(record["target"])
    if current is None:
        return _decide("verify", request, False, "target_missing", at)
    if current != record["sha256"]:
        return _decide("verify", request, False, "content_changed", at)
    return _decide("verify", request, True, "ok", at)
