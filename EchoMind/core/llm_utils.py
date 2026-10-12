"""LLM response helpers shared by Anthropic-compatible providers."""
from typing import Any, Dict, Iterable, List
from urllib.parse import urlparse


def extract_text_content(content: Iterable[Any]) -> str:
    """Return text blocks from Anthropic-style response content."""
    texts: List[str] = []
    for block in content or []:
        if isinstance(block, str):
            texts.append(block)
            continue

        block_type = getattr(block, "type", None)
        text = getattr(block, "text", None)
        if isinstance(block, dict):
            block_type = block.get("type", block_type)
            text = block.get("text", text)

        if isinstance(text, str) and (block_type in (None, "text")):
            texts.append(text)

    return "\n".join(t for t in texts if t)


def structured_output_options(client: Any) -> Dict[str, Any]:
    """Keep DeepSeek's short JSON requests within their output token budget.

    DeepSeek may spend the entire budget on thinking before emitting JSON.
    extra_body also works with the pinned Anthropic SDK (0.40.0).
    """
    base_url = str(getattr(client, "base_url", ""))
    if urlparse(base_url).hostname == "api.deepseek.com":
        return {"extra_body": {"thinking": {"type": "disabled"}}}
    return {}
