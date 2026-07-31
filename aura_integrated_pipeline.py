import os
import re
import time
import math
import random
import urllib.parse
import requests
from bs4 import BeautifulSoup
import numpy as np
import pandas as pd
from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional, Iterable
from collections import Counter
from sklearn.ensemble import RandomForestRegressor

from supabase_config import create_supabase_client, get_supabase_credentials

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.progress import Progress, SpinnerColumn, TextColumn

console = Console()

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Accept-Language': 'en-US,en;q=0.9'
}

# =====================================================================
# 🌐 LIVE DUCKDUCKGO WEB SCRAPER
# =====================================================================
def search_duckduckgo_live(movie_title: str):
    """Fetches real-time search snippets from DuckDuckGo HTML."""
    query = f"{movie_title} movie technical specs aspect ratio imax dolby runtime genre"
    try:
        response = requests.post(
            "https://html.duckduckgo.com/html/", 
            data={'q': query}, 
            headers=HEADERS, 
            timeout=8
        )
        if response.status_code != 200:
            return None, "HTTP Request Blocked"

        soup = BeautifulSoup(response.content, 'html.parser')
        results = soup.find_all('a', class_='result__snippet')
        combined_snippets = " ".join([r.get_text() for r in results]).lower()
        
        first_url_tag = soup.find('a', class_='result__url')
        source_url = first_url_tag.get_text().strip() if first_url_tag else "DuckDuckGo Web Search"

        return combined_snippets, source_url
    except Exception as e:
        return None, str(e)


def analyze_format_from_live_data(movie_title: str):
    """Parses live web snippets for aspect ratios, formats, genres, and runtime."""
    live_text, source_url = search_duckduckgo_live(movie_title)

    if not live_text:
        return {
            "movie": movie_title,
            "ratio": "2.39:1 (Standard)",
            "recommended_format": "STANDARD_2D",
            "explanation": f"Failed to reach web index ({source_url}). Defaulting to standard widescreen.",
            "source": "None"
        }

    ratios = re.findall(r'\b1\.\d\d:\d|2\.\d\d:\d\b', live_text)
    detected_ratios = list(set(ratios))

    # --- FORMAT DETECTION MATRIX ---
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
        "snippet_preview": live_text[:200] + "..."
    }


def map_scraper_output_to_ml_inputs(scraper_result: Dict[str, Any]):
    """Translates raw scraped text into the structured movie_profile for AuraMLEngine."""
    requested_format = scraper_result.get("recommended_format", "STANDARD_2D")
    text = str(scraper_result.get("explanation", "")).lower()

    is_action = any(w in text for w in ['action', 'explosion', 'blockbuster', 'thriller', 'spider'])
    is_scifi = any(w in text for w in ['sci-fi', 'scifi', 'science fiction', 'space', 'interstellar'])
    is_comedy = any(w in text for w in ['comedy', 'funny', 'humor', 'sitcom', 'hangover'])

    runtime_min = 120
    minutes_match = re.findall(r'(\d{2,3})\s*(?:min|minutes)', text)
    if minutes_match:
        runtime_min = int(minutes_match[0])
    else:
        hours_match = re.findall(r'(\d)\s*h(?:our)?s?\s*(\d{1,2})?\s*m', text)
        if hours_match:
            hrs, mins = hours_match[0]
            runtime_min = (int(hrs) * 60) + (int(mins) if mins else 0)

    return requested_format, {
        "is_action": is_action,
        "is_scifi": is_scifi,
        "is_comedy": is_comedy,
        "runtime_min": runtime_min
    }


# =====================================================================
# 1. DATA PROVIDER INTERFACE
# =====================================================================
class BaseDataProvider(ABC):
    @abstractmethod
    def get_format_knowledge_base(self) -> Dict[str, Dict[str, Any]]:
        pass

    @abstractmethod
    def get_available_theaters(self) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    def log_user_interaction(self, query_id: str, selected_theater_id: str, reward: float):
        pass

    @abstractmethod
    def get_booking_history(self) -> List[Dict[str, Any]]:
        pass


