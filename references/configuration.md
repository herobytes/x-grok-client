# Configuration and usage

## Python environment

Python 3.10 or newer is required. From the repository root:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

Use the same interpreter for installation and CLI calls. No activation or
background service is necessary. Do not distribute virtual environments: they
contain platform-specific files and absolute paths.

For a skill installation that may be replaced during updates, keep the runtime
outside the skill directory:

```bash
python3 -m venv "$HOME/.local/share/x-grok-client/.venv"
"$HOME/.local/share/x-grok-client/.venv/bin/python" -m pip install -r /absolute/path/to/x-grok-client/requirements.txt
"$HOME/.local/share/x-grok-client/.venv/bin/python" /absolute/path/to/x-grok-client/scripts/grok_client.py init
```

Replace the repository path with your installation location. Reuse that absolute
interpreter path for later calls. Installing skill files does not automatically
create an environment or install dependencies. Reinstall requirements when they
change. XClientTransaction has a separate
[daily maintenance policy](dependency-maintenance.md).

## First login

Installing dependencies does not create a Cookie file or sign you in. First,
choose where your Cookie dotenv file is stored. Run this in your terminal:

```bash
.venv/bin/python scripts/grok_client.py init
```

If no `envFile` is already configured, `init` asks for a file path. It has no
default Cookie file location and does not derive one from `--config`. You can
enter an existing file or a new path that you choose. Relative paths are resolved
from the configuration directory; `~/...` is supported. To skip the path prompt:

```bash
.venv/bin/python scripts/grok_client.py init --env-file /absolute/path/you/choose/cookies.env
```

Replace the example with your own path. The JSON configuration still defaults to
`~/.config/x-grok-client/config.json`, or the path supplied by `--config` before
`init`. This default applies only to configuration metadata, not credentials.

- **Existing valid Cookie file:** `init` validates it and saves its path in a new
  configuration without asking for the Cookie value. It rewrites the file only
  when the user explicitly accepts a detected proxy that needs saving.
- **New or empty Cookie file:** `init` explains how to obtain the Cookie and asks
  for hidden input. Valid input is saved only at the selected path.
- **No path or no answer:** leaving the path blank, reaching end-of-input, or
  running non-interactively without a configured or explicit path defers setup.
  No files or directories are created or changed. The command ends with creation
  instructions and returns `status: "setup_deferred"`, `cookie_configured: false`.
  Its exit code is 0 because deferring is intentional; scripts must check
  `cookie_configured` before making requests.
- **Existing configuration:** reuse its previously chosen `envFile`. An explicit
  `--env-file` pointing elsewhere is rejected; choose a different `--config` or
  deliberately edit `envFile` before changing accounts or file locations.

