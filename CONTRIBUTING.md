# Contributing

Bug reports, documentation improvements, and focused pull requests are welcome.
Keep discussion constructive and respectful. Use English for documentation,
comments, CLI messages, issues, and pull requests.

## Local setup

Use Python 3.10 or newer and run commands from the repository root:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m ruff check .
.venv/bin/python -m ruff format --check .
.venv/bin/python -m compileall -q scripts
.venv/bin/python -m pip check
.venv/bin/python scripts/grok_client.py --help
.venv/bin/python scripts/update_transaction.py --help
```

To format a change, run `.venv/bin/python -m ruff format .`.
These checks require no X credentials. There is no checked-in regression test
suite; explain how you verified behavioral changes with synthetic data or mocks.
Never represent an offline check as proof of live X/Grok compatibility.

## Before opening a pull request

- Describe the problem, resulting behavior, and validation performed.
- Keep the change focused and update affected documentation and CLI examples.
- Preserve Python 3.10 compatibility and run all local checks above.
- Include only synthetic data in examples or reproduction steps.
- Do not commit local configuration, cookies, proxy credentials, response dumps,
  virtual environments, or generated artifacts.

## Protocol and authentication changes

Read [connection flow](references/connection-flow.md) and
[dependency maintenance](references/dependency-maintenance.md) first.
Keep authenticated requests restricted to the intended endpoints, redirects
disabled, cookie writes atomic, and errors free of credentials. Do not introduce
static transaction IDs or automatic replay of authenticated requests.

For an online reproduction, use your own account and describe the date, Python
version, dependency version, operation, and sanitized error code. Do not attach
raw HTTP traffic or credentials. A 401, 403, or 429 response alone does not prove
that transaction ID generation is broken.

## Reporting problems

Use the bug report template for reproducible defects and the feature request
template for proposals. Check existing issues first. Security-sensitive reports
should follow [SECURITY.md](SECURITY.md), not a public bug report.

By submitting a contribution, you agree that your contribution is available under
the repository's [MIT license](LICENSE).