# =====================================================================
# 2. CURRENT IMPLEMENTATION: MOCK DATA PROVIDER
# =====================================================================
class MockDataProvider(BaseDataProvider):
    def __init__(self):
        self.kb = {
            "IMAX_LASER": {"tier": 5, "has_motion": False, "source": "mock"},
            "IMAX_2D": {"tier": 5, "has_motion": False, "source": "mock"},
            "DOLBY_CINEMA": {"tier": 5, "has_motion": False, "source": "mock"},
            "4DX": {"tier": 4, "has_motion": True, "source": "mock"},
            "PVR_PXL": {"tier": 4, "has_motion": False, "source": "mock"},
            "STANDARD_2D": {"tier": 1, "has_motion": False, "source": "mock"}
        }
        self.theaters = [
            {
                "id": "TH-101",
                "name": "PVR Lulu Mall",
                "distance_km": 2.2,
                "has_step_free_access": True,
                "screens": ["IMAX_LASER", "4DX", "DOLBY_CINEMA"]
            },
            {
                "id": "TH-102",
                "name": "Shenoys Cinemas",
                "distance_km": 1.5,
                "has_step_free_access": False,
                "screens": ["4DX", "STANDARD_2D"]
            },
            {
                "id": "TH-103",
                "name": "Forum Mall Cinepolis",
                "distance_km": 12.8,
                "has_step_free_access": True,
                "screens": ["IMAX_2D", "PVR_PXL", "STANDARD_2D"]
            },
            {
                "id": "TH-104",
                "name": "Navrang Local Talkies",
                "distance_km": 0.8,
                "has_step_free_access": True,
                "screens": ["STANDARD_2D"]
            }
        ]
        self.interaction_logs = []
        self.booking_history = self._generate_mock_booking_history()

    def get_format_knowledge_base(self) -> Dict[str, Dict[str, Any]]:
        return {format_name: metadata.copy() for format_name, metadata in self.kb.items()}

    def get_available_theaters(self) -> List[Dict[str, Any]]:
        return [{**theater, "screens": list(theater.get("screens", []))} for theater in self.theaters]

    def log_user_interaction(self, query_id: str, selected_theater_id: str, reward: float):
        self.interaction_logs.append({
            "query_id": query_id,
            "theater_id": selected_theater_id,
            "reward": reward,
            "source": "mock",
            "logged_at": time.time()
        })
        print(f"  [Mock Storage Logged] User picked '{selected_theater_id}' with score reward {reward}")

    def get_booking_history(self) -> List[Dict[str, Any]]:
        return [dict(record) for record in self.booking_history]

    def _generate_mock_booking_history(self, n: int = 4000) -> List[Dict[str, Any]]:
        rng = random.Random(7)
        genre_format_weights = {
            "scifi":   {"IMAX_LASER": 6, "IMAX_2D": 5, "DOLBY_CINEMA": 4, "4DX": 2, "PVR_PXL": 2, "STANDARD_2D": 1},
            "action":  {"4DX": 6, "IMAX_LASER": 3, "DOLBY_CINEMA": 2, "IMAX_2D": 2, "PVR_PXL": 2, "STANDARD_2D": 1},
            "comedy":  {"STANDARD_2D": 5, "PVR_PXL": 2, "DOLBY_CINEMA": 1, "IMAX_2D": 1, "IMAX_LASER": 1, "4DX": 1},
            "general": {"STANDARD_2D": 3, "IMAX_LASER": 2, "DOLBY_CINEMA": 2, "IMAX_2D": 2, "4DX": 2, "PVR_PXL": 2},
        }
        genre_buckets = list(genre_format_weights.keys())

        history = []
        for _ in range(n):
            genre = rng.choice(genre_buckets)
            weights = genre_format_weights[genre]
            candidate_formats = list(weights.keys())
            w = [weights[f] for f in candidate_formats]
            fmt = rng.choices(candidate_formats, weights=w, k=1)[0]

            eligible_theaters = [t for t in self.theaters if fmt in t["screens"]]
            if not eligible_theaters:
                continue
            theater = rng.choice(eligible_theaters)

            history.append({
                "theater_id": theater["id"],
                "format_name": fmt,
                "genre_bucket": genre,
                "film_id": f"FILM-{rng.randint(1, 250)}",
                "timestamp": time.time() - rng.randint(0, 60 * 60 * 24 * 90),
            })
        return history


