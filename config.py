import os
import json
from typing import TypeVar, Type
from pydantic import BaseModel
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# OpenRouter uses the OpenAI SDK — just point base_url at their API
client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY"),
)

# Default model — override in .env to experiment
MODEL = os.getenv("MODEL", "meta-llama/llama-3.3-70b-instruct")


def call_llm(system_prompt: str, user_message: str, temperature: float = 0) -> str:
    """Single LLM call. Every agent uses this.

    Swap models by changing MODEL in .env — no code changes needed.
    """
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        temperature=temperature,
        max_tokens=3000,
        extra_headers={
            "HTTP-Referer": "https://github.com/0xKanu/certification-practice-mastery",
            "X-Title": "Certification Practice Mastery",
        },
    )
    return response.choices[0].message.content


T = TypeVar("T", bound=BaseModel)

def call_llm_json(system_prompt: str, user_message: str, schema: Type[T], temperature: float = 0) -> T:
    """Call LLM and parse the response as JSON into a Pydantic model.
    Handles markdown code block stripping automatically.
    """
    raw = call_llm(system_prompt, user_message, temperature)
    
    clean = raw.strip()
    if clean.startswith("```"):
        # Split by first newline to remove the ```json part
        parts = clean.split("\n", 1)
        if len(parts) > 1:
            clean = parts[1]
    if clean.endswith("```"):
        clean = clean.rsplit("```", 1)[0]
    clean = clean.strip()
    
    parsed = json.loads(clean)
    return schema(**parsed)