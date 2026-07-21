"""LLM providers for LLMPlayer — one tiny interface, two backends.

    complete(system: str, user: str) -> str

returns the model's raw text. The player turns that text into an Action; the
provider only speaks tokens, so both backends share the same parser.

- ClaudeProvider   — Anthropic API via the official SDK. Defaults to a low-cost
  model (Haiku). Uses the SDK's default credential resolution, so it works with an
  ANTHROPIC_API_KEY *or* an `ant auth login` profile.
      NOTE: the Anthropic API is metered per token. A Claude Pro/Max subscription
      covers claude.ai and Claude Code, not raw Messages API calls — see README.
- LlamaCppProvider — a local `llama-server` (llama.cpp) over its OpenAI-compatible
  /v1/chat/completions endpoint. No API key, no cloud, no per-token cost.

Both are constructed lazily so importing this module never requires the optional
`anthropic` dependency; only building a ClaudeProvider does.
"""
from __future__ import annotations

import json
import urllib.request


def make_provider(agent_cfg: dict):
    """Build the provider named by agent_cfg['provider'] ('claude' | 'llamacpp')."""
    kind = agent_cfg.get("provider", "claude")
    if kind == "claude":
        return ClaudeProvider(
            model=agent_cfg.get("model", "claude-haiku-4-5"),
            max_tokens=agent_cfg.get("max_tokens", 64),
        )
    if kind == "llamacpp":
        lc = agent_cfg.get("llamacpp", {})
        return LlamaCppProvider(
            host=lc.get("host", "127.0.0.1"),
            port=lc.get("port", 8080),
            model=agent_cfg.get("model", "local"),
            max_tokens=agent_cfg.get("max_tokens", 64),
        )
    raise ValueError(f"unknown agent.provider: {kind!r} (expected 'claude' or 'llamacpp')")


class ClaudeProvider:
    """Anthropic Messages API. Low max_tokens — a move pick is one short line."""

    def __init__(self, model: str = "claude-haiku-4-5", max_tokens: int = 64) -> None:
        import anthropic  # optional dep; only needed for this provider
        self.model = model
        self.max_tokens = max_tokens
        self._client = anthropic.Anthropic()   # default credential resolution

    def complete(self, system: str, user: str) -> str:
        resp = self._client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(b.text for b in resp.content if b.type == "text").strip()


class LlamaCppProvider:
    """Local llama.cpp server (`llama-server`), OpenAI-compatible chat endpoint."""

    def __init__(self, host: str = "127.0.0.1", port: int = 8080,
                 model: str = "local", max_tokens: int = 64) -> None:
        self.url = f"http://{host}:{port}/v1/chat/completions"
        self.model = model
        self.max_tokens = max_tokens

    def complete(self, system: str, user: str) -> str:
        payload = json.dumps({
            "model": self.model,
            "max_tokens": self.max_tokens,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }).encode("utf-8")
        req = urllib.request.Request(self.url, data=payload,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read())
        return data["choices"][0]["message"]["content"].strip()
