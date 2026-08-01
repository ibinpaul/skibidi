"""Live web scraper → structured movie profile for ML."""
import re
import requests
from bs4 import BeautifulSoup
from typing import Any, Dict, Tuple

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}


def search_duckduckgo_live(movie_title: str):
    query = f"{movie_title} movie technical specs aspect ratio imax dolby runtime genre"
    try:
        response = requests.post(
            "https://html.duckduckgo.com/html/",
            data={"q": query},
            headers=HEADERS,
            timeout=8,
        )
        if response.status_code != 200:
            return None, "HTTP Request Blocked"

        soup = BeautifulSoup(response.content, "html.parser")
        results = soup.find_all("a", class_="result__snippet")
        combined_snippets = " ".join([r.get_text() for r in results]).lower()

        first_url_tag = soup.find("a", class_="result__url")
        source_url = first_url_tag.get_text().strip() if first_url_tag else "DuckDuckGo Web Search"
        return combined_snippets, source_url
    except Exception as e:
        return None, str(e)


def analyze_format_from_live_data(movie_title: str) -> Dict[str, Any]:
    live_text, source_url = search_duckduckgo_live(movie_title)

    if not live_text:
        return {
            "movie": movie_title,
            "ratio": "2.39:1 (Standard)",
            "recommended_format": "STANDARD_2D",
            "explanation": f"Failed to reach web index ({source_url}). Defaulting to standard widescreen.",
            "source": "None",
            "snippet_preview": "",
        }

    ratios = re.findall(r"\b1\.\d\d:\d|2\.\d\d:\d\b", live_text)
    detected_ratios = list(set(ratios))

    if "1.43:1" in live_text or "imax 70mm" in live_text or "15/70" in live_text or "1.90:1" in live_text or "imax" in live_text:
        rec_fmt = "IMAX_LASER"
        aspect = "1.90:1 / 1.43:1 (IMAX)"
    elif "4dx" in live_text or "motion seat" in live_text:
        rec_fmt = "4DX"
        aspect = "2.39:1 (4DX Motion)"
    elif "dolby" in live_text or "atmos" in live_text:
        rec_fmt = "DOLBY_CINEMA"
        aspect = detected_ratios[0] if detected_ratios else "2.39:1 (Cinemascope)"
    else:
        rec_fmt = "STANDARD_2D"
        aspect = "2.39:1 (Standard)"

    return {
        "movie": movie_title,
        "ratio": aspect,
        "recommended_format": rec_fmt,
        "explanation": live_text,
        "source": source_url,
        "snippet_preview": live_text[:220] + "...",
    }


def map_scraper_output_to_ml_inputs(scraper_result: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    requested_format = scraper_result.get("recommended_format", "STANDARD_2D")
    text = str(scraper_result.get("explanation", "")).lower()

    profile = {
        "is_action": any(w in text for w in ["action", "explosion", "blockbuster", "fight", "marvel"]),
        "is_scifi": any(w in text for w in ["sci-fi", "scifi", "science fiction", "space", "interstellar", "dune"]),
        "is_comedy": any(w in text for w in ["comedy", "funny", "humor", "sitcom", "hangover"]),
        "is_horror": any(w in text for w in ["horror", "scary", "ghost", " possessed"]),
        "is_drama": any(w in text for w in ["drama", "emotional", "biopic", "oscar"]),
        "is_romance": any(w in text for w in ["romance", "romantic", "love story"]),
        "is_thriller": any(w in text for w in ["thriller", "suspense", "mystery", "crime"]),
        "is_animation": any(w in text for w in ["animation", "animated", "pixar", "disney"]),
        "is_fantasy": any(w in text for w in ["fantasy", "wizard", "magic", "dragon"]),
        "is_family": any(w in text for w in ["family", "kids", "children", "pg"]),
        "runtime_min": 120,
    }

    minutes_match = re.findall(r"(\d{2,3})\s*(?:min|minutes)", text)
    if minutes_match:
        profile["runtime_min"] = int(minutes_match[0])
    else:
        hours_match = re.findall(r"(\d)\s*h(?:our)?s?\s*(\d{1,2})?\s*m", text)
        if hours_match:
            hrs, mins = hours_match[0]
            profile["runtime_min"] = (int(hrs) * 60) + (int(mins) if mins else 0)

    return requested_format, profile
