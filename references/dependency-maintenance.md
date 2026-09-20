# Dependency maintenance

The distribution is named `XClientTransaction`; its Python module is
`x_client_transaction`. The CLI checks for compatible stable wheels before
`ask` and `describe` in managed environments. It does not wait for a transaction
ID failure before checking.

## Repository updates

Dependabot checks only XClientTransaction every day at 09:00 Asia/Shanghai,
including weekends, with at most one open version-update PR. GitHub may delay
scheduled jobs. The merge workflow automatically squash-merges stable version
increases, including major versions, when the PR is authored by Dependabot on a
branch in this repository and changes only the XClientTransaction requirement
line in `requirements.txt`.

The workflow uses API metadata and binds the merge to the inspected commit. It
does not check out PR code, run compatibility tests, approve unrelated updates,
or bypass branch protection. Conflicts and unmet protection requirements stop
the merge and require attention. Maintainers can rerun the workflow or use its
manual dispatch to process an existing eligible PR.

Repository updates raise the minimum version for future installations. They do
not update an existing virtual environment. CLI maintenance below independently
checks the latest compatible stable wheel before actual use in a managed
environment and validates it before installation.

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
HTTP 401/403/429, network failures, and transaction ID errors never insert an extra
emergency upgrade or replay a potentially completed Grok request.
