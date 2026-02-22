from __future__ import annotations

import os 
from dataclasses import dataclass

from dotenv import load_dotenv
from anthropic import Anthropic


load_dotenv()


@dataclass(frozen=True)
class LLMConfig:
    model: str
    max_tokens: int


def get_client() -> Anthropic:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set.  Put it in .env or export it in your shell.")
    return Anthropic(api_key=api_key)


def get_config() ->  LLMConfig:
    model = os.getenv("ANTHROPIC_MODEL", "claude-3-haiku-20240307")
    max_tokens = int(os.getenv("ANTHROPIC_MAX_TOKENS", "2000"))
    return LLMConfig(
        model=model,
        max_tokens=max_tokens,
        )