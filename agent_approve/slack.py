"""Slack adapter without network access.

``approval_blocks(request)`` builds a Block Kit message that shows the action,
the target and a short checksum, with exactly one button whose value is
``"<id> <sha256>"``. Sending the message and receiving the click is up to you.

When the click arrives, use ``parse_button_value`` and compare the checksum
with the request before calling ``approve``; ``verify_before_effect`` checks it
once more right before the effect.
"""
from __future__ import annotations

from .request import validate

SHORT_SHA = 12


def button_value(request: dict) -> str:
    return "%s %s" % (request["id"], request["sha256"])


def parse_button_value(value: str):
    """Split a button value into (request_id, sha256)."""
    request_id, _, sha = value.partition(" ")
    return request_id, sha


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def approval_blocks(request: dict) -> dict:
    """Return a Slack message payload (``text`` and ``blocks``) for ``request``."""
    validate(request)
    action = _escape(request["action"])
    target = _escape(request["target"])
    short = request["sha256"][:SHORT_SHA]
    return {
        "text": "Approval requested: %s" % action,
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*Approval requested*\n*Action:* %s\n*Target:* `%s`\n*sha256:* `%s`"
                    % (action, target, short),
                },
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": "The yes counts only for this exact content. "
                        "Any change after approval voids it.",
                    }
                ],
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "action_id": "agent_approve",
                        "text": {"type": "plain_text", "text": "Approve with code"},
                        "style": "primary",
                        "value": button_value(request),
                    }
                ],
            },
        ],
    }
