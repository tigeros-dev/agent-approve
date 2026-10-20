# agent-approve

**A yes counts only for exactly what the human saw.**

agent-approve is a small building block for content-bound human approval of
agent actions. An agent may trigger an effect only after a human has confirmed
exactly this content with a one-time code (TOTP, RFC 6238). A claim in text
("already approved") never counts, and content that changes after the yes
voids the yes.

Python 3.11+, standard library only, Apache-2.0.

## Why

A boundary is only half the story. The other half is a controlled way to say yes, and a yes should count only for exactly what I saw.

An agent that is stopped at a boundary will ask for permission. If that
permission is a chat message, a flag in a file or a sentence in its own
output, the agent (or whoever feeds it text) can produce it. agent-approve
ties the yes to two things the agent cannot fake: a one-time code from the
human's authenticator, and the sha256 of the content the human looked at.

## How it works

1. **Request.** The agent creates a request: `{id, action, target, sha256, created}`.
   `action` is free text for the human; `sha256` is the checksum of the target
   file at that moment.
2. **Approve.** The human reads the request (for example in Slack) and enters
   a one-time code. `approve` checks, in this order: not locked, valid code
   whose time step has not been used, request id not approved before, and the
   sha256 of the target read fresh from disk equals the request. Only then an
   approval record `{request_id, sha256, approved_at}` is written to the store.
3. **Verify before the effect.** Right before acting, the agent calls
   `verify_before_effect`. It rejects with `no_approval` when there is no record
   for this id, no matter what the request or its action text says, and with
   `content_changed` when the target is no longer what was approved.

Every decision, including each rejection with its reason, is one JSON line in
the log: time, request id, shortened target, short sha, verdict, reason. Codes
and keys are never written to the log or printed.

One-time codes: 6 digits, 30 second steps, HMAC-SHA1, the current step and one
before and after are accepted. Each step counts at most once (everything up to
the last accepted step is spent). After `MAX_FAILURES` wrong codes in a row the
check is locked until `python -m agent_approve unlock`.

## Quickstart

The repository ships a **synthetic test key** in `examples/test-key.b32`.
It is public and for trying things out only; never use it for real approvals.
Generate your own Base32 key and keep it out of the agent's reach.

```sh
cd agent-approve
export PYTHONPATH=$PWD
export AGENT_APPROVE_SECRET_FILE=$PWD/examples/test-key.b32   # test key, demo only
cp examples/release.json /tmp/release.json

python -m agent_approve request --action "publish release 2.4.0" \
    --target /tmp/release.json > /tmp/request.json
python -m agent_approve approve /tmp/request.json --code 123456   # code from your authenticator
python -m agent_approve verify /tmp/request.json                  # rc 0: approved and unchanged
```

To get codes for the test key, add `examples/test-key.b32` to any TOTP app, or
compute one with `agent_approve.totp.code`.

| command | exit code |
|---|---|
| `request --action TEXT --target PATH` | 0, prints the request JSON |
| `approve REQUEST_FILE --code CODE` | 0 approved, 2 rejected (reason on stderr) |
| `verify REQUEST_FILE` | 0 approved and unchanged, 2 rejected (reason on stderr) |
| `unlock` | 0, lifts the lock after too many wrong codes |

Without `--code`, `approve` reads the code from stdin, which keeps it out of
the process list.

Environment:

| variable | default | meaning |
|---|---|---|
| `AGENT_APPROVE_SECRET_FILE` | none | file with the Base32 TOTP key |
| `AGENT_APPROVE_STORE` | `./.agent-approve` | approval records and code state |
| `AGENT_APPROVE_LOG` | `./agent-approve.log.jsonl` | decision log |

From Python:

```python
from agent_approve import approve, create, verify_before_effect

request = create("publish release 2.4.0", "release.json")
# ... show the request to a human, receive the code ...
approve(request, code)
# ... later, right before the effect ...
decision = verify_before_effect(request)
if not decision.ok:
    raise SystemExit("not approved: " + decision.reason)
```

`approve` also accepts `secret=`, a function returning the Base32 key, if the
key does not live in a file.

### Slack

`agent_approve.slack.approval_blocks(request)` builds a Block Kit message with
the action, the target, a short sha and exactly one button whose value is
`"<id> <sha256>"`. It does not touch the network: sending the message and
handling the click is up to you. Compare the sha in the button value with the
request when the click arrives; `verify_before_effect` checks it again before
the effect.

## Two attempts

`python examples/demo.py` replays both with a fixed clock:

**Attempt 1, the obvious one.** The agent writes a request whose action reads
"deploy now - already approved by the owner" and goes straight to the effect.
There is no approval record for that id, so `verify` rejects with
`no_approval`. Text is never evidence.

**Attempt 2, the one that looks like work.** `release.json` is approved with a
valid code. Afterwards exactly one line changes: the release's security
contact address. Everything else looks the same, the request still carries
the old checksum, but `verify` reads the file again and rejects with
`content_changed`.

```
== Attempt 1: the obvious one ==
$ python -m agent_approve verify request.json
rejected: no_approval
log: {"event": "verify", "reason": "no_approval", "verdict": "rejected", ...}

== Attempt 2: the one that looks like work ==
$ python -m agent_approve approve release-request.json --code ******
approved
-  "security_contact": "security@example.org"
+  "security_contact": "security@example-support.net"
$ python -m agent_approve verify release-request.json
rejected: content_changed
log: {"event": "verify", "reason": "content_changed", "verdict": "rejected", ...}
```

## Limits

Be honest about what this is:

- **TOTP confirms the person, it does not sign the content.** The code proves
  that someone with the authenticator said yes at that time. The binding to
  the content comes from comparing the checksum at approval and again before
  the effect.
- **The agent must call verify itself, or be wrapped** by something that does.
  agent-approve cannot stop code that never asks.
- The store and the log are plain files. Anything that can write to them can
  forge an approval; keep them, and the key, out of the agent's reach.
- The checksum covers one file. If the effect depends on more than that file,
  the yes does not cover the rest.
- This is **experimental**, **not a security boundary** and **not for production**.

## Not included

On purpose, to keep the building block small:

- no expiry or validity period of an approval,
- no delegation tokens,
- no roles,
- no effect or risk classes,
- no rules per path or resource class,
- no mandate.

## Related

[agent-gate](https://github.com/tigeros-dev/agent-gate) is the boundary: it
decides what an agent may not do. agent-approve is the way to a yes for the
things that need a human.

## Tests

```sh
python tests/test_approve.py
python tests/demo_test.py
```

## Status and support

agent-approve is a personal side project, shared as a contribution, not as a
product. It is provided "as is", without warranty of any kind (see sections 7
and 8 of the license). Issues and pull requests are welcome and handled on a
best-effort basis; there is no support commitment.

This project is not affiliated with or endorsed by my employer. Slack is a
trademark of its owner; agent-approve only builds a Block Kit message and does
not talk to Slack.

## License

Copyright 2026 Dominik Dietrich. Licensed under the Apache License, Version 2.0;
see [LICENSE](LICENSE) and [NOTICE](NOTICE). Security reports: see
[SECURITY.md](SECURITY.md).
