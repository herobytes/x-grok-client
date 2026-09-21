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
```

**Choose your Cookie file after installation.** Installing dependencies does not create a credentials file. Run the setup command in your own interactive terminal:

```bash
.venv/bin/python scripts/grok_client.py init
```

`init` first asks **where your Cookie dotenv file is**. Enter an existing file or a new file path of your choice. There is **no default Cookie file location**. An existing valid Cookie is reused; for a new or empty file, `init` offers hidden Cookie input and saves it only at your chosen path. A path already recorded in `envFile` is reused. The file is rewritten only when saving a new Cookie or a proxy you explicitly accept.

**Leave the path blank to finish setup later.** No configuration or credentials are created or changed. The command ends with instructions for obtaining a Cookie and creating your own file; its JSON result reports `status: "setup_deferred"` and `cookie_configured: false`.

If you already know the path, specify it directly (replace the example with your chosen location):

```bash
.venv/bin/python scripts/grok_client.py init --env-file /absolute/path/you/choose/cookies.env
```

`--config` selects the JSON configuration file and defaults to `~/.config/x-grok-client/config.json`. It does **not** choose a Cookie file for you. Relative Cookie paths are resolved from the configuration directory. For manual creation, see [finish Cookie setup later](references/configuration.md#finish-cookie-setup-later).

### Choose whether to use your system proxy

During `init`, the client checks local system/environment proxy settings. If it detects a supported proxy and your file has no `X_PROXY`, it asks **whether to use that proxy**. Enter `y` to save it. Press Enter, answer `n`, or use `--skip-proxy` to skip; the final instructions explain how to configure it later. No detected proxy means no proxy question. An existing explicit `X_PROXY` is preserved.

For an agent-assisted installation, the agent checks first and asks you before applying a detected proxy. No answer means it is not applied. These commands inspect settings or apply them after you have chosen to do so:

```bash
.venv/bin/python scripts/grok_client.py detect-proxy
.venv/bin/python scripts/grok_client.py init --env-file /absolute/path/you/choose/cookies.env --use-system-proxy
```

Detection makes no network requests and does not prove that the proxy works. It reads proxy environment variables and, when those are absent, native settings on macOS and Windows. Linux desktop-specific settings and PAC scripts are not evaluated. Runtime requests still use only the saved `X_PROXY`; an empty value means direct connection. The client never silently switches to a system proxy after a network error.

### Cookie file format

Save a **UTF-8 dotenv file**, with one variable per line, at your chosen path. The extension does not matter; a name such as `.x-cookies` works. This is a template, not a real Cookie:

```dotenv
# Required: full Cookie request-header value; auth_token and ct0 must be present.
X_COOKIE='auth_token=YOUR_AUTH_TOKEN; ct0=YOUR_CT0; other_cookie=value'

# Optional: your actual proxy URL. Use X_PROXY='' for direct connection.
X_PROXY='http://127.0.0.1:10808'
```

The proxy above is an example, not a default. Keep both variable names exactly as shown. Keep the Cookie on one line, without the `Cookie:` prefix. Use dotenv quotes; within single quotes, escape embedded single quotes as `\'` and backslashes as `\\`. On macOS/Linux, set file permissions to `0600`. See [configuration](references/configuration.md#credentials-file-format) for accepted proxy schemes and the `config.json` format. Setup prints this format again when it finishes, including when a step is deferred.

### Get your X Cookie

In Chrome or Edge:

1. Open [x.com](https://x.com) and sign in to your own account.
2. Open Developer Tools: **Cmd+Option+I** on macOS or **Ctrl+Shift+I** on Windows/Linux.
3. Select **Network**, then reload the page so requests appear.
4. Select a request whose URL starts with `https://x.com/i/api/`. You can filter the list by `i/api`.
5. Open **Headers → Request Headers** and find **Cookie** (or `cookie`). Copy only its value, without the `Cookie:` prefix. It must include both `auth_token=...` and `ct0=...`; if either is missing, select another logged-in request.
6. After choosing your Cookie file path, paste that value into the terminal's hidden `init` prompt and press **Enter**. No characters appearing while you paste is normal. If you deferred setup, save it in your own local dotenv file as described in the [configuration guide](references/configuration.md#finish-cookie-setup-later).

Copy the **request Cookie value**, not a response `Set-Cookie` header, all headers, or **Copy as cURL**. Keep it on one line. Never paste it into an issue, chat, or command-line argument.

**Can a Console one-liner get the cookie?** `document.cookie` (including `copy(document.cookie)` in Chrome DevTools) cannot read **HttpOnly** cookies. X's `auth_token` is an HttpOnly login cookie, so the result is incomplete for this client. Use the Network steps above; a page-level JavaScript snippet cannot bypass HttpOnly.

### Verify setup

After `init` confirms that the Cookie file was configured (`cookie_configured: true`):

```bash
.venv/bin/python scripts/grok_client.py check
.venv/bin/python scripts/grok_client.py ask --prompt "Explain how a solar eclipse works."
```

The `check` command validates local configuration and dependencies only; it does **not** verify online authentication or Grok access. `ask` sends an actual request. For a custom credentials location or replacing an expired cookie, see the [configuration guide](references/configuration.md#first-login).

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
  "envFile": "/absolute/path/you/choose/cookies.env",
  "provider": "x-web",
  "model": "grok-4-auto"
}
```

Replace the illustrative `envFile` value with your own Cookie file. Relative paths are resolved from the configuration file, not your working directory. The example configuration template leaves `envFile` empty so you must choose it explicitly. `model` is an X web `grokModelOptionId`, not an official xAI API model name. The client does not silently change models or accounts.

To keep configuration inside your checkout instead, pass `--config` **before** the command:

```bash
.venv/bin/python scripts/grok_client.py --config config/config.json init
.venv/bin/python scripts/grok_client.py --config config/config.json check
```

On first setup, `init` still asks for your Cookie file path. It never derives a credentials filename from the `--config` directory.

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

Run these checks locally before contributing. They require no X credentials or authenticated requests. This repository does not include a regression test suite; local checks validate code quality, not complete runtime behavior.

Dependabot checks only XClientTransaction every day at 09:00 Asia/Shanghai. A dedicated GitHub Actions workflow automatically squash-merges its single-package stable version updates, including major versions. It verifies the PR author and exact changed dependency line without executing PR code. This is an automatic update policy, not a compatibility test; conflicts or branch protection requirements can stop a merge. See [dependency maintenance](references/dependency-maintenance.md).

See [CONTRIBUTING.md](CONTRIBUTING.md) for contribution guidance and [SECURITY.md](SECURITY.md) for credential handling and vulnerability reporting. Protocol details live in [connection flow](references/connection-flow.md).

## License

[MIT](LICENSE). Dependencies are installed separately and retain their respective licenses.
