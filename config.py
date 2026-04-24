import os
import json
import logging
from typing import TypeVar, Type
from pydantic import BaseModel
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv(override=True)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S"
)

def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)

api_key = os.getenv("OPENROUTER_API_KEY")
base_url = "https://openrouter.ai/api/v1"
if api_key and api_key.startswith("nvapi-"):
    base_url = "https://integrate.api.nvidia.com/v1/"

# OpenRouter uses the OpenAI SDK — just point base_url at their API
client = OpenAI(
    base_url=base_url,
    api_key=api_key,
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