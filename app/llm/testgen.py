from __future__ import annotations

from app.llm.client import get_client, get_config
from app.llm.prompt import TESTGEN_PROMPT_V1


def generate_tests(code: str) -> str:
    client = get_client()
    cfg = get_config()

    prompt = TESTGEN_PROMPT_V1.fromat(code=code)

    resp = client.messages.create(
        model=cfg.model,
        max_tokens=cfg.max_tokens,
        temperature=0.2,
        messages=[
           {
               "role": "user",
               "content": prompt
           }
        ],
    )
    return resp.content[0].text