# =====================================================================
# 3. FUTURE IMPLEMENTATION: SUPABASE DATA PROVIDER
# =====================================================================
class SupabaseDataProvider(BaseDataProvider):
    def __init__(self, supabase_url: str, supabase_key: str):
        from supabase import create_client
        self.supabase = create_client(supabase_url, supabase_key)

    def get_format_knowledge_base(self) -> Dict[str, Dict[str, Any]]:
        try:
            res = self.supabase.table('format_dictionary').select('format_name, base_tier, has_motion_seats').execute()
            kb = {}
            for row in res.data or []:
                fmt = row.get('format_name')
                if fmt:
                    kb[fmt] = {
                        "tier": int(row.get('base_tier', 1)),
                        "has_motion": bool(row.get('has_motion_seats', False)),
                        "source": "supabase"
                    }
            if kb:
                return kb
            return {
                "IMAX_LASER": {"tier": 5, "has_motion": False, "source": "fallback"},
                "IMAX_2D": {"tier": 5, "has_motion": False, "source": "fallback"},
                "DOLBY_CINEMA": {"tier": 5, "has_motion": False, "source": "fallback"},
                "4DX": {"tier": 4, "has_motion": True, "source": "fallback"},
                "PVR_PXL": {"tier": 4, "has_motion": False, "source": "fallback"},
                "STANDARD_2D": {"tier": 1, "has_motion": False, "source": "fallback"},
            }
        except Exception as e:
            print(f"⚠️ Supabase Error: Could not fetch knowledge base. ({e})")
            return {}

    def get_available_theaters(self) -> List[Dict[str, Any]]:
        try:
            cinemas_res = self.supabase.table('cinemas').select('cinema_id, name, city').execute()
            features_res = self.supabase.table('cinema_features').select('cinema_id, supports_disabled_hosting').execute()
            features_by_cinema = {
                row.get('cinema_id'): row
                for row in features_res.data or []
                if row.get('cinema_id') is not None
            }
            showtimes_res = self.supabase.table('showtimes').select('screen_id').execute()
            active_screen_ids = {row.get('screen_id') for row in showtimes_res.data or [] if row.get('screen_id') is not None}

            screen_formats_res = self.supabase.table('screen_formats').select('screen_id, format_name').execute()
            formats_by_screen = {}
            for row in screen_formats_res.data or []:
                screen_id = row.get('screen_id')
                fmt = row.get('format_name')
                if screen_id is not None and fmt:
                    formats_by_screen.setdefault(screen_id, []).append(fmt)

            theaters = []
            for row in cinemas_res.data or []:
                cinema_id = row.get('cinema_id')
                screens_res = self.supabase.table('screens').select('screen_id, name, aspect_ratio').eq('cinema_id', cinema_id).execute()
                screens = []
                for screen in screens_res.data or []:
                    screen_id = screen.get('screen_id')
                    if screen_id is None or screen_id not in active_screen_ids:
                        continue
                    formats = formats_by_screen.get(screen_id, [])
                    if not formats and screen.get('aspect_ratio'):
                        formats = ['STANDARD_2D']
                    if formats:
                        screens.extend(formats)
                if not screens:
                    continue
                feature_row = features_by_cinema.get(cinema_id, {})
                theaters.append({
                    "id": str(cinema_id),
                    "name": row.get('name', f'Cinema {cinema_id}'),
                    "distance_km": 10.0,
                    "has_step_free_access": bool(feature_row.get('supports_disabled_hosting', False)),
                    "screens": screens
                })
            return theaters
        except Exception as e:
            print(f"⚠️ Supabase Error: Could not fetch theaters. ({e})")
            return []

    def log_user_interaction(self, query_id: str, selected_theater_id: str, reward: float):
        try:
            self.supabase.table('training_feedback').insert({
                "query_id": query_id,
                "selected_theater_id": selected_theater_id,
                "relevance_reward": reward
            }).execute()
            print(f"  [Supabase DB Logged] Training point saved for Query {query_id}")
        except Exception as e:
            print(f"⚠️ Supabase Error: Could not log interaction. ({e})")

    def get_booking_history(self) -> List[Dict[str, Any]]:
        try:
            bookings_res = self.supabase.table('bookings').select('showtime_id, created_at').execute()
            history = []
            for row in bookings_res.data or []:
                showtime_id = row.get('showtime_id')
                if not showtime_id:
                    continue
                showtime_res = self.supabase.table('showtimes').select('movie_id, screen_id').eq('showtime_id', showtime_id).execute()
                if not showtime_res.data:
                    continue
                showtime = showtime_res.data[0]
                screen_id = showtime.get('screen_id')
                screen_res = self.supabase.table('screens').select('cinema_id').eq('screen_id', screen_id).execute()
                if not screen_res.data:
                    continue
                cinema_id = screen_res.data[0].get('cinema_id')
                fmt_name = 'STANDARD_2D'
                formats_res = self.supabase.table('screen_formats').select('format_name').eq('screen_id', screen_id).execute()
                if formats_res.data:
                    fmt_name = formats_res.data[0].get('format_name') or fmt_name
                history.append({
                    "theater_id": str(cinema_id),
                    "format_name": fmt_name,
                    "genre_bucket": 'general',
                    "film_id": str(showtime.get('movie_id', 'unknown')),
                    "timestamp": row.get('created_at', time.time()),
                })
            return history
        except Exception as e:
            print(f"⚠️ Supabase Error: Could not fetch booking history. ({e})")
            return []


