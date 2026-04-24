import json
import requests
from pathlib import Path
from ddgs import DDGS
from config import call_llm_json, get_logger
from schemas import SyllabusOutput

logger = get_logger("Agent.SyllabusMapper")

PROMPT = (Path(__file__).parent.parent / "prompts" / "syllabus_mapper.md").read_text()

def _fetch_web_context(certification_name: str) -> str:
    """Uses DuckDuckGo and Jina AI to fetch live syllabus context."""
    query = f"{certification_name} official exam guide syllabus domains"
    logger.info(f"Searching web for: '{query}'")
    
    try:
        results = DDGS().text(query, max_results=3)
        if not results:
            return "No web search results found."
            
        context = "WEB SEARCH SNIPPETS:\n"
        first_url = None
        for r in results:
            context += f"URL: {r['href']}\nTitle: {r['title']}\nSnippet: {r['body']}\n\n"
            if not first_url:
                first_url = r['href']
                
        if first_url:
            logger.info(f"Fetching full text via Jina AI for: {first_url}")
            jina_url = f"https://r.jina.ai/{first_url}"
            resp = requests.get(jina_url, timeout=15)
            if resp.status_code == 200:
                # Limit to 5k chars to save context window and drastically reduce latency
                context += f"\nFULL WEBSITE CONTENT (from {first_url}):\n{resp.text[:5000]}"
            else:
                logger.warning(f"Jina AI fetch failed with status {resp.status_code}")
                
        return context
    except Exception as e:
        logger.warning(f"Web search failed: {e}")
        return f"Web search failed: {e}"


def run_syllabus_mapper(certification_name: str) -> SyllabusOutput:
    """Agent 1: certification name → structured syllabus."""
    logger.info(f"Starting syllabus mapping for: '{certification_name}'")
    
    web_context = _fetch_web_context(certification_name)
    
    user_msg = (
        f"Map the syllabus for: {certification_name}\n\n"
        f"=== LIVE WEB SEARCH CONTEXT ===\n{web_context}\n============================="
    )
    
    result = call_llm_json(
        system_prompt=PROMPT,
        user_message=user_msg,
        schema=SyllabusOutput,
        temperature=0,
    )
    
    if result.is_valid and result.domains:
        logger.info(f"Successfully mapped syllabus with {len(result.domains)} domains.")
    else:
        logger.warning(f"Syllabus mapping rejected input: {result.error_message}")
        
    return result