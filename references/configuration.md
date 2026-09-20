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

Installing dependencies does not create a cookie file or sign you in. Run `init`
in your own interactive terminal to create it automatically:

```bash
.venv/bin/python scripts/grok_client.py init
```

The command displays the target configuration and credentials paths before asking
for hidden input. By default, they are `~/.config/x-grok-client/config.json` and
`~/.config/x-grok-client/credentials.env`. There is no need to create either file
manually. An existing configuration's `envFile` determines the credentials path.

Follow the [browser instructions in the README](../README.md#get-your-x-cookie):
sign in to X, open Developer Tools **Network**, reload, select a request to
`https://x.com/i/api/`, and copy **Headers → Request Headers → Cookie**. Paste
only the value into `init` and press Enter; hidden input does not echo characters.
The value must be one line and include non-empty `auth_token` and `ct0` entries.
Do not include the `Cookie:` prefix or use a response's `Set-Cookie` attributes,
all headers, or a copied cURL command. If no Cookie header appears, select another
request made while signed in.

Console JavaScript such as `document.cookie` or `copy(document.cookie)` cannot
read HttpOnly cookies, including X's `auth_token`. It cannot supply the complete
login cookie required here; use the request header instead.

`init` creates configuration and credentials automatically. New files use mode
`0600`; newly created leaf directories use mode `0700` on POSIX systems. Existing
directory permissions are not changed. The default model is `grok-4-auto`.
Existing model, proxy, and other dotenv entries are preserved. A non-empty cookie
is not replaced unless you explicitly run:

```bash
.venv/bin/python scripts/grok_client.py init --replace-cookie
```

After the cookie is saved, run `check` with the same `--config` selection to
validate local setup. `init` and `check` do not verify online authentication.
Invalid input is rejected before creating the configuration or credentials files.
Interactive instructions go to stderr; the success result remains JSON on stdout.
`--cookie-stdin` omits the interactive instructions for scripted use.

A trusted local program can pipe a cookie into `init --cookie-stdin`. Do not use
literal credentials in `echo`, shell arguments, heredocs, or recorded tool calls.
If the terminal cannot hide interactive input, setup stops rather than echoing it.
See [SECURITY.md](../SECURITY.md) for storage and exposure guidance.

## Configuration files

The default location is `~/.config/x-grok-client/config.json`:

```json
{
  "envFile": "credentials.env",
  "provider": "x-web",
  "model": "grok-4-auto"
}
```

Only these three keys are accepted. `envFile` supports an absolute path, `~/...`,
or a path relative to the configuration file. Credentials are read only from the
specified file, never supplemented from process environment variables. Dotenv
interpolation is disabled, including `${...}` substitution.

`model` is a web `grokModelOptionId`. The default is not a guarantee of account
access or a list of supported models. The configured value is passed unchanged;
there is no automatic model fallback.

The dotenv template is:

```dotenv
X_COOKIE=''
X_PROXY=''
```

Use `init` to populate `X_COOKIE`. If editing manually, follow dotenv quoting and
escaping rules. `X_PROXY` accepts HTTP, HTTPS, SOCKS5, or SOCKS5H URLs. For example:

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
`config/credentials.example.env`; private files are created locally and ignored
by Git. Updating the source does not require moving or recreating credentials.

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
