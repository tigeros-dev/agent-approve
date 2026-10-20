"""RFC 6238 one-time codes with single use per time step and a lockout.

- 6 digits, 30 second steps, HMAC-SHA1, the current step plus one before and
  one after are accepted.
- Every step counts at most once: everything up to the last accepted step is
  spent, so neither the same code nor an older one works again.
- After MAX_FAILURES misses in a row the check is locked until ``unlock()``
  (``python -m agent_approve unlock``) is called.

The state is a small JSON file in the store, written atomically under a file
lock. It holds the last accepted step and the miss counter, never a code and
never the key. The key is read from the file named in AGENT_APPROVE_SECRET_FILE
(Base32) or from a function passed in by the caller; it is never printed or
logged.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import struct
from pathlib import Path
from typing import Callable, Optional

from .files import exclusive_lock, read_json, write_json_atomic

DIGITS = 6
STEP_SECONDS = 30
WINDOW = 1
MAX_FAILURES = 5

SECRET_ENV = "AGENT_APPROVE_SECRET_FILE"
STATE_FILE = "totp-state.json"
LOCK_FILE = "totp-state.lock"

_CODE_PATTERN = re.compile(r"[0-9]{%d}" % DIGITS)


class KeyUnavailable(Exception):
    """The key could not be loaded. The message never contains key material."""


def code(key: bytes, at: float) -> str:
    """Return the RFC 6238 code for the raw ``key`` at Unix time ``at``."""
    return _code_for_step(key, int(at // STEP_SECONDS))


def _code_for_step(key: bytes, step: int) -> str:
    mac = hmac.new(key, struct.pack(">Q", step), hashlib.sha1).digest()
    offset = mac[-1] & 0x0F
    value = struct.unpack(">I", mac[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(value % 10 ** DIGITS).zfill(DIGITS)


def decode_key(text: str) -> bytes:
    """Decode a Base32 key, ignoring spaces, case and missing padding."""
    cleaned = re.sub(r"[\s=]", "", text).upper()
    if not cleaned:
        raise KeyUnavailable("the key is empty")
    try:
        raw = base64.b32decode(cleaned + "=" * (-len(cleaned) % 8))
    except (ValueError, TypeError):
        raise KeyUnavailable("the key is not valid Base32") from None
    if len(raw) < 10:
        raise KeyUnavailable("the key is shorter than 80 bits")
    return raw


def load_key(secret: Optional[Callable[[], str]] = None) -> bytes:
    """Load the raw key from ``secret()`` or from AGENT_APPROVE_SECRET_FILE."""
    if secret is not None:
        return decode_key(secret())
    path = os.environ.get(SECRET_ENV, "")
    if not path:
        raise KeyUnavailable("%s is not set" % SECRET_ENV)
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError:
        raise KeyUnavailable("the key file cannot be read") from None
    return decode_key(text)


def _empty_state() -> dict:
    return {"last_step": None, "failures": 0, "locked": False}


def _load_state(store: Path) -> dict:
    state = read_json(store / STATE_FILE, None)
    if not isinstance(state, dict):
        return _empty_state()
    merged = _empty_state()
    merged.update({k: state[k] for k in merged if k in state})
    return merged


def is_locked(store: Path) -> bool:
    """True while the check is locked after too many misses."""
    with exclusive_lock(store / LOCK_FILE):
        return bool(_load_state(store)["locked"])


def check(given: str, now: float, store: Path, secret: Optional[Callable[[], str]] = None):
    """Check a code at time ``now``. Returns (ok, reason).

    Reasons: ``ok``, ``locked``, ``bad_code`` (also for a spent step), and
    ``no_key`` when the key cannot be loaded. The given code is never stored.
    """
    with exclusive_lock(store / LOCK_FILE):
        state = _load_state(store)
        if state["locked"]:
            return False, "locked"
        try:
            key = load_key(secret)
        except KeyUnavailable:
            return False, "no_key"
        current = int(now // STEP_SECONDS)
        last = state["last_step"]
        matched = None
        if isinstance(given, str) and _CODE_PATTERN.fullmatch(given):
            for step in range(current - WINDOW, current + WINDOW + 1):
                if last is not None and step <= last:
                    continue
                if hmac.compare_digest(_code_for_step(key, step), given):
                    matched = step
                    break
        if matched is None:
            state["failures"] = int(state["failures"]) + 1
            if state["failures"] >= MAX_FAILURES:
                state["locked"] = True
            write_json_atomic(store / STATE_FILE, state)
            return False, "locked" if state["locked"] else "bad_code"
        state["last_step"] = matched
        state["failures"] = 0
        write_json_atomic(store / STATE_FILE, state)
        return True, "ok"


def unlock(store: Path) -> None:
    """Lift the lock and reset the miss counter; spent steps stay spent."""
    with exclusive_lock(store / LOCK_FILE):
        state = _load_state(store)
        state["failures"] = 0
        state["locked"] = False
        write_json_atomic(store / STATE_FILE, state)
