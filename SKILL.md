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
3. For first login, have the user run `init` in their own terminal and enter the
   cookie through its hidden prompt. Explain that installing dependencies does
   not create credentials: `init` creates the configuration and cookie file after
   valid input, so manual file creation is unnecessary. Show the user how to get
   the cookie: sign in to X, open Developer Tools Network, reload, select an
   `x.com/i/api/` request, and copy Headers > Request Headers > Cookie (value only,
   including `auth_token` and `ct0`). Do not recommend Console `document.cookie`;
   it cannot read HttpOnly login cookies. Do not request cookies in chat or pass them
   as command-line arguments. Replacing a configured cookie requires
   `init --replace-cookie`. Run `check` afterward; it validates local files and
   dependencies, not online authentication or Grok access. Do not read or print
   the credentials file to inspect login state; the script reads it internally.
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
