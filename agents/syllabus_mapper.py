import json
import requests
from pathlib import Path
from ddgs import DDGS
from config import call_llm_json, get_logger
from schemas import SyllabusOutput

logger = get_logger("Agent.SyllabusMapper")

PROMPT = (Path(__file__).parent.parent / "prompts" / "syllabus_mapper.md").read_text()


def _fetch_web_context(certification_name: str) -> str:
    """Uses DuckDuckGo and Jina AI to fetch live syllabus context.
    
    Strategy:
    1. Search with multiple queries to maximise chance of hitting official sources
    2. Prefer official vendor URLs (cloud.google.com, aws.amazon.com, etc.)
    3. Fetch full page text via Jina AI Reader API
    4. Strip boilerplate from scraped content before truncating
    """
    queries = [
        f"{certification_name} official exam guide syllabus domains",
        f"{certification_name} certification exam guide sections weightings site:cloud.google.com OR site:aws.amazon.com OR site:learn.microsoft.com",
    ]
    
    all_results = []
    for query in queries:
        logger.info(f"Searching web for: '{query}'")
        try:
            results = DDGS().text(query, max_results=5)
            if results:
                all_results.extend(results)
        except Exception as e:
            logger.warning(f"Search failed for query '{query}': {e}")
    
    if not all_results:
        return "No web search results found."
    
    # De-duplicate by URL
    seen_urls = set()
    unique_results = []
    for r in all_results:
        if r['href'] not in seen_urls:
            seen_urls.add(r['href'])
            unique_results.append(r)
    
    # Build snippet context
    context = "WEB SEARCH SNIPPETS:\n"
    for r in unique_results:
        context += f"URL: {r['href']}\nTitle: {r['title']}\nSnippet: {r['body']}\n\n"
    
    # Prioritise official vendor URLs and known-good syllabus sites over blogs/spam
    OFFICIAL_DOMAINS = [
        "cloud.google.com", "aws.amazon.com", "learn.microsoft.com",
        "training.linuxfoundation.org", "cisco.com", "comptia.org",
    ]
    GOOD_SYLLABUS_SITES = [
        "study4exam.com", "examtopics.com", "vmexam.com",
    ]
    # Blacklist spam/dumps sites that waste our character budget
    BLACKLISTED_DOMAINS = [
        "dumpsmaterials", "pass4leader", "braindump", "actualtests",
        "testking", "certificationst", "dumpsbase", "pass4sure",
    ]
    
    # Filter out blacklisted URLs entirely
    filtered_results = [
        r for r in unique_results
        if not any(bl in r['href'].lower() for bl in BLACKLISTED_DOMAINS)
    ]
    if not filtered_results:
        filtered_results = unique_results  # fallback if everything was blacklisted
    
    # Sort: official domains first, then syllabus sites, then others
    def _url_priority(r):
        url = r['href'].lower()
        for i, domain in enumerate(OFFICIAL_DOMAINS):
            if domain in url:
                return i
        for i, domain in enumerate(GOOD_SYLLABUS_SITES):
            if domain in url:
                return 10 + i
        return 100  # blogs, medium, linkedin etc. are last
    
    sorted_results = sorted(filtered_results, key=_url_priority)
    
    # Try to fetch full text from the best URL (up to 2 attempts)
    for r in sorted_results[:2]:
        target_url = r['href']
        logger.info(f"Fetching full text via Jina AI for: {target_url}")
        try:
            jina_url = f"https://r.jina.ai/{target_url}"
            resp = requests.get(jina_url, timeout=20)
            if resp.status_code == 200:
                page_text = _clean_page_text(resp.text)
                # Use 8K chars — enough for full exam guides but not wasteful
                context += f"\nFULL WEBSITE CONTENT (from {target_url}):\n{page_text[:8000]}"
                break
            else:
                logger.warning(f"Jina AI fetch failed ({resp.status_code}) for {target_url}")
        except Exception as e:
            logger.warning(f"Jina AI fetch error for {target_url}: {e}")
    
    return context


def _clean_page_text(raw_text: str) -> str:
    """Strip common web boilerplate from scraped Markdown content.
    
    Removes navigation links, sign-in prompts, cookie banners, etc.
    to maximise the useful content within our character budget.
    """
    lines = raw_text.split("\n")
    cleaned = []
    skip_patterns = [
        "sign in", "sign up", "cookie", "subscribe", "newsletter",
        "open in app", "get app", "write", "search", "sitemap",
        "follow", "read more", "clap", "share", "comment",
        "img src", "image:", "![", "miro.medium.com",
    ]
    
    for line in lines:
        line_lower = line.strip().lower()
        # Skip very short lines (likely navigation)
        if len(line.strip()) < 5:
            continue
        # Skip boilerplate patterns
        if any(pattern in line_lower for pattern in skip_patterns):
            continue
        cleaned.append(line)
    
    return "\n".join(cleaned)


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