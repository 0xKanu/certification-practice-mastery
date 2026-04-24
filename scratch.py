import os
import requests
from dotenv import load_dotenv

load_dotenv(override=True)
api_key = os.getenv("OPENROUTER_API_KEY")

try:
    resp = requests.get(
        "https://integrate.api.nvidia.com/v1/models",
        headers={"Authorization": f"Bearer {api_key}"}
    )
    if resp.status_code == 200:
        data = resp.json()
        models = [m["id"] for m in data.get("data", [])]
        for m in sorted(models):
            if "llama" in m.lower() or "nemotron" in m.lower() or "instruct" in m.lower() or "mixtral" in m.lower():
                print(m)
    else:
        print(f"Failed: {resp.status_code} {resp.text}")
except Exception as e:
    print(f"Error: {e}")
