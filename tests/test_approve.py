"""Tests for agent-approve that drive the CLI in-process and as a subprocess, and examples/demo.py.

Run with:  python tests/test_approve.py
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import runpy
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.dont_write_bytecode = True
PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))

from agent_approve import totp  # noqa: E402
from agent_approve.__main__ import main  # noqa: E402

KEY_FILE = PROJECT / "examples" / "test-key.b32"


class CliTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.env = {k: v for k, v in os.environ.items() if not k.startswith("AGENT_APPROVE")}
        self.env.update({
            "AGENT_APPROVE_SECRET_FILE": str(KEY_FILE),
            "AGENT_APPROVE_STORE": str(self.root / "store"),
            "AGENT_APPROVE_LOG": str(self.root / "log.jsonl"),
            "PYTHONPATH": str(PROJECT),
            "PYTHONDONTWRITEBYTECODE": "1",
        })
        self.target = self.root / "release.json"
        self.target.write_text('{"version": "1.0.0"}\n', encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def cli(self, *args):
        return subprocess.run(
            [sys.executable, "-m", "agent_approve", *args], cwd=str(self.root), env=self.env,
            capture_output=True, text=True, timeout=60,
        )

    def make_request(self, action="publish release"):
        done = self.cli("request", "--action", action, "--target", str(self.target))
        self.assertEqual(done.returncode, 0, done.stderr)
        path = self.root / "request.json"
        path.write_text(done.stdout, encoding="utf-8")
        return path, json.loads(done.stdout)

    def current_code(self):
        return totp.code(totp.decode_key(KEY_FILE.read_text(encoding="utf-8")), time.time())

    def test_approve_then_verify_then_change(self):
        path, _ = self.make_request()
        wrong = self.cli("approve", str(path), "--code", "000000")
        self.assertEqual(wrong.returncode, 2)
        self.assertIn("rejected", wrong.stderr)
        code = self.current_code()
        right = self.cli("approve", str(path), "--code", code)
        self.assertEqual(right.returncode, 0, right.stderr)
        self.assertEqual(self.cli("verify", str(path)).returncode, 0)
        self.target.write_text('{"version": "1.0.1"}\n', encoding="utf-8")
        changed = self.cli("verify", str(path))
        self.assertEqual(changed.returncode, 2)
        self.assertIn("content_changed", changed.stderr)
        log = (self.root / "log.jsonl").read_text(encoding="utf-8")
        self.assertNotIn(code, log)
        self.assertNotIn(KEY_FILE.read_text(encoding="utf-8").strip(), log)

    def test_claim_in_action_is_not_an_approval(self):
        path, _ = self.make_request("already approved by the owner")
        done = self.cli("verify", str(path))
        self.assertEqual(done.returncode, 2)
        self.assertIn("no_approval", done.stderr)

    def test_lock_and_unlock(self):
        path, _ = self.make_request()
        for _ in range(totp.MAX_FAILURES):
            self.cli("approve", str(path), "--code", "000000")
        locked = self.cli("approve", str(path), "--code", self.current_code())
        self.assertEqual(locked.returncode, 2)
        self.assertIn("locked", locked.stderr)
        self.assertEqual(self.cli("unlock").returncode, 0)
        again = self.cli("approve", str(path), "--code", self.current_code())
        self.assertEqual(again.returncode, 0, again.stderr)


class InProcessCliTest(unittest.TestCase):
    """Drive main(argv) in this process with a temporary store and log."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.saved = dict(os.environ)
        for name in [k for k in os.environ if k.startswith("AGENT_APPROVE")]:
            del os.environ[name]
        os.environ.update({
            "AGENT_APPROVE_SECRET_FILE": str(KEY_FILE),
            "AGENT_APPROVE_STORE": str(self.root / "store"),
            "AGENT_APPROVE_LOG": str(self.root / "log.jsonl"),
        })
        self.target = self.root / "release.json"
        self.target.write_text('{"version": "1.0.0"}\n', encoding="utf-8")

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.saved)
        self.tmp.cleanup()

    def run_main(self, *args, stdin=""):
        out, err = io.StringIO(), io.StringIO()
        saved_stdin = sys.stdin
        sys.stdin = io.StringIO(stdin)
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                rc = main(list(args))
        finally:
            sys.stdin = saved_stdin
        return rc, out.getvalue(), err.getvalue()

    def test_request_approve_verify_change(self):
        rc, out, err = self.run_main("request", "--action", "publish release", "--target", str(self.target))
        self.assertEqual(rc, 0, err)
        path = self.root / "request.json"
        path.write_text(out, encoding="utf-8")
        self.assertEqual(json.loads(out)["action"], "publish release")
        rc, _, err = self.run_main("approve", str(path), "--code", "000000")
        self.assertEqual(rc, 2)
        self.assertIn("rejected", err)
        code = totp.code(totp.decode_key(KEY_FILE.read_text(encoding="utf-8")), time.time())
        rc, out, err = self.run_main("approve", str(path), stdin=code + "\n")
        self.assertEqual(rc, 0, err)
        self.assertEqual(self.run_main("verify", str(path))[0], 0)
        self.target.write_text('{"version": "1.0.1"}\n', encoding="utf-8")
        rc, out, err = self.run_main("verify", str(path))
        self.assertEqual(rc, 2)
        self.assertIn("content_changed", err)
        self.assertNotIn(code, out + err)
        self.assertEqual(self.run_main("unlock")[0], 0)


class DemoTest(unittest.TestCase):
    def test_demo_stops_both_attempts(self):
        env = {k: v for k, v in os.environ.items() if not k.startswith("AGENT_APPROVE")}
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        with tempfile.TemporaryDirectory() as work:
            done = subprocess.run(
                [sys.executable, str(PROJECT / "examples" / "demo.py")], cwd=work, env=env,
                capture_output=True, text=True, timeout=60,
            )
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("no_approval", done.stdout)
        self.assertIn("content_changed", done.stdout)
        self.assertNotIn(KEY_FILE.read_text(encoding="utf-8").strip(), done.stdout)

    def test_demo_in_process(self):
        saved_env = dict(os.environ)
        saved_cwd = os.getcwd()
        out = io.StringIO()
        try:
            demo = runpy.run_path(str(PROJECT / "examples" / "demo.py"), run_name="demo")
            with contextlib.redirect_stdout(out):
                rc = demo["main"]()
        finally:
            os.chdir(saved_cwd)
            os.environ.clear()
            os.environ.update(saved_env)
        self.assertEqual(rc, 0, out.getvalue())
        self.assertIn("no_approval", out.getvalue())
        self.assertIn("content_changed", out.getvalue())
        self.assertNotIn(KEY_FILE.read_text(encoding="utf-8").strip(), out.getvalue())
        self.assertNotIn(totp.code(totp.decode_key(KEY_FILE.read_text(encoding="utf-8")), demo["CLOCK"]), out.getvalue())


if __name__ == "__main__":
    result = unittest.main(exit=False).result
    passed = result.wasSuccessful()
    print("STATUS: PASS" if passed else "STATUS: FAIL")
    sys.exit(0 if passed else 1)