# =====================================================================
# 4. POPULARITY-LIFT CALCULATOR
# =====================================================================
class PreferenceLiftCalculator:
    def __init__(self, data_provider: BaseDataProvider, prior_weight: float = 8.0):
        self.data_provider = data_provider
        self.prior_weight = prior_weight

    def _availability_shares(self, theaters: List[Dict[str, Any]]):
        format_screen_counts = Counter()
        total_screens = 0
        for t in theaters:
            for fmt in t.get("screens", []):
                format_screen_counts[fmt] += 1
                total_screens += 1
        if total_screens == 0:
            return {}, 0
        return {fmt: count / total_screens for fmt, count in format_screen_counts.items()}, total_screens

    def _smoothed_lift(self, bookings: Iterable[Dict[str, Any]], availability_shares: Dict[str, float], prior_means: Optional[Dict[str, float]] = None) -> Dict[str, float]:
        bookings = list(bookings)
        total_bookings = len(bookings)
        booking_counts = Counter(b["format_name"] for b in bookings)

        lift = {}
        for fmt, avail_share in availability_shares.items():
            observed = booking_counts.get(fmt, 0)
            expected = avail_share * total_bookings
            prior_mean = 1.0 if prior_means is None else prior_means.get(fmt, 1.0)
            lift[fmt] = (observed + self.prior_weight * prior_mean) / (expected + self.prior_weight)
        return lift

    def compute_overall_lift(self) -> Dict[str, float]:
        theaters = self.data_provider.get_available_theaters()
        booking_history = self.data_provider.get_booking_history()
        availability_shares, _ = self._availability_shares(theaters)
        return self._smoothed_lift(booking_history, availability_shares, prior_means=None)

    def compute_genre_lift(self, active_genres: List[str]) -> Dict[str, float]:
        theaters = self.data_provider.get_available_theaters()
        booking_history = self.data_provider.get_booking_history()
        availability_shares, _ = self._availability_shares(theaters)

        overall_lift = self._smoothed_lift(booking_history, availability_shares, prior_means=None)

        if not active_genres:
            return overall_lift

        genre_set = set(active_genres)
        genre_bookings = [b for b in booking_history if b.get("genre_bucket") in genre_set]
        return self._smoothed_lift(genre_bookings, availability_shares, prior_means=overall_lift)

    def get_lift(self, format_name: str, active_genres: Optional[List[str]] = None) -> float:
        lift_map = self.compute_genre_lift(active_genres or [])
        return lift_map.get(format_name, 1.0)


