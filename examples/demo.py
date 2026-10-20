"""Replay two attempts against agent-approve with a fixed clock.

Run from anywhere:  python examples/demo.py

Everything happens in a temporary directory; examples/release.json is copied,
never changed. The one-time code is computed from the synthetic test key in
examples/test-key.b32 and is never printed.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

EXAMPLES = Path(__file__).resolve().parent
sys.path.insert(0, str(EXAMPLES.parent))

from agent_approve import approve, create, totp, verify_before_effect  # noqa: E402

CLOCK = 1767225600.0  # 2026-01-01T00:00:00Z, fixed so the run is repeatable


def shell(line: str) -> None:
    print("$ " + line)


def show_decision(decision) -> None:
    if decision.ok:
        print("approved")
    else:
        print("rejected: %s" % decision.reason)


def show_last_log_line(log: Path) -> None:
    lines = log.read_text(encoding="utf-8").splitlines()
    print("log: " + lines[-1])


def main() -> int:
    with tempfile.TemporaryDirectory() as work:
        root = Path(work)
        os.environ["AGENT_APPROVE_SECRET_FILE"] = str(EXAMPLES / "test-key.b32")
        os.environ["AGENT_APPROVE_STORE"] = str(root / ".agent-approve")
        os.environ["AGENT_APPROVE_LOG"] = str(root / "agent-approve.log.jsonl")
        os.chdir(root)
        log = root / "agent-approve.log.jsonl"

        print("== Attempt 1: the obvious one ==")
        print("The agent claims the approval in the action text and goes straight to the effect.")
        deploy = root / "deploy.sh"
        deploy.write_text("echo deploy\n", encoding="utf-8")
        request = create("deploy now - already approved by the owner", deploy, now=CLOCK)
        shell('python -m agent_approve request --action "deploy now - already approved by the owner"'
              " --target deploy.sh > request.json")
        shell("python -m agent_approve verify request.json")
        first = verify_before_effect(request, now=CLOCK + 5)
        show_decision(first)
        show_last_log_line(log)
        print()

        print("== Attempt 2: the one that looks like work ==")
        print("A release is approved with a valid code; afterwards exactly one line changes.")
        release = root / "release.json"
        shutil.copyfile(EXAMPLES / "release.json", release)
        request = create("publish release example-tool 2.4.0", release, now=CLOCK)
        shell('python -m agent_approve request --action "publish release example-tool 2.4.0"'
              " --target release.json > release-request.json")
        shell("python -m agent_approve approve release-request.json --code ******")
        key = totp.load_key()
        second = approve(request, totp.code(key, CLOCK), now=CLOCK)
        show_decision(second)
        show_last_log_line(log)
        before = "security@example.org"
        after = "security@example-support.net"
        release.write_text(release.read_text(encoding="utf-8").replace(before, after), encoding="utf-8")
        print("# one line changed in release.json:")
        print('-  "security_contact": %s' % json.dumps(before))
        print('+  "security_contact": %s' % json.dumps(after))
        shell("python -m agent_approve verify release-request.json")
        third = verify_before_effect(request, now=CLOCK + 20)
        show_decision(third)
        show_last_log_line(log)

    expected = (
        not first.ok and first.reason == "no_approval"
        and second.ok
        and not third.ok and third.reason == "content_changed"
    )
    print()
    print("demo: " + ("both attempts stopped" if expected else "UNEXPECTED RESULT"))
    return 0 if expected else 1


if __name__ == "__main__":
    sys.exit(main())
