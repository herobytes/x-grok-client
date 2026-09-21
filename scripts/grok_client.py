"""Standalone X web Grok client. No database, browser runtime or xAI API key."""

from __future__ import annotations

import argparse
import asyncio
import getpass
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import warnings
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from http.cookies import CookieError, SimpleCookie
from importlib import import_module
from io import StringIO
from pathlib import Path
from urllib import request as urllib_request
from urllib.parse import urlsplit

DEFAULT_CONFIG = Path.home() / ".config/x-grok-client/config.json"
CALL_TIMEOUT_SECONDS = 180
QUERY_ID = "vvC5uy7pWWHXS2aDi1FZeA"
CREATE_URL = f"https://x.com/i/api/graphql/{QUERY_ID}/CreateGrokConversation"
RESPONSE_URL = "https://grok.x.com/2/grok/add_response.json"
# Public X web application token; account authentication comes from X_COOKIE.
BEARER = (
    "Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D"
    "1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"
)
PROMPT = (
    "Read the following X post, including its images and videos. "
    "Return only a JSON object with these fields: "
    '{"summary": "overall meaning of the post", '
    '"media_description": "description of the media", '
    '"tags": ["topic or sentiment tag"]}. '
    "Write the field values in English. Do not include any other text."
)
COOKIE_SETUP_HELP = """Get your X Cookie in Chrome or Edge:
1. Open https://x.com and sign in to your own account.
2. Open Developer Tools (Mac: Cmd+Option+I; Windows/Linux: Ctrl+Shift+I).
3. Select Network, reload the page, and select a request to x.com/i/api/.
4. Under Headers > Request Headers, copy only the Cookie header value.
   It must include auth_token and ct0. If absent, select another logged-in request.
5. Paste the value into the hidden terminal prompt below and press Enter.

Do not include the Cookie: prefix, copy a response Set-Cookie header, or use Copy as cURL.
Console document.cookie cannot read HttpOnly cookies such as auth_token.
Keep the cookie private; do not paste it into chat, issues, or command arguments.
"""


class GrokError(Exception):
    """Stable, credential-free error suitable for CLI output."""

    code = "grok_error"


class ConfigError(GrokError):
    code = "configuration_error"


class AuthError(GrokError):
    code = "authentication_error"


class RateLimitError(GrokError):
    code = "rate_limit"


class ProtocolError(GrokError):
    code = "protocol_error"


class TransactionIdError(ProtocolError):
    code = "transaction_id_error"


class TransactionNetworkError(GrokError):
    code = "transaction_network_error"


class EmptyError(GrokError):
    code = "empty_response"


class CredentialChangedError(GrokError):
    code = "credentials_changed"


class CredentialWriteError(GrokError):
    code = "credential_write_error"


@dataclass(frozen=True)
class Config:
    env_file: Path
    provider: str
    model: str


def load_config(path: str | Path | None = None) -> Config:
    """Read configuration metadata only; never return credentials."""
    config_path = Path(path).expanduser().resolve() if path else DEFAULT_CONFIG
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise ConfigError(
            "Cannot read config.json; run init for first-time setup, or check the path and JSON format."
        ) from None
    if not isinstance(data, dict) or set(data) != {"envFile", "provider", "model"}:
        raise ConfigError("config.json must contain exactly envFile, provider, and model.")
    if data["provider"] != "x-web":
        raise ConfigError(
            "Only provider=x-web is supported; providers are never switched automatically."
        )
    if not isinstance(data["model"], str) or not data["model"].strip():
        raise ConfigError("model must be a non-empty X web grokModelOptionId.")
    if not isinstance(data["envFile"], str) or not data["envFile"].strip():
        raise ConfigError("envFile must point to a local credentials file.")
    env_file = Path(data["envFile"]).expanduser()
    if not env_file.is_absolute():
        env_file = config_path.parent / env_file
    return Config(env_file.resolve(), data["provider"], data["model"].strip())