# =====================================================================
# 5. TRUE ML ENGINE
# =====================================================================
class AuraMLEngine:
    def __init__(self, data_provider: BaseDataProvider):
        self.data_provider = data_provider
        self.model = RandomForestRegressor(n_estimators=50, max_depth=6, random_state=42)
        self.is_trained = False
        self.lift_calculator = PreferenceLiftCalculator(data_provider)
        self._train_synthetic_model()

    def _train_synthetic_model(self):
        print("\n⚙️  [ML Pipeline] Generating 5,000 synthetic training records (Multi-Genre Overlap + Lift)...")
        X_train, y_train = [], []
        for _ in range(5000):
            is_exact_match = random.choice([1, 0])
            screen_tier = random.randint(1, 5)
            has_motion = random.choice([1, 0])
            dist_km = round(random.uniform(0.5, 25.0), 1)
            needs_access = random.choice([1, 0])
            has_access = random.choice([1, 0])
            runtime_min = random.randint(85, 190)

            is_action = 1 if random.random() < 0.40 else 0
            is_scifi = 1 if random.random() < 0.25 else 0
            is_comedy = 1 if random.random() < 0.35 else 0

            format_lift = float(np.random.lognormal(mean=0.0, sigma=0.4))
            format_lift = max(0.2, min(3.5, format_lift))

            score = 30.0
            if is_exact_match: score += 40.0
            score += (screen_tier * 4.0)
            if is_action and has_motion: score += 15.0
            if has_motion and runtime_min > 150: score -= 15.0
            if is_scifi and screen_tier >= 4: score += 18.0

            if is_comedy and not is_action: score -= (dist_km * 3.5)
            else: score -= (dist_km * 1.5)

            score += (format_lift - 1.0) * 15.0
            if needs_access and not has_access: score = 0.0
            elif needs_access and has_access: score += 20.0

            score += random.uniform(-5.0, 5.0)
            score = max(0.0, min(100.0, score))

            X_train.append([
                is_exact_match, screen_tier, has_motion, dist_km,
                needs_access, has_access, runtime_min,
                is_action, is_scifi, is_comedy, format_lift,
            ])
            y_train.append(score)

        print("🧠 [ML Pipeline] Training RandomForestRegressor...")
        self.model.fit(X_train, y_train)
        self.is_trained = True
        print("✅ [ML Pipeline] Model successfully trained!")

    def rank_theaters_for_user(
        self, requested_format: str, needs_accessibility: bool, movie_profile: Dict[str, Any]
    ) -> List[Dict[str, Any]]:

        is_action = 1 if movie_profile.get("is_action") else 0
        is_scifi = 1 if movie_profile.get("is_scifi") else 0
        is_comedy = 1 if movie_profile.get("is_comedy") else 0
        needs_access_flag = 1 if needs_accessibility else 0
        runtime_min = float(movie_profile.get("runtime_min", 120))

        active_genres = []
        if is_scifi: active_genres.append("scifi")
        if is_action: active_genres.append("action")
        if is_comedy: active_genres.append("comedy")
        if not active_genres: active_genres = ["general"]

        kb = self.data_provider.get_format_knowledge_base()
        theaters = self.data_provider.get_available_theaters()
        lift_map = self.lift_calculator.compute_genre_lift(active_genres)
        ranked_results = []

        for t in theaters:
            screens = [str(s) for s in t.get("screens", [])]
            if not screens: continue

            dist_km = float(t.get("distance_km", 10.0))
            has_access_flag = 1 if t.get("has_step_free_access", False) else 0

            best_screen_score = 0.0
            best_matched_fmt = "NONE"
            best_lift = 1.0

            for screen_format in screens:
                screen_meta = kb.get(screen_format, {})
                format_lift = lift_map.get(screen_format, 1.0)
                features = np.array([[
                    1 if screen_format == requested_format else 0,
                    float(screen_meta.get("tier", 1)),
                    1 if screen_meta.get("has_motion") else 0,
                    dist_km, needs_access_flag, has_access_flag,
                    runtime_min, is_action, is_scifi, is_comedy, format_lift,
                ]])
                
                ml_predicted_score = self.model.predict(features)[0]

                if ml_predicted_score > best_screen_score:
                    best_screen_score = ml_predicted_score
                    best_matched_fmt = screen_format
                    best_lift = format_lift

            reason = f"ML Score based on distance ({dist_km}km), format & preference-lift ({best_lift:.2f}x)"
            if needs_accessibility and has_access_flag == 0:
                reason = "Accessibility dealbreaker"

            ranked_results.append({
                "id": t["id"],
                "name": t["name"],
                "matched_format": best_matched_fmt,
                "reason": reason,
                "lift": round(best_lift, 2),
                "score": round(best_screen_score, 2)
            })

        return sorted(ranked_results, key=lambda x: x["score"], reverse=True)


