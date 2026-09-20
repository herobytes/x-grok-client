# X Grok Client

A lightweight Python CLI and reusable agent skill for asking questions and summarizing X posts through the Grok web interface.

Use your own X session cookie to start conversations, continue a previous conversation, or request a structured description of a post and its media. No xAI API key, database, browser automation, or background service is required.

This is an unofficial client, not affiliated with X or xAI. It uses private web endpoints that can change without notice. An X account with access to Grok is required; web model availability depends on your account.

## Features

- Ask questions with a prompt, a UTF-8 file, or standard input.
- Continue conversations using the returned conversation ID.
- Summarize X posts with `summary`, `media_description`, and `tags` fields.
- Keep configuration separate from credentials, with hidden input during setup.
- Persist refreshed cookies atomically, with file locking and conflict detection.
- Use an explicit HTTP(S) or SOCKS5 proxy.
- Generate dynamic transaction IDs and maintain their dependency in a dedicated virtual environment.
- Return JSON results and sanitized errors for scripting.

## Quick start

Python **3.10 or newer** is required. The commands below target macOS and Linux. Download or clone this repository, then run these commands from its root:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python scripts/grok_client.py init
.venv/bin/python scripts/grok_client.py check
.venv/bin/python scripts/grok_client.py ask --prompt "Explain how a solar eclipse works."
```

Run `init` in your own interactive terminal. It asks for your X **Cookie request-header value** with input hidden. Use the value from a request to `x.com` in your logged-in browser's developer tools, without the `Cookie:` prefix. It must include `auth_token` and `ct0`. Never paste it into an issue, chat, or command-line argument.

By default, `init` creates `~/.config/x-grok-client/config.json` and `credentials.env`. The `check` command validates local configuration and dependencies only; it does **not** verify online authentication or Grok access.

Before the first `ask` or `describe` of the day, the CLI may download, validate, and update **XClientTransaction** inside a managed virtual environment. This can add startup time and make anonymous requests to X. See [dependency maintenance](references/dependency-maintenance.md) for the exact scope and failure behavior.

## Usage

```bash
# Ask a question.
.venv/bin/python scripts/grok_client.py ask --prompt "What is an event loop?"

# Read a longer prompt from a UTF-8 file or standard input.
.venv/bin/python scripts/grok_client.py ask --prompt-file question.txt
cat question.txt | .venv/bin/python scripts/grok_client.py ask --prompt-file -

# Continue a conversation using an ID returned by ask.
.venv/bin/python scripts/grok_client.py ask \
  --conversation-id YOUR_CONVERSATION_ID \
  --prompt "Show a small example."

# Summarize a post and its media; replace this illustrative URL.
.venv/bin/python scripts/grok_client.py describe https://x.com/username/status/1234567890

# Replace an expired cookie or switch accounts explicitly.
.venv/bin/python scripts/grok_client.py init --replace-cookie

# Inspect all commands.
.venv/bin/python scripts/grok_client.py --help
```

`ask` follows the language of your prompt. The built-in `describe` prompt requests English field values. Post and media descriptions are model-generated interpretations, not independently verified observations.

An illustrative `ask` result:

```json
{
  "conversation_id": "example-conversation-id",
  "model": "grok-4-auto",
  "text": "An event loop schedules and runs asynchronous work."
}
```

`describe` returns `conversation_id`, `model`, `tweet_url`, `summary`, `media_description`, `tags`, and `structured`. When the answer cannot be parsed as JSON, the original text is returned as the summary with `structured: false`.

Results go to stdout. Errors and dependency maintenance events go to stderr as JSON. Exit codes are `0` for success, `1` for runtime errors, and `2` for invalid CLI arguments.

## Configuration

The configuration contains exactly three fields:

```json
{
  "envFile": "credentials.env",
  "provider": "x-web",
  "model": "grok-4-auto"
}
```

`envFile` is resolved relative to the configuration file, not your working directory. `model` is an X web `grokModelOptionId`, not an official xAI API model name. The client does not silently change models or accounts.

To keep configuration inside your checkout instead, pass `--config` **before** the command:

```bash
.venv/bin/python scripts/grok_client.py --config config/config.json init
.venv/bin/python scripts/grok_client.py --config config/config.json check
```

Only example configuration files belong in Git. Actual credentials, local configuration, virtual environments, caches, and maintenance state are ignored. For proxies, persistent skill installation, and cookie handling, see the [configuration guide](references/configuration.md).

## Agent skill

[SKILL.md](SKILL.md) is the agent entry point. Keep it together with `scripts/`, `references/`, `requirements.txt`, and the example configuration files. Install Python dependencies separately; installing skill files does not install them automatically. Agents should use an absolute interpreter path and script path when invoking the CLI from another working directory.

## Limitations

- Requests use private X/Grok web endpoints and are not guaranteed to remain compatible.
- New conversations are retained on X; the client does not create temporary chats or delete history.
- Failed authenticated requests are not retried automatically: a timeout may occur after a remote operation succeeds.
- No posting, replying, media uploads, image generation, conversation listing, or model discovery is implemented.
- Only final response text is collected; search results and citations are not exported as separate structures.
- Local validation does not establish live service compatibility. Use your account only within its permissions and the service's applicable terms.

## Development

```bash
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m ruff check .
.venv/bin/python -m ruff format --check .
.venv/bin/python -m compileall -q scripts
.venv/bin/python -m pip check
```

Run these checks locally before contributing. They require no X credentials or authenticated requests. This repository does not include a regression test suite or a GitHub Actions workflow; local checks validate code quality, not complete runtime behavior.

See [CONTRIBUTING.md](CONTRIBUTING.md) for contribution guidance and [SECURITY.md](SECURITY.md) for credential handling and vulnerability reporting. Protocol details live in [connection flow](references/connection-flow.md).

## License

[MIT](LICENSE). Dependencies are installed separately and retain their respective licenses.
