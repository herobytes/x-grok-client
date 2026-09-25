# Connection flow

The client uses the X web Grok protocol directly. It has no database, browser
runtime, or dependency on another application. Its responsibilities are local
configuration, authenticated requests, response parsing, and cookie persistence.

## Request sequence

1. `load_config()` reads configuration metadata. Constructing `GrokClient` loads
   `X_COOKIE` and optional `X_PROXY` from `envFile`, requiring `auth_token` and `ct0`.
2. An anonymous `requests.Session` uses XClientTransaction's `handle_x_migration()`
   to fetch the actual X homepage and its on-demand script. The bootstrap never
   sends account cookies. The generator is cached for three hours, but each API
   request receives a fresh transaction ID for its HTTP method and path.
3. A new conversation posts to
   `https://x.com/i/api/graphql/<QUERY_ID>/CreateGrokConversation` with
   `{"variables": {}, "queryId": "<QUERY_ID>"}`. `QUERY_ID` is defined in
   `scripts/grok_client.py`. The returned
   `data.create_grok_conversation.conversation_id` is required. Continuing a known
   conversation skips this step.
4. The answer request posts JSON text to
   `https://grok.x.com/2/grok/add_response.json` with content type
   `text/plain;charset=UTF-8`. Key fields include `responses[0].message`,
   `conversationId`, and `grokModelOptionId`. Requests use `MODEL_MODE_AUTO`,
   enable search/citation and history flags, set `imageGenerationCount=0`, and
   set `isTemporaryChat=false`. These flags do not guarantee model access or
   implement separate citation export.
5. Both requests include the public X web bearer token, account cookies,
   `x-csrf-token=ct0`, OAuth2Session headers, Origin/Referer, and a dynamic
   transaction ID. Authenticated redirects are disabled. Changed `Set-Cookie`
   values are persisted before updating in-memory state. HTTP 401/403 blocks
   that client instance; HTTP 429 is not retried.
6. Response text is normally NDJSON. Only non-thinking fragments with
   `result.messageTag == "final"` are concatenated. The parser accepts `data:`
   prefixes and `[DONE]`, ignores header and tool cards, and rejects invalid JSON,
   explicit stream errors, or empty final text.
7. `describe` sends a normalized post URL with an English summary prompt. Grok
   interprets the post and media. The client tries to parse JSON between the first
   `{` and last `}`; if parsing fails, it preserves the text and returns
   `structured=false`. Empty summary and media description fields are rejected.

## Timeouts and failure behavior

- Authenticated requests are never replayed automatically. A network error can
  occur after a conversation has already been created.
- A stale cached transaction generator can be rebuilt once anonymously. This
  does not replay an authenticated request. If generation still raises
  `transaction_id_error`, CLI `ask`/`describe` force one validated dependency update
  under the environment lock, then resume the unsent request in a fresh process.
  An already created conversation ID is preserved. A second error stops recovery.
- HTTP read timeouts are 60 seconds for conversation creation and 120 seconds for
  answers. A combined asynchronous timeout of 180 seconds covers `ask`; responses
  are limited to 8 MiB.
- Synchronous bootstrap requests have a 30-second timeout each. Cancelling an
  awaiting coroutine does not immediately terminate an in-progress worker thread.
- Dependency maintenance precedes the request and has its own subprocess timeouts;
  its duration is not included in the 180-second `ask` budget. A transaction repair
  runs after the failed attempt finishes; its single retry has a new 180-second
  `ask` budget and a 210-second subprocess timeout. No package installation runs
  in an abandoned asynchronous worker thread.
- Cookie writes use atomic replacement, a process lock, and source-file snapshots.
  A conflict or write failure stops the call without overwriting newer credentials.

See [dependency maintenance](dependency-maintenance.md) for update timing and
[configuration](configuration.md) for credential storage.

## Python integration

Add the absolute `scripts` directory to your import path, then import
`GrokClient` and `load_config`:

```python
import asyncio
import sys

sys.path.insert(0, "/absolute/path/to/x-grok-client/scripts")
from grok_client import GrokClient, load_config

async def main():
    client = GrokClient(load_config())
    result = await client.ask("Explain cooperative multitasking.")
    print(result["text"])

asyncio.run(main())
```

Use `await client.ask(prompt, conversation_id)` for a follow-up or
`await client.describe(post_url)` for a summary. Requests on one instance are
serialized. Independent instances reuse refreshed cookies through the credentials
file; conflicts require constructing a fresh client.

Direct imports do not run CLI dependency maintenance or hold its environment lock.
They also do not automatically repair transaction ID failures.
Coordinate maintenance before starting long-lived application processes; do not
replace a dependency while a process is still using its imported modules.

## Compatibility boundaries

Endpoint query IDs, the public bearer token, browser headers, request fields, and
stream formats can change. HTTP 403 may reflect account restrictions or access
permissions rather than a protocol defect. No static transaction ID fallback,
model discovery, media upload, image generation, conversation listing, or separate
search-result export is implemented. Offline checks do not prove that the current
web service accepts these requests.