For Cookie acquisition, follow the [browser steps in the README](../README.md#get-your-x-cookie):
sign in to X, open Developer Tools **Network**, reload, select a request to
`https://x.com/i/api/`, and copy **Headers → Request Headers → Cookie**. Use only
the value, on one line, including non-empty `auth_token` and `ct0` entries. Do not
copy the `Cookie:` prefix, a response `Set-Cookie` header, all headers, or a cURL
command. If the header is absent, select another logged-in request.

Console JavaScript such as `document.cookie` or `copy(document.cookie)` cannot
read HttpOnly cookies, including X's `auth_token`. Use the request header instead.
Hidden terminal input does not echo characters; press Enter after pasting.

New files written by `init` use mode `0600`; newly created leaf directories use
mode `0700` on POSIX systems. Existing directory and linked-file permissions are
not changed. Check permissions yourself when linking a manually created file.
The first configuration uses model `grok-4-auto`. Existing configuration and other
dotenv entries are preserved. An existing proxy is replaced only with explicit
`--use-system-proxy`. To explicitly replace an existing Cookie:

```bash
.venv/bin/python scripts/grok_client.py init --replace-cookie
```

An existing valid file is otherwise reused. In `--cookie-stdin` mode, replacing a
non-empty Cookie requires `--replace-cookie`; the supplied input is not silently
ignored or allowed to overwrite it.

After setup returns `cookie_configured: true`, run `check` with the same `--config`
selection. Neither `init` nor `check` verifies online authentication. Invalid input
is rejected before creating configuration or credentials files. Instructions go
to stderr; the result on stdout remains JSON. Interactive setup ends with the
complete Cookie and configuration file formats using synthetic placeholders.

For a trusted local program piping a Cookie into `init --cookie-stdin`, select the
file with `--env-file` or an existing configuration. Without either, setup is
deferred without consuming stdin. Do not pass literal credentials through `echo`,
shell arguments, heredocs, or recorded tool calls. If an interactive terminal
cannot hide input, setup stops rather than echoing the Cookie.

## System proxy setup

`init` detects proxies locally before configuration. It uses Python's system
proxy discovery: environment variables first, then native macOS System
Configuration or Windows Internet Settings when proxy environment settings are
absent. Linux uses proxy environment variables. HTTPS, ALL, HTTP, and SOCKS proxy
entries are considered in that order because the X endpoints use HTTPS. Plain
host/port entries are normalized to proxy URLs. PAC scripts, WPAD, and
desktop-specific Linux proxy settings are not evaluated.

If a supported proxy is detected and `X_PROXY` is empty or absent, interactive
setup asks whether to apply it. Only `y` or `yes` applies it; no, blank input,
end-of-input, or non-interactive execution skips it. No detected proxy means no
question. An existing explicit `X_PROXY` is retained without a replacement prompt.

Use these options for an already confirmed installation choice:

- `init --use-system-proxy` explicitly saves the currently detected proxy,
  including replacing an existing `X_PROXY`. It fails if no supported proxy is
  detected. Select the Cookie file via `--env-file` or an existing configuration.
- `init --skip-proxy` skips the question, preserves existing proxy settings, and
  prints follow-up guidance when a detected proxy was not applied.
- `detect-proxy` reports a sanitized candidate and detection status as JSON. It
  needs no configuration or Cookie file and does not write files or access X.
  Proxy usernames and passwords are withheld. A detection error returns
  `detection_unavailable`, not a claim that the machine has no proxy.

The `init` JSON result includes `proxy_setup` (`applied`, `existing`, `skipped`,
`not_detected`, or `detection_unavailable`). Completed Cookie setup also reports
`proxy_configured`. These statuses describe local configuration, not connectivity.
In `--cookie-stdin` mode, proxy questions never consume Cookie input: use an
explicit proxy choice if desired. When setup is deferred before saving, no proxy
is persisted, even if `--use-system-proxy` was supplied.

### Finish a skipped proxy step

The final guidance includes the detected address with credentials redacted, the
complete dotenv format, and the command to apply the system proxy later:

```bash
.venv/bin/python scripts/grok_client.py init --env-file /absolute/path/you/choose/cookies.env --use-system-proxy
```

Alternatively, edit **`X_PROXY` in the same file as `X_COOKIE`**, using your actual
proxy URL. For example, `X_PROXY='http://127.0.0.1:10808'`. This example address is
not automatically selected. Leave `X_PROXY=''` only when you want direct
connections. A system-wide proxy does not redirect this client's traffic by
itself: runtime HTTP clients continue to use `trust_env=False` and the saved
explicit `X_PROXY` for both authenticated requests and transaction ID bootstrap.
Environment bypass lists are not imported into this explicit setting.

Run the offline `check` afterward. An explicitly requested `check-transaction`
performs an anonymous network probe without sending account cookies; a successful
probe does not verify authenticated Grok access. Network errors do not trigger
an automatic switch of proxy, account, or service.

## Finish Cookie setup later

If you have not chosen a path, installation can finish without login setup. No
credentials location is selected on your behalf. When ready:

1. Choose a private file location on your machine.
2. Use a local text editor to create a UTF-8 dotenv file there:

   ```dotenv
   X_COOKIE='auth_token=YOUR_AUTH_TOKEN; ct0=YOUR_CT0; other_cookie=value'
   X_PROXY=''
   ```

3. Replace the placeholder locally with the full request Cookie value using the
   browser steps above. Keep it on one line and escape quotes according to dotenv
   rules. On macOS/Linux, set file permissions to `0600`, for example with
   `chmod 600 /absolute/path/you/choose/cookies.env` (replace the path).
4. Link the existing file and validate local setup:

   ```bash
   .venv/bin/python scripts/grok_client.py init --env-file /absolute/path/you/choose/cookies.env
   .venv/bin/python scripts/grok_client.py check
   ```

Alternatively, run the same `init --env-file` command before creating the file;
it will ask for hidden Cookie input and write only to your chosen location.
See [SECURITY.md](../SECURITY.md) for credential handling.

## Configuration files

The default location is `~/.config/x-grok-client/config.json`:

```json
{
  "envFile": "/absolute/path/you/choose/cookies.env",
  "provider": "x-web",
  "model": "grok-4-auto"
}
```

The path above is illustrative; replace it with your own. The repository template
leaves `envFile` empty and must be filled before use. Only these three keys are
accepted. `envFile` supports an absolute path, `~/...`,
or a path relative to the configuration file. Credentials are read only from the
specified file, never supplemented from process environment variables. Dotenv
interpolation is disabled, including `${...}` substitution.

`model` is a web `grokModelOptionId`. The default is not a guarantee of account
access or a list of supported models. The configured value is passed unchanged;
there is no automatic model fallback.

## Credentials file format

Use UTF-8 dotenv, not JSON or a raw Cookie header. The file extension is arbitrary
(for example, `.env` or `.x-cookies`). Use one variable per line, exactly named
`X_COOKIE` and `X_PROXY`:

```dotenv
X_COOKIE='auth_token=YOUR_AUTH_TOKEN; ct0=YOUR_CT0; other_cookie=value'
X_PROXY=''
```

`X_COOKIE` is required and must contain the actual full request Cookie value,
including non-empty `auth_token` and `ct0`. The values above are placeholders;
replace them locally, not in chat. Omit the `Cookie:` prefix and keep the value on
one line. `X_PROXY` is optional; empty means a direct connection. These variables
belong only in the selected Cookie file; `config.json` contains the three metadata
fields shown above. Never put a Cookie or proxy password in configuration JSON.

Use `init` with your chosen file path to populate `X_COOKIE`. If editing manually, follow dotenv quoting and
escaping rules: keep surrounding single quotes, escape embedded single quotes as
`\'` and backslashes as `\\`. Use mode `0600` for the file on macOS/Linux.
`X_PROXY` accepts HTTP, HTTPS, SOCKS5, or SOCKS5H URLs. For example:

```dotenv
X_PROXY='socks5h://127.0.0.1:7890'
```

An empty proxy means a direct connection. Authenticated proxy URLs belong only in
the credentials file. Both API requests and transaction ID bootstrap disable
system proxy environment variables and use this explicit setting. Convert VLESS
or similar sharing links into a local HTTP/SOCKS listener with your proxy software.

## Local versus shared configuration

To keep configuration inside the checkout, specify it before the subcommand:

```bash
.venv/bin/python scripts/grok_client.py --config config/config.json init
.venv/bin/python scripts/grok_client.py --config config/config.json check
.venv/bin/python scripts/grok_client.py --config config/config.json ask --prompt "Hello."
```

Omit `--config` to use the shared location under `~/.config/x-grok-client/`.
The repository ships only `config/config.example.json` and
`config/credentials.example.env`; the JSON template intentionally has no Cookie
path. Private files are created only after path selection and valid input. Keep
them outside Git; the repository ignores local dotenv files and `config/config.json`. Updating the source does not require moving or recreating credentials.

To distribute the skill, include `SKILL.md`, `scripts/`, `references/`,
`requirements.txt`, the example configuration files, and `LICENSE`. Never include
actual credentials, local configuration, lock files, temporary files, or `.venv`.

## Cookie refresh and concurrency

A new `GrokClient` reads the latest credentials from disk. When a response changes
a cookie through `Set-Cookie`, the client:

1. Updates only `X_COOKIE`, preserving proxy settings, other entries, and comments.
2. Uses a same-directory temporary file, restrictive permissions, and atomic
   replacement, then updates its in-memory cookies.
3. Reuses a refreshed `ct0` from conversation creation in the following request.
4. Holds a file lock during writes and checks a snapshot of the previous file.
   If another client or a manual edit has changed the file, it stops instead of
   overwriting newer credentials.

A failed write does not count as a successful refresh. Required cookies deleted
by the server stay deleted; a new login is needed. HTTP 401/403 blocks further
requests from that client instance. The client does not scrape browser cookies,
refresh on a timer, or promise that a session never expires.

File locks coordinate this client's processes, but ordinary editors do not honor
them. Stop active calls before manually editing credentials or changing accounts.
A conflict or timeout may follow a completed remote operation; do not blindly
resend it.

## Output and troubleshooting

`check` is offline and returns `network_checked: false`. It validates local
configuration and imports dependencies; it does not test whether a cookie is
expired. `check-transaction` performs anonymous network requests and generates an
ID, but does not validate authenticated server acceptance.

Success goes to stdout as JSON. Errors go to stderr with `error` and `message`
fields. Exit codes are 0 for success, 1 for runtime failure, and 2 for invalid CLI
arguments. Maintenance events use separate JSON lines on stderr.

For login failures, obtain a fresh cookie from your own browser and run
`init --replace-cookie`. For protocol changes, verify that the X web interface
works for your account and consult [connection flow](connection-flow.md).
Offline checks do not establish live service compatibility.
