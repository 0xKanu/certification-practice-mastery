import os
import json
import time
import logging
from typing import TypeVar, Type
from pydantic import BaseModel
from openai import OpenAI, RateLimitError
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

_logger = get_logger("Config")

# ── Provider Routing ─────────────────────────────────────
# Switch between providers by setting PROVIDER in .env
# Supported: "openrouter", "nvidia"
PROVIDER = os.getenv("PROVIDER", "openrouter").lower().strip()

if PROVIDER == "nvidia":
    api_key = os.getenv("NVIDIA_API_KEY")
    base_url = "https://integrate.api.nvidia.com/v1"
    MODEL = os.getenv("NVIDIA_MODEL", "meta/llama-3.3-70b-instruct")
    _logger.info(f"Provider: NVIDIA NIM  |  Model: {MODEL}")
else:
    # Default: OpenRouter (generous free tier, wide model selection)
    api_key = os.getenv("OPENROUTER_API_KEY")
    base_url = "https://openrouter.ai/api/v1"
    MODEL = os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct")
    _logger.info(f"Provider: OpenRouter  |  Model: {MODEL}")

client = OpenAI(
    base_url=base_url,
    api_key=api_key,
)


def call_llm(system_prompt: str, user_message: str, temperature: float = 0) -> str:
    """Single LLM call. Every agent uses this.

    Swap providers/models by changing PROVIDER + keys in .env — no code changes needed.
    Includes exponential backoff for rate-limited free tiers.
    """
    max_retries = 5
    base_wait = 4

    for attempt in range(max_retries):
        try:
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
        except RateLimitError as e:
            wait_time = base_wait * (2 ** attempt)  # 4s, 8s, 16s, 32s, 64s
            if attempt == max_retries - 1:
                _logger.error(f"Rate limit exhausted after {max_retries} attempts. Error: {e.message if hasattr(e, 'message') else str(e)}")
                raise
            _logger.warning(f"Rate limit (429). Waiting {wait_time}s before retry {attempt+1}/{max_retries}...")
            time.sleep(wait_time)


T = TypeVar("T", bound=BaseModel)

def call_llm_json(system_prompt: str, user_message: str, schema: Type[T], temperature: float = 0) -> T:
    """Call LLM and parse the response as JSON into a Pydantic model.
    Handles markdown code block stripping automatically.
    """
    raw = call_llm(system_prompt, user_message, temperature)

    clean = raw.strip()
    
    # Extract JSON between the first '{' and the last '}'
    start_idx = clean.find('{')
    end_idx = clean.rfind('}')
    
    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
        clean = clean[start_idx:end_idx + 1]
    
    try:
        parsed = json.loads(clean)
    except json.JSONDecodeError as e:
        _logger.error(f"JSON Parse Error. Raw LLM response:\n{raw}")
        raise e
        
    return schema(**parsed)