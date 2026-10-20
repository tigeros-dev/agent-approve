# Security policy

agent-approve is experimental. It is not a security boundary and not meant for
production use; see the limits section in the README.

## Reporting a problem

If you find a way to get an effect verified without a matching approval, to
reuse a one-time code, to get past the lock, or to make a key or code show up
in a log or output, please write to **hello@tigeros.dev** instead of opening a
public issue.

Please include:

- the agent-approve version (`agent_approve.__version__`) and Python version,
- the request and the commands that show the problem,
- what you expected and what happened.

Never send a real key. The synthetic test key in `examples/` is enough to
reproduce any issue.

This is a small project maintained in spare time; reports are handled on a
best-effort basis, and reporters are credited unless they ask not to be.

## Supported versions

There are no releases. Fixes land on the `main` branch only.
