"""Command line: python -m agent_approve {request,approve,verify,unlock}.

Exit codes: 0 approved, 2 rejected (reason on stderr), 1 usage or I/O error.
"""
from __future__ import annotations

import argparse
import json
import sys

from . import totp
from .approve import approve, store_dir, verify_before_effect
from .request import InvalidRequest, create

REJECTED_RC = 2


def _load_request(path: str):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def _report(decision, verb: str) -> int:
    if decision.ok:
        print(verb)
        return 0
    print("rejected: %s" % decision.reason, file=sys.stderr)
    return REJECTED_RC


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="agent-approve",
        description="Content-bound human approval with a one-time code.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    made = sub.add_parser("request", help="create a request and print it as JSON")
    made.add_argument("--action", required=True, help="what the agent wants to do")
    made.add_argument("--target", required=True, help="the file the action depends on")

    yes = sub.add_parser("approve", help="approve a request with a one-time code")
    yes.add_argument("request_file")
    yes.add_argument("--code", help="the 6-digit code; read from stdin when omitted")

    check = sub.add_parser("verify", help="check right before the effect")
    check.add_argument("request_file")

    sub.add_parser("unlock", help="lift the lock after too many wrong codes")

    args = parser.parse_args(argv)
    try:
        if args.command == "request":
            print(json.dumps(create(args.action, args.target), indent=2))
            return 0
        if args.command == "approve":
            given = args.code if args.code is not None else sys.stdin.readline().strip()
            return _report(approve(_load_request(args.request_file), given), "approved")
        if args.command == "verify":
            return _report(verify_before_effect(_load_request(args.request_file)), "approved, unchanged")
        totp.unlock(store_dir())
        print("unlocked")
        return 0
    except (OSError, ValueError, InvalidRequest) as error:
        print("error: %s" % error, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