def parse_cookie(value: str) -> dict[str, str]:
    # Values may contain '=' and JSON, so do not parse the whole header as SimpleCookie.
    if not value or len(value) > 64000 or any(c in value for c in "\r\n\0"):
        raise ConfigError(
            "X_COOKIE is empty, too long, or contains line breaks; provide a single-line Cookie request header."
        )
    cookies = {}
    for pair in value.split(";"):
        if not pair.strip():
            continue
        name, sep, content = pair.strip().partition("=")
        if not sep or not re.fullmatch(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+", name):
            raise ConfigError("Invalid X_COOKIE format.")
        cookies[name] = content.strip()
    if not cookies.get("auth_token") or not cookies.get("ct0"):
        raise ConfigError("X_COOKIE must contain non-empty auth_token and ct0 values.")
    try:
        value.encode("ascii")
    except UnicodeEncodeError:
        raise ConfigError(
            "X_COOKIE must be the original ASCII request header from your browser."
        ) from None
    return cookies


@dataclass
class Credentials:
    cookies: dict[str, str] = field(repr=False)
    proxy: str | None = field(default=None, repr=False)


def read_env_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        raise ConfigError(
            "Cannot read the credentials file specified by envFile; run init for first-time setup."
        ) from None


def parse_env(content: str) -> dict:
    try:
        from dotenv import dotenv_values
        from dotenv.parser import parse_stream
    except ImportError:
        raise ConfigError("Missing dependencies; install requirements.txt.") from None
    # Validate before dotenv_values, which otherwise logs parser diagnostics.
    if any(binding.error for binding in parse_stream(StringIO(content))):
        raise ConfigError("The credentials file is not valid dotenv; check its quoting.")
    return dotenv_values(stream=StringIO(content), interpolate=False)


def parse_credentials(content: str) -> Credentials:
    values = parse_env(content)
    cookies = parse_cookie(values.get("X_COOKIE") or "")
    return Credentials(cookies, parse_proxy(values.get("X_PROXY")))


def parse_proxy(value: str | None) -> str | None:
    proxy = (value or "").strip() or None
    if proxy:
        try:
            parsed = urlsplit(proxy)
            parsed.port  # Validate port syntax without exposing the proxy URL.
            valid = parsed.scheme in {"http", "https", "socks5", "socks5h"} and parsed.hostname
        except ValueError:
            valid = False
        if not valid:
            raise ConfigError("X_PROXY must be a valid HTTP(S) or SOCKS5 proxy URL.")
    return proxy


def load_credentials(config: Config) -> Credentials:
    return parse_credentials(read_env_text(config.env_file))


@dataclass(frozen=True)
class ProxyDetection:
    proxy: str | None = field(default=None, repr=False)
    status: str = "not_detected"
    source: str = "unknown"
    reason: str | None = None

    def public(self) -> dict:
        address = None
        if self.proxy:
            parsed = urlsplit(self.proxy)
            host = parsed.hostname
            if ":" in host:
                host = f"[{host}]"
            port = f":{parsed.port}" if parsed.port is not None else ""
            credentials = "<credentials>@" if parsed.username is not None else ""
            address = f"{parsed.scheme}://{credentials}{host}{port}"
        return {
            "status": self.status,
            "detected": bool(self.proxy),
            "proxy": address,
            "source": self.source,
            "reason": self.reason,
        }


def proxy_from_settings(proxies: dict, source: str) -> ProxyDetection:
    """Normalize supported static proxies without exposing their credentials."""
    invalid = False
    for key in ("https", "all", "http", "socks"):
        value = proxies.get(key)
        if not value:
            continue
        invalid = True
        if not isinstance(value, str) or not value.strip():
            continue
        value = value.strip()
        if any(char.isspace() for char in value):
            continue
        if "://" not in value:
            value = ("socks5h://" if key == "socks" else "http://") + value
        if value.startswith("socks://"):
            value = "socks5h://" + value[len("socks://") :]
        try:
            proxy = parse_proxy(value)
        except ConfigError:
            continue
        if proxy:
            return ProxyDetection(proxy, "detected", source)
    if invalid:
        return ProxyDetection(
            status="detection_unavailable", source=source, reason="unsupported_proxy_settings"
        )
    return ProxyDetection(source=source)


def detect_system_proxy() -> ProxyDetection:
    """Inspect environment and native settings; empty macOS output is inconclusive."""
    source = "environment"
    try:
        environment = proxy_from_settings(urllib_request.getproxies_environment(), source)
        if environment.status != "not_detected":
            return environment
        # NO_PROXY alone must not suppress discovery of the native system proxy.
        if sys.platform == "darwin":
            source = "macos_system"
            result = subprocess.run(
                ["/usr/sbin/scutil", "--proxy"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode != 0:
                raise OSError()
            fields = dict(
                re.findall(
                    r"^\s*(HTTPSEnable|HTTPSProxy|HTTPSPort|HTTPEnable|HTTPProxy|HTTPPort|"
                    r"SOCKSEnable|SOCKSProxy|SOCKSPort|ProxyAutoConfigEnable|ProxyAutoDiscoveryEnable)"
                    r"\s*:\s*(.*?)\s*$",
                    result.stdout,
                    re.MULTILINE,
                )
            )
            flags = {key: value for key, value in fields.items() if key.endswith("Enable")}
            if not flags or any(value not in {"0", "1"} for value in flags.values()):
                return ProxyDetection(
                    status="detection_unavailable",
                    source=source,
                    reason="system_settings_unreadable",
                )
            proxies = {}
            for prefix, key in (("HTTPS", "https"), ("HTTP", "http"), ("SOCKS", "socks")):
                if fields.get(prefix + "Enable") != "1":
                    continue
                host, port = fields.get(prefix + "Proxy", ""), fields.get(prefix + "Port", "")
                if not host or not port.isdigit() or not 1 <= int(port) <= 65535:
                    return ProxyDetection(
                        status="detection_unavailable",
                        source=source,
                        reason="unsupported_proxy_settings",
                    )
                if ":" in host and not host.startswith("["):
                    host = f"[{host}]"
                scheme = "socks5h" if key == "socks" else "http"
                proxies[key] = f"{scheme}://{host}:{port}"
            native = proxy_from_settings(proxies, source)
            if native.status != "not_detected":
                return native
            if any(
                fields.get(key) == "1"
                for key in ("ProxyAutoConfigEnable", "ProxyAutoDiscoveryEnable")
            ):
                return ProxyDetection(
                    status="detection_unavailable",
                    source=source,
                    reason="automatic_proxy_requires_manual_configuration",
                )
            return native
        if sys.platform == "win32":
            source = "windows_system"
            return proxy_from_settings(urllib_request.getproxies_registry(), source)
        return environment
    except Exception:
        return ProxyDetection(
            status="detection_unavailable", source=source, reason="system_settings_unreadable"
        )


def with_env_value(content: str, key: str, value: str) -> str:
    """Replace one dotenv entry; preserve other values and comments."""
    from dotenv.parser import parse_stream

    parse_env(content)
    quoted = "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"
    entry = f"{key}={quoted}\n"
    output = []
    replaced = False
    for binding in parse_stream(StringIO(content)):
        if binding.key == key:
            if not replaced:
                output.append(entry)
                replaced = True
        else:
            output.append(binding.original.string)
    text = "".join(output)
    if not replaced:
        text += ("\n" if text and not text.endswith("\n") else "") + entry
    return text


def with_cookie(content: str, cookie: str) -> str:
    """Replace only X_COOKIE; preserve proxy, other entries and comments."""
    return with_env_value(content, "X_COOKIE", cookie)


def configure_proxy(
    content: str,
    detection: ProxyDetection,
    *,
    use_system_proxy=False,
    skip_proxy=False,
    interactive=False,
) -> tuple[str, str]:
    current = parse_proxy(parse_env(content).get("X_PROXY"))
    if use_system_proxy:
        if not detection.proxy:
            raise ConfigError("No supported system proxy was detected; configure X_PROXY manually.")
        return with_env_value(content, "X_PROXY", detection.proxy), "applied"
    if current:
        return content, "existing"
    if not detection.proxy:
        return content, detection.status
    if interactive and not skip_proxy:
        print(
            f"Detected system proxy: {detection.public()['proxy']}\n"
            "Use this proxy for X requests and Transaction ID generation? [y/N]: ",
            end="",
            file=sys.stderr,
            flush=True,
        )
        try:
            answer = input().strip().lower()
        except EOFError:
            answer = ""
        if answer in {"y", "yes"}:
            return with_env_value(content, "X_PROXY", detection.proxy), "applied"
    return content, "skipped" if interactive or skip_proxy else "confirmation_required"


def setup_file_guide(detection: ProxyDetection, proxy_status: str) -> None:
    """Show a complete synthetic template, never actual credential contents."""
    if proxy_status == "applied":
        print("The confirmed system proxy was saved in X_PROXY.", file=sys.stderr)
    elif proxy_status == "existing":
        print("The existing X_PROXY setting was preserved.", file=sys.stderr)
    elif proxy_status in {"skipped", "confirmation_required"} and detection.proxy:
        print(
            f"System proxy detected: {detection.public()['proxy']}. It was not applied.\n"
            "Your explicit confirmation is required before applying it.\n"
            "To apply it, run init --use-system-proxy with your chosen --env-file\n"
            "or existing --config. Alternatively, edit X_PROXY in your Cookie file.\n"
            "An empty X_PROXY uses a direct connection, which may fail on your network.",
            file=sys.stderr,
        )
    elif proxy_status == "detection_unavailable":
        print(
            "System proxy settings could not be reliably read; this does not mean no proxy exists. "
            "Run detect-proxy in your own terminal to check, or provide the proxy address manually.",
            file=sys.stderr,
        )
    print(
        "\nCookie file format (UTF-8 dotenv, one variable per line; examples only):\n"
        "X_COOKIE='your-cookies...'\n"
        "X_PROXY=''\n\n"
        "X_COOKIE: required, full Cookie request-header value on one line; auth_token and ct0\n"
        "are validation checks only, not a two-cookie template. Keep EVERY cookie pair from the\n"
        "copied header; do not extract just those two keys. Do not include the Cookie: prefix.\n"
        "X_PROXY: optional proxy URL; empty means direct. For example:\n"
        "X_PROXY='http://127.0.0.1:10808'\n"
        "Use your actual proxy address and port; this example is not a default.\n"
        "Supported schemes: http, https, socks5, socks5h. Put proxy passwords only in this file.\n"
        "Keep the quotes; escape embedded single quotes as \\' and backslashes as \\\\.\n"
        "Do not paste these placeholder values over an existing Cookie or proxy.\n"
        "On macOS/Linux, restrict this file to mode 0600.\n"
        "The selected config.json must contain exactly these fields (replace envFile):\n"
        '{"envFile":"/absolute/path/you/choose/cookies.env","provider":"x-web","model":"grok-4-auto"}\n'
        "Keep credentials in the dotenv file, not config.json. Run check with the same config\n"
        "after setup. check is offline and does not prove X connectivity.",
        file=sys.stderr,
    )


def atomic_write(path: Path, content: str):
    """Same-directory replacement; the new file is owner-only from creation."""
    fd, temporary = tempfile.mkstemp(prefix=".x-grok-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            os.chmod(temporary, 0o600)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class CookieStore:
    """Persist refreshed X_COOKIE with a process lock and snapshot comparison."""

    def __init__(self, path: Path):
        self.path = path
        self.source = read_env_text(path)

    def ensure_current(self):
        if read_env_text(self.path) != self.source:
            raise CredentialChangedError(
                "Credentials changed outside this client. Create a new client; do not blindly resend a request that may have completed."
            )

    def save(self, cookies: dict[str, str]):
        from filelock import FileLock, Timeout

        value = "; ".join(f"{name}={value}" for name, value in cookies.items())
        updated = with_cookie(self.source, value)
        try:
            # Never hold the file lock during network calls or wait on another caller.
            with FileLock(str(self.path) + ".lock", timeout=0, mode=0o600):
                self.ensure_current()
                atomic_write(self.path, updated)
                self.source = updated
        except Timeout:
            raise CredentialWriteError(
                "Another process is writing credentials; refreshed values were not saved. The remote request may have completed; do not blindly retry."
            ) from None
        except OSError:
            raise CredentialWriteError(
                "Cannot save refreshed cookies; check directory permissions and disk space. The remote request may have completed; do not blindly retry."
            ) from None


def defer_setup(detection: ProxyDetection, *, skip_proxy=False) -> dict:
    """Leave files untouched and explain how to finish setup later."""
    print(
        "Cookie setup deferred; no files were created or changed.\n"
        "When ready:\n"
        "1. Choose a private location for your cookie file; there is no default.\n"
        "2. Run init --env-file /absolute/path/you/choose/cookies.env.\n"
        "   init can use an existing dotenv file or help create one at that location.\n"
        "3. To create it manually, use a local editor to save these dotenv entries:\n"
        "   X_COOKIE='your-cookies...'\n"
        "   X_PROXY=''\n"
        "   On macOS/Linux, restrict the file permissions to 0600.\n"
        "4. Run init --env-file with that path to link the file, then run check.\n"
        "   Keep the same --config selection for each command.\n\n"
        + COOKIE_SETUP_HELP.replace(
            "Paste the value into the hidden terminal prompt below and press Enter.",
            "Save the value locally, or paste it into the hidden prompt when you run init later.",
        ),
        file=sys.stderr,
    )
    proxy_status = (
        ("skipped" if skip_proxy else "confirmation_required")
        if detection.proxy
        else detection.status
    )
    setup_file_guide(detection, proxy_status)
    return {
        "ok": True,
        "status": "setup_deferred",
        "cookie_configured": False,
        "proxy_setup": proxy_status,
        "proxy_detection": detection.public(),
        "network_checked": False,
    }


def initialize(
    config_path: str | Path | None,
    *,
    env_file: str | Path | None = None,
    cookie_stdin=False,
    replace_cookie=False,
    use_system_proxy=False,
    skip_proxy=False,
) -> dict:
    """Use a user-selected cookie file; never choose its location implicitly."""
    from filelock import FileLock, Timeout

    detection = detect_system_proxy()
    path = Path(config_path).expanduser().resolve() if config_path else DEFAULT_CONFIG
    existing_config = path.read_text(encoding="utf-8") if path.exists() else None
    config = load_config(path) if existing_config is not None else None
    if env_file is None and config is not None:
        env_file = config.env_file
    if env_file is None:
        if cookie_stdin or not sys.stdin.isatty():
            return defer_setup(detection, skip_proxy=skip_proxy)
        print(
            "Where is your Cookie dotenv file? Enter an existing file or a path you choose.\n"
            "Relative paths are resolved from the configuration directory.\n"
            f"Configuration file: {path}\n"
            "Cookie file path (leave blank to finish setup later): ",
            end="",
            file=sys.stderr,
            flush=True,
        )
        try:
            env_file = input().strip()
        except EOFError:
            return defer_setup(detection, skip_proxy=skip_proxy)
    if not str(env_file).strip():
        return defer_setup(detection, skip_proxy=skip_proxy)
    selected = Path(env_file).expanduser()
    if not selected.is_absolute():
        selected = path.parent / selected
    selected = selected.resolve()
    if selected == path:
        raise ConfigError("The cookie file and configuration file must have different paths.")
    if config is not None and config.env_file != selected:
        raise ConfigError(
            "--env-file differs from the configured envFile; choose another --config file "
            "or explicitly edit envFile in the existing configuration."
        )
    config = config or Config(selected, "x-web", "grok-4-auto")
    existing_env = read_env_text(selected) if selected.exists() else None
    values = parse_env(existing_env or "")
    reuse_cookie = bool(values.get("X_COOKIE")) and not replace_cookie
    if reuse_cookie:
        if cookie_stdin:
            raise ConfigError(
                "A cookie is already configured; use init --replace-cookie to replace it."
            )
        parse_credentials(existing_env)
        updated = existing_env
    else:
        if cookie_stdin:
            cookie = sys.stdin.read(64002).removesuffix("\n").removesuffix("\r")
        else:
            if not sys.stdin.isatty():
                return defer_setup(detection, skip_proxy=skip_proxy)
            print(
                f"Configuration file: {path}\n"
                f"Your selected Cookie file: {selected}\n\n" + COOKIE_SETUP_HELP,
                file=sys.stderr,
            )
            with warnings.catch_warnings():
                warnings.simplefilter("error", getpass.GetPassWarning)
                try:
                    cookie = getpass.getpass("Paste your X Cookie (input hidden): ")
                except EOFError:
                    return defer_setup(detection, skip_proxy=skip_proxy)
                except getpass.GetPassWarning:
                    raise ConfigError(
                        "The terminal cannot hide input; initialization was cancelled "
                        "without writing credentials."
                    ) from None
            if not cookie.strip():
                return defer_setup(detection, skip_proxy=skip_proxy)
        parse_cookie(cookie)
        updated = with_cookie(existing_env if existing_env is not None else "X_PROXY=''\n", cookie)
        # Validate preserved proxy as well before writing anything.
        parse_credentials(updated)
    updated, proxy_status = configure_proxy(
        updated,
        detection,
        use_system_proxy=use_system_proxy,
        skip_proxy=skip_proxy,
        interactive=not cookie_stdin and sys.stdin.isatty(),
    )
    parse_credentials(updated)
    try:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        selected.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with (
            FileLock(str(path) + ".lock", timeout=0, mode=0o600),
            FileLock(str(selected) + ".lock", timeout=0, mode=0o600),
        ):
            latest_config = path.read_text(encoding="utf-8") if path.exists() else None
            latest_env = read_env_text(selected) if selected.exists() else None
            if latest_config != existing_config or latest_env != existing_env:
                raise CredentialChangedError(
                    "Configuration changed during initialization; nothing was overwritten. Run init again."
                )
            if existing_config is None:
                atomic_write(
                    path,
                    json.dumps(
                        {
                            "envFile": str(selected),
                            "provider": config.provider,
                            "model": config.model,
                        },
                        indent=2,
                    )
                    + "\n",
                )
            if updated != existing_env:
                atomic_write(selected, updated)
    except Timeout:
        raise CredentialWriteError(
            "Another process is writing configuration; initialization stopped."
        ) from None
    except OSError:
        raise CredentialWriteError(
            "Initialization could not write files; check directory permissions and disk space, then run init again."
        ) from None
    if not cookie_stdin:
        action = "Using existing Cookie file" if reuse_cookie else "Cookie saved to"
        print(
            f"{action}: {selected}.\n"
            "Next, run check with the same configuration to validate local setup.\n"
            "This setup did not test online authentication or Grok access.",
            file=sys.stderr,
        )
    if not cookie_stdin or proxy_status in {
        "skipped",
        "confirmation_required",
        "detection_unavailable",
    }:
        setup_file_guide(detection, proxy_status)
    return {
        "ok": True,
        "status": "configured",
        "cookie_configured": True,
        "cookie_persistence": "env_file",
        "proxy_setup": proxy_status,
        "proxy_detection": detection.public(),
        "proxy_configured": bool(parse_proxy(parse_env(updated).get("X_PROXY"))),
        "network_checked": False,
    }


class TransactionIds:
    """Cache public web bootstrap for 3 h; generate a fresh ID for each request."""

    def __init__(self, proxy: str | None):
        self.proxy = proxy
        self.client = None
        self.built_at = 0.0
        self.lock = asyncio.Lock()

    async def get(self, method: str, path: str) -> str:
        import requests

        async with self.lock:
            cached = self.client is not None and time.monotonic() - self.built_at < 10800
            for attempt in range(2 if cached else 1):
                try:
                    if self.client is None or time.monotonic() - self.built_at >= 10800:
                        self.client = await asyncio.to_thread(self._build)
                        self.built_at = time.monotonic()
                    value = self.client.generate_transaction_id(method=method, path=path)
                    if not isinstance(value, str) or not value:
                        raise ValueError()
                    return value
                except requests.RequestException:
                    raise TransactionNetworkError(
                        "Transaction ID bootstrap failed; check the network, proxy, and HTTP status. No emergency upgrade was triggered."
                    ) from None
                except ImportError:
                    raise ConfigError(
                        "Transaction ID dependencies are missing or cannot be imported; check your requirements.txt installation."
                    ) from None
                except Exception:
                    self.client = None
                    self.built_at = 0.0
                    if not (cached and attempt == 0):
                        raise TransactionIdError(
                            "Dynamic transaction ID parsing or generation failed; see the dependency maintenance guide. Static IDs are not supported."
                        ) from None

    def _build(self):
        import bs4
        import requests
        from x_client_transaction import ClientTransaction
        from x_client_transaction.utils import (
            generate_headers,
            get_ondemand_file_url,
            handle_x_migration,
        )

        class BoundedSession(requests.Session):
            def request(self, method, url, **kwargs):
                kwargs.setdefault("timeout", 30)
                response = super().request(method, url, **kwargs)
                response.raise_for_status()
                return response

        # Anonymous bootstrap: never put the account Cookie in this session.
        with BoundedSession() as session:
            session.trust_env = False
            session.headers.update(generate_headers())
            if self.proxy:
                session.proxies.update(http=self.proxy, https=self.proxy)
            home = handle_x_migration(session)
            response = session.get(get_ondemand_file_url(response=home))
            response.raise_for_status()
            script = bs4.BeautifulSoup(response.content, "html.parser")
            return ClientTransaction(home_page_response=home, ondemand_file_response=script)


async def check_transaction(config: Config) -> dict:
    """Anonymous bootstrap and local generation; never send an account Cookie."""
    from importlib.metadata import version

    proxy = parse_proxy(parse_env(read_env_text(config.env_file)).get("X_PROXY"))
    provider = TransactionIds(proxy)
    try:
        await asyncio.wait_for(provider.get("POST", urlsplit(RESPONSE_URL).path), timeout=90)
    except asyncio.TimeoutError:
        raise TransactionNetworkError(
            "Transaction ID bootstrap timed out; no emergency upgrade was triggered."
        ) from None
    return {
        "ok": True,
        "package": "XClientTransaction",
        "version": version("XClientTransaction"),
        "transaction_id_generated": True,
        "server_acceptance_checked": False,
    }


def collect_stream(body: str) -> str:
    pieces = []
    for line in body.splitlines():
        line = line.strip()
        if not line or line.startswith(":"):
            continue
        if line.startswith("data:"):
            line = line[5:].strip()
        if line == "[DONE]":
            continue
        try:
            item = json.loads(line)
        except ValueError:
            raise ProtocolError(
                "The Grok stream contains invalid JSON; a potentially truncated answer was not returned."
            ) from None
        if not isinstance(item, dict):
            raise ProtocolError("The Grok stream structure has changed.")
        result = item.get("result") or {}
        if not isinstance(result, dict):
            raise ProtocolError("The Grok result structure has changed.")
        if item.get("error") or item.get("errors") or result.get("error") or result.get("errors"):
            raise ProtocolError(
                "The Grok stream reported an error; the raw response body was withheld."
            )
        if result.get("messageTag") == "final" and not result.get("isThinking"):
            piece = result.get("message")
            if not isinstance(piece, str):
                raise ProtocolError("A Grok final fragment is not text.")
            pieces.append(piece)
    text = "".join(pieces).strip()
    if not text:
        raise EmptyError(
            "Grok returned no final text; stopped without creating another conversation or retrying."
        )
    return text


def parse_summary(raw: str) -> dict:
    start, end = raw.find("{"), raw.rfind("}")
    try:
        data = json.loads(raw[start : end + 1]) if 0 <= start < end else None
    except ValueError:
        data = None
    if data is None:
        data = {"summary": raw.strip(), "media_description": "", "tags": []}
        structured = False
    else:
        structured = True
    if not isinstance(data, dict):
        raise ProtocolError("Summary JSON must be an object.")
    summary, media, tags = (
        data.get("summary", ""),
        data.get("media_description", ""),
        data.get("tags") or [],
    )
    if (
        not isinstance(summary, str)
        or not isinstance(media, str)
        or not isinstance(tags, list)
        or any(not isinstance(tag, str) for tag in tags)
    ):
        raise ProtocolError("Summary fields have unexpected types.")
    if not (summary.strip() or media.strip()):
        raise EmptyError("Both the summary and media description are empty.")
    return dict(summary=summary, media_description=media, tags=tags, structured=structured)


def normalize_tweet_url(value: str) -> str:
    if not re.fullmatch(
        r"https://(?:x\.com|twitter\.com)/(?:[A-Za-z0-9_]+/status|i/web/status)/[0-9]+(?:\?[^#\s]*)?",
        value,
    ):
        raise ConfigError("Provide a valid post URL: https://x.com/username/status/numeric-id.")
    parsed = urlsplit(value)
    return "https://x.com" + parsed.path


class GrokClient:
    def __init__(self, config: Config):
        self.config = config
        self.cookie_store = CookieStore(config.env_file)
        self.credentials = parse_credentials(self.cookie_store.source)
        self.transaction_ids = TransactionIds(self.credentials.proxy)
        self.blocked = False
        self.lock = asyncio.Lock()

    def _refresh_cookies(self, headers: list[str]):
        cookies = dict(self.credentials.cookies)
        for header in headers:
            jar = SimpleCookie()
            try:
                jar.load(header)
            except CookieError:
                continue
            for name, item in jar.items():
                max_age = None
                if item["max-age"]:
                    try:
                        max_age = int(item["max-age"])
                    except ValueError:
                        pass
                expired = max_age is not None and max_age <= 0
                if max_age is None and item["expires"]:
                    try:
                        expires = parsedate_to_datetime(item["expires"])
                        expired |= expires <= datetime.now(timezone.utc)
                    except (ValueError, TypeError, OverflowError):
                        pass
                if expired or not item.value:
                    cookies.pop(name, None)
                else:
                    cookies[name] = item.value
        if cookies != self.credentials.cookies:
            # Write before adopting: a failed write must not pretend persistence worked.
            self.cookie_store.save(cookies)
            self.credentials.cookies = cookies

    async def _request(self, url: str, payload: dict, *, plain=False) -> str:
        import httpx

        if self.blocked:
            raise AuthError(
                "This client is no longer authenticated; update credentials and create a new client."
            )
        if url not in {CREATE_URL, RESPONSE_URL}:
            raise ConfigError(
                "Refusing to send credentials outside the configured X/Grok endpoints."
            )
        self.cookie_store.ensure_current()
        cookies = self.credentials.cookies
        if not cookies.get("auth_token") or not cookies.get("ct0"):
            self.blocked = True
            raise AuthError("Required login cookies are missing; update the credentials file.")
        tx = await self.transaction_ids.get("POST", urlsplit(url).path)
        self.cookie_store.ensure_current()
        headers = {
            "authorization": BEARER,
            "x-csrf-token": cookies["ct0"],
            "cookie": "; ".join(f"{key}={value}" for key, value in cookies.items()),
            "content-type": "text/plain;charset=UTF-8" if plain else "application/json",
            "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "x-twitter-active-user": "yes",
            "x-twitter-auth-type": "OAuth2Session",
            "x-twitter-client-language": "en",
            "referer": "https://x.com/",
            "origin": "https://x.com",
            "x-client-transaction-id": tx,
        }
        proxy = self.credentials.proxy
        if proxy and proxy.startswith("socks5h://"):
            proxy = "socks5://" + proxy[len("socks5h://") :]
        try:
            async with httpx.AsyncClient(
                proxy=proxy, trust_env=False, follow_redirects=False, timeout=120 if plain else 60
            ) as client:
                async with client.stream(
                    "POST",
                    url,
                    headers=headers,
                    content=json.dumps(payload, ensure_ascii=False).encode(),
                ) as response:
                    self._refresh_cookies(response.headers.get_list("set-cookie"))
                    if response.status_code in (401, 403):
                        self.blocked = True
                        raise AuthError(
                            f"X returned HTTP {response.status_code}; check authentication, Grok access, or account restrictions."
                        )
                    if response.status_code == 429:
                        raise RateLimitError(
                            "X/Grok returned HTTP 429; stopped. Retry manually later."
                        )
                    if not 200 <= response.status_code < 300:
                        raise ProtocolError(
                            f"X/Grok returned HTTP {response.status_code}; the response body was withheld."
                        )
                    content = bytearray()
                    async for chunk in response.aiter_bytes():
                        content.extend(chunk)
                        if len(content) > 8 * 1024 * 1024:
                            raise ProtocolError("The response exceeds the 8 MiB limit.")
                    return content.decode("utf-8")
        except httpx.HTTPError:
            raise GrokError(
                "The network request failed or timed out; no retry was attempted. A remote conversation may already exist."
            ) from None
        except UnicodeError:
            raise ProtocolError("The Grok response is not valid UTF-8.") from None

    async def ask(self, message: str, conversation_id: str | None = None) -> dict:
        if not isinstance(message, str) or not message.strip():
            raise ConfigError("The prompt must not be empty.")
        if conversation_id is not None and (
            not isinstance(conversation_id, str) or not conversation_id.strip()
        ):
            raise ConfigError("conversation_id must be a non-empty string.")
        async with self.lock:
            try:
                return await asyncio.wait_for(
                    self._ask(message, conversation_id), timeout=CALL_TIMEOUT_SECONDS
                )
            except asyncio.TimeoutError:
                raise GrokError(
                    "The call exceeded the 180-second total timeout; the remote request may have completed. Do not blindly retry."
                ) from None

    async def _ask(self, message: str, conversation_id: str | None) -> dict:
        if conversation_id is None:
            raw = await self._request(CREATE_URL, {"variables": {}, "queryId": QUERY_ID})
            try:
                data = json.loads(raw)
                if data.get("errors"):
                    raise ValueError()
                conversation_id = data["data"]["create_grok_conversation"]["conversation_id"]
                if (
                    not isinstance(conversation_id, (str, int))
                    or isinstance(conversation_id, bool)
                    or not str(conversation_id).strip()
                ):
                    raise ValueError()
                conversation_id = str(conversation_id)
            except (ValueError, KeyError, TypeError, AttributeError):
                raise ProtocolError(
                    "Conversation creation returned no valid conversation_id; check the web protocol or account permissions."
                ) from None
        body = {
            "responses": [
                {"message": message, "sender": 1, "promptSource": "", "fileAttachments": []}
            ],
            "systemPromptName": "",
            "grokModelOptionId": self.config.model,
            "modelMode": "MODEL_MODE_AUTO",
            "conversationId": conversation_id,
            "returnSearchResults": True,
            "returnCitations": True,
            "promptMetadata": {"promptSource": "NATURAL", "action": "INPUT"},
            "imageGenerationCount": 0,
            "requestFeatures": {"eagerTweets": True, "serverHistory": True},
            "enableSideBySide": True,
            "toolOverrides": {},
            "modelConfigOverride": {},
            "isTemporaryChat": False,
        }
        text = collect_stream(await self._request(RESPONSE_URL, body, plain=True))
        return {"conversation_id": conversation_id, "model": self.config.model, "text": text}

    async def describe(self, tweet_url: str) -> dict:
        url = normalize_tweet_url(tweet_url)
        result = await self.ask(f"{PROMPT}\n{url}")
        return {
            "conversation_id": result["conversation_id"],
            "model": result["model"],
            "tweet_url": url,
            **parse_summary(result["text"]),
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", help="Config JSON path; default ~/.config/x-grok-client/config.json"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    setup = commands.add_parser("init", help="Choose or link your Cookie file; no network calls")
    setup.add_argument(
        "--env-file",
        help="Your chosen Cookie dotenv path; relative to the config directory, no default",
    )
    setup.add_argument(
        "--cookie-stdin",
        action="store_true",
        help="Read from a trusted local pipe, never a Cookie command-line argument",
    )
    setup.add_argument(
        "--replace-cookie", action="store_true", help="Explicitly replace an existing login Cookie"
    )
    proxy_choice = setup.add_mutually_exclusive_group()
    proxy_choice.add_argument(
        "--use-system-proxy",
        action="store_true",
        help="Explicitly apply the detected system proxy to your chosen Cookie file",
    )
    proxy_choice.add_argument(
        "--skip-proxy",
        action="store_true",
        help="Skip the proxy question and show instructions for later setup",
    )
    commands.add_parser(
        "detect-proxy",
        help="Read system proxy settings locally; no credentials or network requests",
    )
    commands.add_parser(
        "check", help="Check local configuration/dependencies without any network calls"
    )
    commands.add_parser(
        "check-transaction",
        help="Anonymous network bootstrap and ID generation; no Grok conversation",
    )
    ask = commands.add_parser("ask", help="Send a question to X web Grok")
    source = ask.add_mutually_exclusive_group(required=True)
    source.add_argument("--prompt")
    source.add_argument("--prompt-file", help="UTF-8 file; use - for stdin")
    ask.add_argument(
        "--conversation-id", help="Continue a known conversation of the configured account"
    )
    describe = commands.add_parser(
        "describe", help="Summarize an X post including media via its link"
    )
    describe.add_argument("tweet_url")
    args = parser.parse_args()
    try:
        if args.command == "detect-proxy":
            detection = detect_system_proxy()
            print(
                json.dumps(
                    {
                        "ok": detection.status != "detection_unavailable",
                        **detection.public(),
                        "network_checked": False,
                    },
                    ensure_ascii=False,
                )
            )
            return 1 if detection.status == "detection_unavailable" else 0
        if args.command == "init":
            print(
                json.dumps(
                    initialize(
                        args.config,
                        env_file=args.env_file,
                        cookie_stdin=args.cookie_stdin,
                        replace_cookie=args.replace_cookie,
                        use_system_proxy=args.use_system_proxy,
                        skip_proxy=args.skip_proxy,
                    ),
                    ensure_ascii=False,
                )
            )
            return 0
        config = load_config(args.config)
        if args.command == "check-transaction":
            print(json.dumps(asyncio.run(check_transaction(config)), ensure_ascii=False))
            return 0
        client = GrokClient(config)
        if args.command == "check":
            for module in (
                "httpx",
                "requests",
                "bs4",
                "x_client_transaction",
                "socksio",
                "socks",
                "filelock",
                "packaging",
            ):
                import_module(module)
            output = {
                "ok": True,
                "provider": config.provider,
                "model": config.model,
                "cookie_configured": True,
                "proxy_configured": bool(client.credentials.proxy),
                "cookie_persistence": "env_file",
                "network_checked": False,
            }
        else:
            from update_transaction import MaintenanceError, runtime_maintenance

            if args.command == "ask":
                message = (
                    args.prompt
                    if args.prompt is not None
                    else (
                        sys.stdin.read()
                        if args.prompt_file == "-"
                        else Path(args.prompt_file).read_text(encoding="utf-8")
                    )
                )
                if not message.strip():
                    raise ConfigError("The prompt must not be empty.")
            else:
                normalize_tweet_url(args.tweet_url)
            config_path = (
                Path(args.config).expanduser().resolve() if args.config else DEFAULT_CONFIG
            )
            try:
                with runtime_maintenance(config_path) as maintenance:
                    if maintenance["status"] != "already_checked":
                        print(
                            json.dumps(
                                {"event": "dependency_maintenance", **maintenance},
                                ensure_ascii=False,
                            ),
                            file=sys.stderr,
                        )
                    output = asyncio.run(
                        client.ask(message, args.conversation_id)
                        if args.command == "ask"
                        else client.describe(args.tweet_url)
                    )
            except MaintenanceError as exc:
                raise GrokError(str(exc)) from None
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0
    except GrokError as exc:
        print(
            json.dumps({"ok": False, "error": exc.code, "message": str(exc)}, ensure_ascii=False),
            file=sys.stderr,
        )
        return 1
    except ImportError:
        print(
            '{"ok":false,"error":"missing_dependency","message":"Install requirements.txt."}',
            file=sys.stderr,
        )
        return 1
    except (OSError, UnicodeError):
        print(
            '{"ok":false,"error":"file_error","message":"Cannot read or write a required file."}',
            file=sys.stderr,
        )
        return 1
    except Exception:
        print(
            '{"ok":false,"error":"unexpected_error","message":"Unexpected client error; do not expose credentials or raw responses when troubleshooting."}',
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
