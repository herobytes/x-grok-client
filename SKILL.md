---
name: x-grok-client
description: Ask questions, continue conversations, or summarize X posts and their media through the Grok web interface using a local X session cookie. Use when the user explicitly requests X Grok or Grok-based post analysis, not for posting, replying, browser automation, or the official xAI API.
---

# X Grok Client

Use the bundled Python CLI. Configuration stores `envFile`, `provider`, and
`model`; the referenced dotenv file stores the cookie and optional proxy.
Only `provider=x-web` is supported.

## Workflow

1. For initial setup or configuration problems, read
   [configuration](references/configuration.md). Use Python 3.10+ with
   `requirements.txt` installed. Installing skill files does not install Python
   dependencies. Reuse the existing configuration, account, and model.
2. Resolve the skill directory from this file's location. Use absolute paths for
   the interpreter and script. The default configuration is
   `~/.config/x-grok-client/config.json`; select a different file with `--config`
   before the command. A relative `envFile` is relative to its configuration file.
3. During first-time installation, ask the user where their Cookie dotenv file
   is stored. Ask for the path only, never the Cookie value. Continue independent
   installation work while waiting. Do not choose a Cookie location, generate a
   default `envFile`, or create credentials without a user-selected path. If the
   user does not answer or leaves it blank, finish installation and include
   [manual file creation instructions](references/configuration.md#finish-cookie-setup-later)
   in the final response. State that Cookie setup remains incomplete; do not run
   authenticated requests or claim that login is configured.
   When a path is provided, use `init --env-file <user-selected-path>` to link an
   existing dotenv file. For a new or empty file, have the user run this command
   in their own terminal for hidden Cookie input. Existing configured `envFile`
   values represent a previous choice and can be reused without asking again.
   Explain how to get the Cookie: sign in to X, open Developer Tools Network,
   reload, select an `x.com/i/api/` request, and copy Headers > Request Headers >
   Cookie (the entire value, without filtering individual cookie pairs).
   `auth_token` and `ct0` are validation requirements, not instructions to extract
   only two values. Console `document.cookie`
   cannot read HttpOnly login cookies. Never pass Cookie values as command-line
   arguments or read and print the credentials file. Replacing an existing Cookie
   requires `init --replace-cookie`. Run `check` only after setup completes; it
   validates local files and dependencies, not online authentication or Grok access.
4. During installation, run `detect-proxy` to inspect system/environment proxy
   settings without loading credentials or making network requests. On macOS,
   use host-level execution for the initial read when the tool supports it;
   a sandboxed process may be unable to see System Configuration. Obtain the
   execution permission through the tool's normal permission mechanism before
   that initial call, not by retrying after a specified task has failed. If a proxy is
   detected and no existing `X_PROXY` is configured, ask whether the user wants to
   apply it. Display only the sanitized address from the command. Never interpret
   no answer as consent. Apply it only after an affirmative answer using
   `init --use-system-proxy` with the user's chosen file/configuration. If no proxy
   is reliably reported (`not_detected`), do not ask a proxy question.
   `detection_unavailable` means the current environment could not reliably read
   system settings. A sandbox can hide them; never describe this as "no system
   proxy". Stop the specified installation task on a detection error, report the
   result, and provide the command for the user to run in their own terminal.
   Do not retry with different permissions/tools or change settings without the
   user's authorization. Preserve an existing explicit `X_PROXY` unless
   the user asks to replace it. Use `init --skip-proxy` if the user skips this step.
   If the Cookie path or input remains unavailable, finish independent installation
   work and include the proxy instructions in the final response instead of
   attempting to save settings. A confirmed proxy still requires a chosen file.
   Non-interactive `init` returns `proxy_setup: confirmation_required` when a proxy
   was detected but no decision was supplied. Ask the user in the conversation;
   do not treat this as consent, a deliberate skip, or completed proxy setup.
   Reusing an existing Cookie and passing offline `check` do not replace this step.
5. End installation with the actual Cookie/proxy setup status and the full
   [file format](references/configuration.md#credentials-file-format), including
   `X_COOKIE` and `X_PROXY`, required Cookie keys, quoting, and the JSON `envFile`
   mapping. Use `X_COOKIE='your-cookies...'` or `X_COOKIE=''` in examples, never a
   partial Cookie header or the actual file contents. Tell the user to paste the
   entire Cookie request-header value, retaining every cookie pair. If the
   proxy step was skipped or unanswered, explain how to add `X_PROXY` later or
   rerun `init --use-system-proxy`. Explain that an empty proxy means direct
   connection, which may not work on the user's network. Do not reduce the final
   guidance to a single sentence or only a link to documentation.
6. Use `ask` for questions or `describe` for an explicit X post URL. `ask` creates
   a retained conversation unless a previous `conversation_id` is provided. The
   client does not post or reply. In a dedicated environment, the CLI checks
   XClientTransaction once per day before an actual request; see
   [dependency maintenance](references/dependency-maintenance.md).
7. Report the returned result accurately. Post and media descriptions are model
   interpretations. `structured=false` means the summary fell back to plain text.
   The CLI repairs `transaction_id_error` once as described below. Stop on other
   errors; do not replay an authenticated request whose outcome is unknown.

Replace `<python>` and `<skill-dir>` with actual absolute paths:

```bash
<python> <skill-dir>/scripts/grok_client.py check
<python> <skill-dir>/scripts/grok_client.py ask --prompt "Explain this concept."
<python> <skill-dir>/scripts/grok_client.py ask --prompt-file /absolute/path/question.txt
<python> <skill-dir>/scripts/grok_client.py ask --conversation-id PREVIOUS_ID --prompt "Explain the second point."
<python> <skill-dir>/scripts/grok_client.py describe https://x.com/username/status/1234567890
```

Use a UTF-8 prompt file or `--prompt-file -` for long or private input. Prompts are
sent to `grok.x.com`; include only what the task needs.

## Error handling

- Missing configuration: identify the required file and fields without requesting
  credentials in chat. `load_config()` returns metadata only.
- HTTP 401/403: stop and check authentication, Grok access, or account restrictions.
- HTTP 429, empty final text, malformed streams, and timeouts: stop and report.
  The remote operation may already have completed.
- `transaction_id_error`: update XClientTransaction in the same managed Python
  environment, then retry once. CLI `ask` and `describe` do this automatically:
  force a validated update even if today's check already ran, then retry in a
  fresh Python process using the same prompt, account, model, and any conversation
  already created. Only the request blocked before sending by ID generation is
  resumed. Do not add a second agent-level update/retry on top of the CLI.
  `transaction_recovery_failed` means recovery stopped; report it without looping.
- If a standalone `check-transaction` returns `transaction_id_error`, run the
  same interpreter with `scripts/update_transaction.py --config <same-config> --repair`.
  On success, retry that probe once in a fresh process; if update or retry fails,
  stop. Use the project/skill `.venv` or `~/.local/share/x-grok-client/.venv`;
  never silently update system Python or an unrelated environment.
- `transaction_network_error` (including TLS/proxy failures), HTTP 401/403/429,
  and malformed responses are not evidence of a stale transaction package.
  Report them without triggering this repair. Never use static transaction IDs.
- Credential conflicts or failed writes: stop. Another process may have updated
  the file, and the request may already have completed. Create a fresh client
  after resolving the issue instead of blindly retrying.
- Never output cookies, CSRF values, authenticated proxy URLs, request headers, or
  raw HTTP error bodies. CLI errors are sanitized; maintenance events are JSON
  lines on stderr, while answers remain on stdout.

Changed response cookies are written atomically to the original `envFile` and
reused on later calls. Plaintext credential files are not encrypted; cookie
refresh does not invalidate all previous values. Exposed cookies require session
revocation and a new login.

For protocol changes or Python integration, read
[connection flow](references/connection-flow.md). For installation, proxies, and
persistent environments, read [configuration](references/configuration.md).
