import re
import requests
from bs4 import BeautifulSoup
from typing import Dict, Any
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("aura_scraper")

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Accept-Language': 'en-US,en;q=0.9'
}

# =====================================================================
# LIVE DUCKDUCKGO WEB SCRAPER
# =====================================================================
def search_duckduckgo_live(movie_title: str):
    query = f"{movie_title} movie technical specs aspect ratio imax dolby runtime genre"
    try:
        response = requests.post(
            "https://html.duckduckgo.com/html/", 
            data={'q': query}, headers=HEADERS, timeout=5
        )
        if response.status_code != 200:
            return None, "HTTP Request Blocked"

        soup = BeautifulSoup(response.content, 'html.parser')
        results = soup.find_all('a', class_='result__snippet')
        combined_snippets = " ".join([r.get_text() for r in results]).lower()
        return combined_snippets, "DuckDuckGo Web Search"
    except Exception as e:
        logger.error(f"Scraper error: {e}")
        return None, str(e)


def analyze_format_from_live_data(movie_title: str) -> Dict[str, Any]:
    live_text, source_url = search_duckduckgo_live(movie_title)

    if not live_text:
        return {"movie": movie_title, "recommended_format": "__COLD_START_UNKNOWN__", "explanation": ""}

    ratios = re.findall(r'\b(?:1\.[3489]3|2\.[34]9|1\.\d\d):1\b', live_text)
    detected_ratios = list(set(ratios))

    if "1.43:1" in live_text or "imax 70mm" in live_text or "15/70" in live_text or "1.90:1" in live_text or "imax" in live_text:
        rec_fmt = "IMAX_LASER"
    elif "4dx" in live_text or "motion seat" in live_text:
        rec_fmt = "4DX"
    elif "dolby" in live_text or "atmos" in live_text:
        rec_fmt = "DOLBY_CINEMA"
    else:
        rec_fmt = "STANDARD_2D"

    return {"movie": movie_title, "recommended_format": rec_fmt, "explanation": live_text}


def extract_10_genre_profile(text: str) -> Dict[str, Any]:
    """Scans the text for all 10 genres supported by the Main ML Engine."""
    runtime_min = 120
    minutes_match = re.findall(r'(\d{2,3})\s*(?:min|minutes)', text)
    if minutes_match: runtime_min = int(minutes_match[0])
    
    return {
        "is_action": any(w in text for w in ['action', 'explosion', 'blockbuster']),
        "is_scifi": any(w in text for w in ['sci-fi', 'scifi', 'science fiction', 'space', 'alien']),
        "is_comedy": any(w in text for w in ['comedy', 'funny', 'humor', 'laugh']),
        "is_horror": any(w in text for w in ['horror', 'scary', 'terrifying', 'gore']),
        "is_drama": any(w in text for w in ['drama', 'emotional', 'tragedy']),
        "is_romance": any(w in text for w in ['romance', 'love', 'romantic']),
        "is_thriller": any(w in text for w in ['thriller', 'suspense', 'tense']),
        "is_animation": any(w in text for w in ['animation', 'animated', 'pixar', 'anime']),
        "is_fantasy": any(w in text for w in ['fantasy', 'magic', 'mythical']),
        "is_family": any(w in text for w in ['family', 'kids', 'children']),
        "runtime_min": runtime_min
    }

# =====================================================================
# FASTAPI REST API
# =====================================================================
app = FastAPI(title="Aura Movie Scraper API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

class ScrapeRequest(BaseModel):
    movie_name: str

@app.post("/scrape")
def scrape_movie_data(req: ScrapeRequest):
    if not req.movie_name.strip():
        raise HTTPException(status_code=400, detail="Movie name cannot be empty.")
    
    logger.info(f"Scraping web data for: {req.movie_name}")
    raw_data = analyze_format_from_live_data(req.movie_name)
    movie_profile = extract_10_genre_profile(raw_data["explanation"])

    return {
        "movie_name": req.movie_name,
        "guessed_format": raw_data["recommended_format"],
        "movie_profile": movie_profile
    }

if __name__ == "__main__":
    logger.info("🚀 Starting Scraper API on port 8001...")
    uvicorn.run(app, host="0.0.0.0", port=8001) # Note: Port 8001 so it doesn't conflict with the ML Engine on 8000