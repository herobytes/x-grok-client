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
   Cookie (value only, including `auth_token` and `ct0`). Console `document.cookie`
   cannot read HttpOnly login cookies. Never pass Cookie values as command-line
   arguments or read and print the credentials file. Replacing an existing Cookie
   requires `init --replace-cookie`. Run `check` only after setup completes; it
   validates local files and dependencies, not online authentication or Grok access.
4. Use `ask` for questions or `describe` for an explicit X post URL. `ask` creates
   a retained conversation unless a previous `conversation_id` is provided. The
   client does not post or reply. In a dedicated environment, the CLI checks
   XClientTransaction once per day before an actual request; see
   [dependency maintenance](references/dependency-maintenance.md).
5. Report the returned result accurately. Post and media descriptions are model
   interpretations. `structured=false` means the summary fell back to plain text.
   Stop on errors; do not automatically replay authenticated requests or create
   another conversation.

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
- `transaction_id_error` or `transaction_network_error`: report the computation
  or network failure. Do not add an emergency upgrade or use static IDs.
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
