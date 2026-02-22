from __future__ import annotations

from app.llm.client import get_client, get_config
from app.llm.prompt import REVIEW_PROMPT_V1

def review_code(code: str) -> str:
    client = get_client()
    cfg = get_config()


    prompt = REVIEW_PROMPT_V1.format(code=code)

    resp = client.messages.create(
        model=cfg.model,
        max_tokens=cfg.max_tokens,
        temperature=0.2,
        messages=[
            {
                "role":"user",
                "content": prompt,

            }
        ],
    )

    return resp.content[0].text



