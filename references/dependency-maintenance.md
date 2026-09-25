# Dependency maintenance

The distribution is named `XClientTransaction`; its Python module is
`x_client_transaction`. The CLI checks for compatible stable wheels before
`ask` and `describe` in managed environments. It does not wait for a transaction
ID failure before checking.

## Update policy

1. Use the local calendar date. After one successful check that day, skip further
   maintenance and proceed with the request.
2. Download the latest stable wheel compatible with the current Python from the
   configured pip package index. Do not downgrade a newer installed version.
3. If an update exists, install it into a temporary directory and validate it in
   a fresh subprocess with anonymous X bootstrap and dynamic ID generation.
4. Download the installed version's wheel as a rollback backup. Only then replace
   XClientTransaction in the managed environment. Run `pip check` and validate
   transaction ID generation again in a fresh subprocess.
5. On download or candidate-validation failure, keep the existing version. If
   post-installation validation fails, attempt rollback. Record the failed attempt
   and wait at least one hour before checking again on a later CLI invocation.
6. An interrupted installation or failed rollback blocks further Grok calls until
   the environment is repaired manually.

There is no background process or scheduler. A one-hour retry interval means a
later invocation becomes eligible; nothing runs automatically when the hour ends.
The first request of the day may take longer. Keeping an older version does not
ensure it still works with the current X protocol.

Only XClientTransaction is upgraded. Other dependencies are not upgraded
transitively. Major versions are eligible, but prereleases are excluded. If an
update needs new dependencies or incompatible APIs, validation can fail and the
old version remains. Package mirrors may lag behind the upstream index.

## Managed environments and locking

Automatic maintenance is limited to these virtual environments:

- `.venv` inside this repository or skill directory.
- `~/.local/share/x-grok-client/.venv`.

Other environments return `unmanaged_environment` and are not modified. Python
3.10+, pip, and the dependencies from `requirements.txt` are required.

Maintenance and the subsequent CLI request share `.x-grok-runtime.lock` inside the
virtual environment. The lock remains held until the request finishes, so another
managed CLI call cannot update a dependency while that request is running. Lock
contention fails immediately instead of waiting.

`init`, `check`, and `check-transaction` do not trigger updates. Direct Python
imports of `GrokClient` do not trigger maintenance or take the runtime lock.
Applications using that interface must coordinate maintenance separately, before
starting processes that import the dependency.

## Repair after a transaction ID error

For CLI `ask` and `describe`, `transaction_id_error` triggers one immediate repair
of XClientTransaction in the same managed environment. This bypasses the daily
success cache and one-hour failure interval for this recovery attempt, but never
bypasses invalid state, interrupted installation, or failed rollback protection.
The runtime lock remains held through repair and the retry.

The updater downloads the latest compatible stable wheel, stages and probes it,
and keeps a rollback wheel before installation. If the installed version is
already the latest, repair validates and reinstalls that version once. It never
downgrades a newer installed version. Other packages are not upgraded. Failed
validation or installation stops recovery; rollback is attempted if necessary.

After a successful repair, the CLI uses the same Python executable in a fresh
subprocess so previously imported package code is not reused. The original prompt
is transferred over stdin, not command-line arguments. The original account,
model, configuration, and refreshed credentials are checked before the retry;
external configuration or credential changes stop it. For `describe`, the same
post URL and summary parsing are preserved.

Transaction IDs are generated before sending each authenticated request. If the
error occurred before conversation creation, the retry creates the conversation.
If creation already succeeded, its ID is carried forward, so only the unsent
answer request is attempted. The child performs no maintenance or recovery loop.
An update failure or any error on the single retry becomes
`transaction_recovery_failed`. Do not start another agent-level repair afterward.

TLS/proxy failures (`transaction_network_error`), HTTP 401/403/429, malformed
responses, and timeouts do not trigger package repair or request replay. There is
no static transaction ID fallback. Direct Python imports do not perform this
automatic recovery.

For a standalone `check-transaction` failure specifically classified as
`transaction_id_error`, the skill runs one explicit repair using the same Python
and configuration, then retries the probe once only if repair succeeded:

```bash
.venv/bin/python scripts/update_transaction.py --config /path/to/config.json --repair
.venv/bin/python scripts/grok_client.py --config /path/to/config.json check-transaction
```

Run the second command only when the first exits successfully. Probes themselves
never trigger repair, including the probes used internally by the updater.

## Manual commands

Check the daily maintenance policy without asking a question:

```bash
.venv/bin/python scripts/update_transaction.py
```

This still respects daily success records and the one-hour failed-attempt interval.
Select another configuration with `--config /absolute/path/config.json`.

Probe the installed transaction generator without updating anything:

```bash
.venv/bin/python scripts/grok_client.py check-transaction
```

The probe requires configuration and the referenced dotenv file, but not a valid
cookie. It reads only the configured proxy for anonymous requests to X pages and
scripts. It does not send account cookies, print the generated ID, or create a
Grok conversation. `transaction_id_generated: true` means local generation
succeeded; `server_acceptance_checked: false` means authenticated acceptance was
not tested.

## State and diagnostics

`.x-grok-transaction-maintenance.json` in the managed environment records attempt
time, local check date, package versions, and status. It contains no cookie.
Maintenance events are JSON lines on stderr; business results remain on stdout.
Raw pip output and authenticated proxy URLs are not printed.

| Status | Meaning |
| --- | --- |
| `up_to_date` | The installed version is current or newer; today's check succeeded. |
| `updated` | The candidate was installed and validated; today's check succeeded. |
| `already_checked` | A successful check already ran today. |
| `check_failed` | The check failed; the old version remains usable by policy. |
| `candidate_validation_failed` | The candidate failed its probe; the old version remains. |
| `rolled_back` | Post-installation validation failed; the previous version was restored. |
| `retry_deferred` | Less than one hour has passed since a failed attempt. |
| `unmanaged_environment` | Automatic maintenance is disabled for this interpreter. |
| `rollback_failed` | Rollback failed; repair the environment before further calls. |
| `installing` | An interrupted installation remains recorded; manual repair is required. |

An invalid state file also blocks maintenance. Inspect and repair the environment
before correcting its state; do not delete records to force repeated updates.
HTTP 401/403/429 and network failures never trigger an extra upgrade or replay a
potentially completed Grok request. `transaction_id_error` has the single bounded
repair exception described above. Recovery emits `transaction_repair` and
`transaction_retry` JSON events on stderr; normal result JSON remains on stdout.