# =====================================================================
# 6. REST-STYLE ENTRYPOINT
# =====================================================================
url, key = get_supabase_credentials()
USE_SUPABASE = bool(url and key)
if USE_SUPABASE:
    provider = SupabaseDataProvider(url, key)
else:
    provider = MockDataProvider()
ml_system = AuraMLEngine(data_provider=provider)


def get_recommendations(req: Dict[str, Any]) -> Dict[str, Any]:
    format_map = {
        "IMAX_LASER": "IMAX_LASER",
        "IMAX_2D": "IMAX_2D",
        "DOLBY_CINEMA": "DOLBY_CINEMA",
        "4DX": "4DX",
        "PVR_PXL": "PVR_PXL",
        "STANDARD_2D": "STANDARD_2D",
    }

    payload = dict(req or {})
    guessed_format = str(payload.get("guessed_format", "") or "").strip().upper()
    requested_format = format_map.get(guessed_format, "STANDARD_2D")

    movie_profile = payload.get("movie_profile", {}) or {}
    if not isinstance(movie_profile, dict):
        movie_profile = {}

    results = ml_system.rank_theaters_for_user(
        requested_format=requested_format,
        needs_accessibility=bool(payload.get("needs_accessibility", False)),
        movie_profile=movie_profile,
    )

    top_recommendation = results[0] if results else None

    return {
        "status": "success",
        "movie": payload.get("movie_name", "unknown"),
        "top_recommendation": top_recommendation,
    }


# =====================================================================
# 7. CLI EXECUTION PIPELINE (SINGLE BEST SUGGESTION OUTPUT)
# =====================================================================
def main_cli():
    console.print("\n[bold red]🌐 CineBook: Real-Time Web Scraper -> Aura ML Model[/bold red]\n")

    while True:
        movie = Prompt.ask("[bold yellow]Enter Movie Title[/bold yellow] (or type 'exit' to quit)")
        if movie.lower() == 'exit':
            break

        # 1. Run Scraper
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            transient=True,
        ) as progress:
            progress.add_task(description=f"Scraping web specs for '{movie}'...", total=None)
            scraper_result = analyze_format_from_live_data(movie)

        # 2. Map Scraper Output -> ML Inputs
        requested_format, movie_profile = map_scraper_output_to_ml_inputs(scraper_result)

        # 3. Run ML Engine Inference
        rankings = ml_system.rank_theaters_for_user(
            requested_format=requested_format,
            needs_accessibility=False,
            movie_profile=movie_profile
        )

        # Extract ONLY the #1 best recommendation
        best = rankings[0] if rankings else None

        # 4. Render Single Suggestion Card
        if best:
            output_card = f"""
[bold white]Movie Searched:[/bold white] {movie.title()}
[bold white]Scraped Aspect Ratio:[/bold white] [bold cyan]{scraper_result['ratio']}[/bold cyan]
[bold white]Target Viewing Format:[/bold white] [bold gold1]{requested_format}[/bold gold1]

--------------------------------------------------
[bold green]🏆 BEST RECOMMENDED THEATRE[/bold green]
[bold white]Theatre Name:[/bold white] [bold yellow]{best['name']}[/bold yellow]
[bold white]Best Screen Format:[/bold white] [bold cyan]{best['matched_format']}[/bold cyan]
[bold white]Match Score:[/bold white] [bold green]{best['score']}/100[/bold green]
[bold white]Reason:[/bold white] {best['reason']}
"""
        else:
            output_card = "No suitable theater match found."

        console.print(Panel(output_card, title="[bold cyan]AI THEATRE SUGGESTION[/bold cyan]", expand=False))
        console.print("\n" + "="*50 + "\n")


if __name__ == "__main__":
    main_cli()