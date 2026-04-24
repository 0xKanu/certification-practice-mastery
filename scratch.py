import json
from ddgs import DDGS
import requests

def search_cert(cert_name):
    query = f"{cert_name} official exam guide syllabus domains"
    print(f"Searching: {query}")
    
    results = DDGS().text(query, max_results=3)
    
    context = ""
    for r in results:
        context += f"URL: {r['href']}\nTitle: {r['title']}\nSnippet: {r['body']}\n\n"
        
        # Try fetching full text via Jina AI
        print(f"Fetching full text for {r['href']} via Jina...")
        try:
            jina_url = f"https://r.jina.ai/{r['href']}"
            resp = requests.get(jina_url, timeout=10)
            if resp.status_code == 200:
                text = resp.text
                context += f"FULL WEBSITE CONTENT:\n{text[:2500]}\n\n"
            else:
                print(f"Jina failed with {resp.status_code}")
        except Exception as e:
            print(f"Failed to fetch {r['href']}: {e}")
            
    print(context)

search_cert("Google Associate Data Practitioner")
