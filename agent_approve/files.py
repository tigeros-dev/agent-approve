"""Small file helpers: atomic JSON writes and an exclusive file lock."""
from __future__ import annotations

import contextlib
import fcntl
import json
import os
import tempfile
from pathlib import Path


def write_json_atomic(path: Path, doc) -> None:
    """Write ``doc`` as JSON to ``path`` so that readers never see half a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", suffix=".part", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(doc, handle, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def create_json_once(path: Path, doc) -> bool:
    """Create ``path`` with ``doc`` only if it does not exist yet.

    Returns False when the file already exists. The content is written to a
    temporary file first and then hard-linked into place, which is both atomic
    and exclusive.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", suffix=".part", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(doc, handle, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(tmp, path)
        except FileExistsError:
            return False
        return True
    finally:
        with contextlib.suppress(OSError):
            os.unlink(tmp)


@contextlib.contextmanager
def exclusive_lock(path: Path):
    """Hold an exclusive advisory lock on ``path`` for the duration of the block."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def read_json(path: Path, default=None):
    """Read a JSON file, returning ``default`` when it does not exist."""
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError:
        return default
