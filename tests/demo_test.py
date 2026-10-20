"""Run examples/demo.py in this process and check what it shows.

Run from anywhere:  python tests/demo_test.py

The demo changes the working directory and three environment variables; both
are restored afterwards. The one-time code must not appear in the output.
"""
from __future__ import annotations

import contextlib
import io
import os
import runpy
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
DEMO = PROJECT / "examples" / "demo.py"
VARIABLES = ("AGENT_APPROVE_SECRET_FILE", "AGENT_APPROVE_STORE", "AGENT_APPROVE_LOG")


def run_demo():
    saved_cwd = os.getcwd()
    saved_env = {name: os.environ.get(name) for name in VARIABLES}
    out, err = io.StringIO(), io.StringIO()
    try:
        demo = runpy.run_path(str(DEMO), run_name="demo")
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = demo["main"]()
    finally:
        os.chdir(saved_cwd)
        for name, value in saved_env.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
    return demo, rc, out.getvalue(), err.getvalue()


def main() -> int:
    demo, rc, out, err = run_demo()
    from agent_approve import totp

    key = totp.decode_key((PROJECT / "examples" / "test-key.b32").read_text(encoding="utf-8"))
    code = totp.code(key, demo["CLOCK"])
    checks = [
        ("demo returns 0", rc == 0),
        ("attempt 1 rejected with no_approval", "rejected: no_approval" in out),
        ("attempt 2 approved", "\napproved\n" in out),
        ("changed release rejected with content_changed", "rejected: content_changed" in out),
        ("demo says both attempts stopped", "demo: both attempts stopped" in out),
        ("nothing on stderr", err == ""),
        ("one-time code not printed", code not in out),
    ]
    bad = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(("ok    " if ok else "WRONG ") + name)
    print("STATUS: " + ("PASS" if not bad else "FAIL"))
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
