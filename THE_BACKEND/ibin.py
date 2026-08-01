import os
import math
import logging
import random
import numpy as np
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")
from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional, Iterable
from collections import Counter
from sklearn.ensemble import RandomForestRegressor

# --- FastAPI & REST Imports ---
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
import madhev
import scraper
import owner

# --- Supabase Import ---
from supabase import create_client, Client

# Configure production logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("aura_ml_api")


# =====================================================================
# UTILITY FUNCTIONS
# =====================================================================
def calculate_haversine_distance(lat1: Optional[float], lon1: Optional[float], lat2: Optional[float], lon2: Optional[float]) -> float:
    if lat1 is None or lon1 is None or lat2 is None or lon2 is None:
        return 5.0
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return round(R * c, 2)

def parse_screen_format(screen_name: str) -> str:
    name_upper = (screen_name or "").upper().strip()
    if "IMAX LASER" in name_upper or "IMAX 3D" in name_upper: return "IMAX_LASER"
    elif "IMAX" in name_upper: return "IMAX_2D"
    elif "DOLBY" in name_upper or "ATMOS" in name_upper: return "DOLBY_CINEMA"
    elif "4DX" in name_upper or "MX4D" in name_upper: return "4DX"
    elif "PXL" in name_upper or "BIGPIX" in name_upper or "ICE" in name_upper: return "PVR_PXL"
    elif "SCREENX" in name_upper: return "SCREENX"
    return "STANDARD_2D"


# =====================================================================
# DATA PROVIDERS
# =====================================================================
class BaseDataProvider(ABC):
    @abstractmethod
    def get_format_knowledge_base(self) -> Dict[str, Dict[str, Any]]: pass
    @abstractmethod
    def get_available_theaters(self, movie_name: Optional[str] = None, user_lat: Optional[float] = None, user_lon: Optional[float] = None) -> List[Dict[str, Any]]: pass
    @abstractmethod
    def get_booking_history(self) -> List[Dict[str, Any]]: pass
    @abstractmethod
    def get_now_showing_movies(self) -> List[Dict[str, Any]]: pass
    @abstractmethod
    def get_movie_showtimes(self, movie_name: str) -> List[Dict[str, Any]]: pass

class MockDataProvider(BaseDataProvider):
    def get_format_knowledge_base(self):
        return {
            "IMAX_LASER": {"tier": 5, "has_motion": False},
            "IMAX_2D": {"tier": 5, "has_motion": False},
            "DOLBY_CINEMA": {"tier": 5, "has_motion": False},
            "4DX": {"tier": 4, "has_motion": True},
            "PVR_PXL": {"tier": 4, "has_motion": False},
            "SCREENX": {"tier": 3, "has_motion": False},
            "STANDARD_2D": {"tier": 1, "has_motion": False}
        }
    def get_available_theaters(self, movie_name=None, user_lat=None, user_lon=None):
        return [
            {"id": "1", "name": "PVR Lulu Mall", "distance_km": 2.2, "has_step_free_access": True, "screens": ["IMAX_LASER", "4DX", "DOLBY_CINEMA"]},
            {"id": "2", "name": "Shenoys Cinemas", "distance_km": 1.5, "has_step_free_access": False, "screens": ["4DX", "STANDARD_2D"]}
        ]
    def get_booking_history(self):
        return []

    def get_now_showing_movies(self):
        return [
            {"title": "Dune: Part Two", "guessed_format": "IMAX_LASER", "runtime_min": 166},
            {"title": "Inside Out 2", "guessed_format": "DOLBY_CINEMA", "runtime_min": 96},
            {"title": "Kalki 2898 AD", "guessed_format": "IMAX_2D", "runtime_min": 176},
            {"title": "Deadpool & Wolverine", "guessed_format": "4DX", "runtime_min": 127},
            {"title": "Aavesham", "guessed_format": "STANDARD_2D", "runtime_min": 158},
        ]

    def get_movie_showtimes(self, movie_name: str) -> List[Dict[str, Any]]:
        slots = ["4:30 PM", "7:00 PM", "10:15 PM"]
        showtimes = []
        for cinema_id, cinema_name in [("1", "PVR Lulu Mall"), ("2", "Shenoys Cinemas")]:
            for idx, slot in enumerate(slots):
                showtimes.append({
                    "cinema_id": cinema_id,
                    "showtime_id": int(cinema_id) * 100 + idx + 1,
                    "screen_id": int(cinema_id) * 10 + idx + 1,
                    "starts_at": slot,
                    "format_label": "IMAX Laser" if cinema_id == "1" and idx == 0 else "Dolby Cinema" if idx == 1 else "Standard 2D",
                })
        return showtimes

class SupabaseDataProvider(BaseDataProvider):
    def __init__(self, supabase_client: Client):
        self.supabase = supabase_client
        self._mock = MockDataProvider()

    def _fallback_knowledge_base(self):
        return {
            "IMAX_LASER": {"tier": 5, "has_motion": False},
            "IMAX_2D": {"tier": 5, "has_motion": False},
            "DOLBY_CINEMA": {"tier": 5, "has_motion": False},
            "4DX": {"tier": 4, "has_motion": True},
            "PVR_PXL": {"tier": 4, "has_motion": False},
            "SCREENX": {"tier": 3, "has_motion": False},
            "STANDARD_2D": {"tier": 1, "has_motion": False}
        }

    def get_format_knowledge_base(self) -> Dict[str, Dict[str, Any]]:
        try:
            res = self.supabase.table('format_dictionary').select('*').execute()
            if not res or not res.data: return self._fallback_knowledge_base()
            return {row['format_name']: {"tier": row['base_tier'], "has_motion": row['has_motion_seats']} for row in res.data}
        except Exception as e:
            logger.error(f"KB Error, using fallback: {e}")
            return self._fallback_knowledge_base()

    def get_available_theaters(self, movie_name: Optional[str] = None, user_lat: Optional[float] = None, user_lon: Optional[float] = None) -> List[Dict[str, Any]]:
        clean_movie = movie_name.strip() if movie_name else ""
        try:
            if clean_movie:
                res = self.supabase.table('movies').select(
                    'movie_id, title, showtimes(screens(screen_id, name, cinemas(cinema_id, name, latitude, longitude, cinema_features(supports_disabled_hosting))))'
                ).ilike('title', f"%{clean_movie}%").execute()

                if not res or not res.data:
                    logger.warning(f"Movie '{clean_movie}' not found. Falling back to demo cinemas.")
                    return self._mock.get_available_theaters(movie_name, user_lat, user_lon)

                target_movie = next((m for m in res.data if m.get('title', '').strip().lower() == clean_movie.lower()), res.data[0])

                cinemas_map = {}
                for showtime in target_movie.get('showtimes') or []:
                    screen = showtime.get('screens') or {}
                    cinema = screen.get('cinemas') or {}
                    cinema_id = cinema.get('cinema_id')
                    if not cinema_id: continue

                    if cinema_id not in cinemas_map:
                        features = cinema.get('cinema_features') or {}
                        if isinstance(features, list) and len(features) > 0: features = features[0]
                        has_access = features.get('supports_disabled_hosting', False) if isinstance(features, dict) else False
                        
                        dist_km = calculate_haversine_distance(user_lat, user_lon, cinema.get('latitude'), cinema.get('longitude'))
                        cinemas_map[cinema_id] = {"id": str(cinema_id), "name": cinema.get('name', 'Unknown Cinema'), "distance_km": dist_km, "has_step_free_access": has_access, "screens": []}
                    
                    cinemas_map[cinema_id]["screens"].append(parse_screen_format(screen.get('name') or ''))

                if not cinemas_map:
                    return self._mock.get_available_theaters(movie_name, user_lat, user_lon)
                return list(cinemas_map.values())
            else:
                return self._get_all_theaters_fallback(user_lat, user_lon)
        except Exception as e:
            logger.error(f"DB Error: {e}")
            return self._mock.get_available_theaters(movie_name, user_lat, user_lon)

    def _get_all_theaters_fallback(self, user_lat: Optional[float], user_lon: Optional[float]) -> List[Dict[str, Any]]:
        res = self.supabase.table('cinemas').select('cinema_id, name, latitude, longitude, cinema_features(supports_disabled_hosting), screens(name)').execute()
        if not res or not res.data: return []
        
        theaters = []
        for row in res.data:
            features = row.get('cinema_features') or {}
            if isinstance(features, list) and len(features) > 0: features = features[0]
            dist_km = calculate_haversine_distance(user_lat, user_lon, row.get('latitude'), row.get('longitude'))
            formats = [parse_screen_format(s.get('name')) for s in row.get('screens') or []]
            theaters.append({
                "id": str(row['cinema_id']),
                "name": row['name'],
                "distance_km": dist_km,
                "has_step_free_access": features.get('supports_disabled_hosting', False) if isinstance(features, dict) else False,
                "screens": formats
            })
        return theaters

    def get_booking_history(self) -> List[Dict[str, Any]]:
        try:
            res = self.supabase.table('training_feedback').select('selected_theater_id, format_name, genre_bucket, query_id, created_at').execute()
            return res.data if res and res.data else []
        except Exception:
            return []

    def get_now_showing_movies(self) -> List[Dict[str, Any]]:
        try:
            res = self.supabase.table('movies').select('title, runtime_min, runtime_minutes, duration_min, showtimes(screens(name))').limit(24).execute()
            if not res or not res.data:
                return self._mock.get_now_showing_movies()

            movies: List[Dict[str, Any]] = []
            for row in res.data:
                title = (row.get('title') or '').strip()
                if not title:
                    continue

                runtime = row.get('runtime_min') or row.get('runtime_minutes') or row.get('duration_min') or 120
                try:
                    runtime_min = int(runtime)
                except Exception:
                    runtime_min = 120

                formats: List[str] = []
                for showtime in row.get('showtimes') or []:
                    screen = showtime.get('screens') or {}
                    formats.append(parse_screen_format(screen.get('name') or ''))

                guessed_format = Counter(formats).most_common(1)[0][0] if formats else 'STANDARD_2D'
                movies.append({
                    'title': title,
                    'guessed_format': guessed_format,
                    'runtime_min': runtime_min,
                })

            if not movies:
                return self._mock.get_now_showing_movies()
            return movies
        except Exception as e:
            logger.error(f"Now-showing query failed, using fallback: {e}")
            return self._mock.get_now_showing_movies()

    def get_movie_showtimes(self, movie_name: str) -> List[Dict[str, Any]]:
        clean_movie = movie_name.strip() if movie_name else ""
        try:
            if not clean_movie:
                return self._mock.get_movie_showtimes(movie_name)

            res = self.supabase.table('movies').select(
                'movie_id, title, showtimes(showtime_id, start_time, screens(screen_id, name, cinemas(cinema_id, name)))'
            ).ilike('title', f"%{clean_movie}%").execute()

            if not res or not res.data:
                return self._mock.get_movie_showtimes(movie_name)

            target_movie = next(
                (m for m in res.data if m.get('title', '').strip().lower() == clean_movie.lower()),
                res.data[0],
            )

            showtimes = []
            for showtime in target_movie.get('showtimes') or []:
                screen = showtime.get('screens') or {}
                cinema = screen.get('cinemas') or {}
                cinema_id = cinema.get('cinema_id')
                screen_id = screen.get('screen_id')
                showtime_id = showtime.get('showtime_id')
                if not cinema_id or not screen_id or not showtime_id:
                    continue
                fmt = parse_screen_format(screen.get('name') or '')
                showtimes.append({
                    'cinema_id': str(cinema_id),
                    'showtime_id': int(showtime_id),
                    'screen_id': int(screen_id),
                    'starts_at': str(showtime.get('start_time') or 'TBD'),
                    'format_label': fmt.replace('_', ' ').title(),
                })

            if not showtimes:
                return self._mock.get_movie_showtimes(movie_name)
            return showtimes
        except Exception as e:
            logger.error(f"Showtimes query failed, using fallback: {e}")
            return self._mock.get_movie_showtimes(movie_name)


# =====================================================================
# POPULARITY-LIFT CALCULATOR
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
        if total_screens == 0: return {}, 0
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

    def compute_genre_lift(self, active_genres: List[str]) -> Dict[str, float]:
        theaters = self.data_provider.get_available_theaters()
        booking_history = self.data_provider.get_booking_history()
        availability_shares, _ = self._availability_shares(theaters)
        
        overall_lift = self._smoothed_lift(booking_history, availability_shares, prior_means=None)
        if not active_genres: return overall_lift
        
        genre_set = set(active_genres)
        genre_bookings = [b for b in booking_history if b.get("genre_bucket") in genre_set]
        return self._smoothed_lift(genre_bookings, availability_shares, prior_means=overall_lift)


# =====================================================================
# TRUE ML ENGINE (18-FEATURE EXPANDED ARRAY)
# =====================================================================
class AuraMLEngine:
    def __init__(self, data_provider: BaseDataProvider):
        self.data_provider = data_provider
        self.model = RandomForestRegressor(n_estimators=50, max_depth=6, random_state=42)
        self.lift_calculator = PreferenceLiftCalculator(data_provider)
        self._train_synthetic_model()

    def _train_synthetic_model(self):
        logger.info("[ML Pipeline] Training Random Forest model with full 10-genre matrix...")
        X_train, y_train = [], []
        for _ in range(8000): # Increased samples for broader feature set
            is_exact_match, has_motion, needs_access, has_access = [random.choice([1, 0]) for _ in range(4)]
            screen_tier = random.randint(1, 5)
            dist_km = round(random.uniform(0.5, 25.0), 1)
            runtime_min = random.randint(85, 190)
            
            # Genre generation probabilities
            is_action = 1 if random.random() < 0.30 else 0
            is_scifi = 1 if random.random() < 0.20 else 0
            is_comedy = 1 if random.random() < 0.25 else 0
            is_horror = 1 if random.random() < 0.15 else 0
            is_drama = 1 if random.random() < 0.30 else 0
            is_romance = 1 if random.random() < 0.15 else 0
            is_thriller = 1 if random.random() < 0.20 else 0
            is_animation = 1 if random.random() < 0.15 else 0
            is_fantasy = 1 if random.random() < 0.15 else 0
            is_family = 1 if random.random() < 0.20 else 0

            format_lift = max(0.2, min(3.5, float(np.random.lognormal(mean=0.0, sigma=0.4))))

            # Base Scoring
            score = 30.0 + (screen_tier * 4.0) + (40.0 if is_exact_match else 0)
            score += (format_lift - 1.0) * 15.0
            
            # Accessibility Rules
            if needs_access and not has_access: score = 0.0
            elif needs_access and has_access: score += 20.0

            # Distance Penalties based on genre engagement
            casual_movie = is_comedy or is_family or is_romance
            epic_movie = is_action or is_scifi or is_fantasy
            score -= (dist_km * (3.5 if casual_movie and not epic_movie else 1.5))

            # --- SYNTHETIC GENRE RULES ---
            # Motion (4DX) Rules
            if has_motion:
                if is_action or is_horror or is_fantasy: score += 18.0
                if is_drama or is_romance: score -= 25.0 # Motion is terrible for serious dialogue
                if runtime_min > 150: score -= 15.0 # Too long in a moving seat

            # Premium Format (IMAX/Dolby - Tiers 4/5) Rules
            if screen_tier >= 4:
                if epic_movie: score += 20.0
                if is_animation or is_thriller: score += 10.0
                if is_family and not is_animation: score -= 5.0 # Expensive for large groups

            # Standard 2D (Tier 1/2) Rules
            if screen_tier <= 2:
                if is_drama or is_romance or is_comedy: score += 15.0 # Perfectly suited
            
            score = max(0.0, min(100.0, score + random.uniform(-5.0, 5.0)))
            
            # 18 Features Exact Order
            X_train.append([
                is_exact_match, screen_tier, has_motion, dist_km, needs_access, has_access, runtime_min, 
                format_lift, # 8 Core Features
                is_action, is_scifi, is_comedy, is_horror, is_drama, 
                is_romance, is_thriller, is_animation, is_fantasy, is_family # 10 Genre Features
            ])
            y_train.append(score)

        self.model.fit(X_train, y_train)
        logger.info("[ML Pipeline] Model successfully trained on 18-feature array!")

    def rank_theaters_for_user(self, requested_format: str, needs_accessibility: bool, movie_profile: Dict[str, Any], movie_name: Optional[str] = None, user_lat: Optional[float] = None, user_lon: Optional[float] = None) -> List[Dict[str, Any]]:
        
        # Safely extract all 10 genres from payload
        is_action = 1 if movie_profile.get("is_action") else 0
        is_scifi = 1 if movie_profile.get("is_scifi") else 0
        is_comedy = 1 if movie_profile.get("is_comedy") else 0
        is_horror = 1 if movie_profile.get("is_horror") else 0
        is_drama = 1 if movie_profile.get("is_drama") else 0
        is_romance = 1 if movie_profile.get("is_romance") else 0
        is_thriller = 1 if movie_profile.get("is_thriller") else 0
        is_animation = 1 if movie_profile.get("is_animation") else 0
        is_fantasy = 1 if movie_profile.get("is_fantasy") else 0
        is_family = 1 if movie_profile.get("is_family") else 0

        needs_access_flag = 1 if needs_accessibility else 0
        runtime_min = float(movie_profile.get("runtime_min", 120))
        
        # Build Active Genres array for Bayesian Lift
        genre_keys = ["action", "scifi", "comedy", "horror", "drama", "romance", "thriller", "animation", "fantasy", "family"]
        genre_vals = [is_action, is_scifi, is_comedy, is_horror, is_drama, is_romance, is_thriller, is_animation, is_fantasy, is_family]
        active_genres = [g for g, v in zip(genre_keys, genre_vals) if v] or ["general"]

        kb = self.data_provider.get_format_knowledge_base()
        theaters = self.data_provider.get_available_theaters(movie_name=movie_name, user_lat=user_lat, user_lon=user_lon)
        lift_map = self.lift_calculator.compute_genre_lift(active_genres)
        
        ranked_results = []

        for t in theaters:
            screens = [str(s) for s in t.get("screens", [])]
            if not screens: continue

            dist_km = float(t.get("distance_km", 5.0))
            has_access_flag = 1 if t.get("has_step_free_access", False) else 0
            best_screen_score = 0.0
            best_matched_fmt = "NONE"
            best_lift = 1.0

            for screen_format in set(screens):
                screen_meta = kb.get(screen_format, {})
                format_lift = lift_map.get(screen_format, 1.0)
                
                # 18 Features Exact Order Match for Inference
                features = np.array([[
                    1 if screen_format == requested_format else 0,
                    float(screen_meta.get("tier", 1)),
                    1 if screen_meta.get("has_motion") else 0,
                    dist_km, needs_access_flag, has_access_flag, runtime_min, 
                    format_lift,
                    is_action, is_scifi, is_comedy, is_horror, is_drama, 
                    is_romance, is_thriller, is_animation, is_fantasy, is_family
                ]])
                
                ml_predicted_score = float(self.model.predict(features)[0])
                
                if ml_predicted_score > best_screen_score:
                    best_screen_score = ml_predicted_score
                    best_matched_fmt = screen_format
                    best_lift = format_lift

            reason = f"ML Score based on distance ({dist_km}km), format & preference-lift ({best_lift:.2f}x)"
            if needs_accessibility and has_access_flag == 0: reason = "Accessibility dealbreaker"

            ranked_results.append({
                "id": t["id"],
                "name": t["name"],
                "distance_km": dist_km,
                "matched_format": best_matched_fmt,
                "reason": reason,
                "lift": round(best_lift, 2),
                "score": round(best_screen_score, 2)
            })

        return sorted(ranked_results, key=lambda x: x["score"], reverse=True)


# =====================================================================
# REST API CONTROLLERS (FastAPI)
# =====================================================================
app = FastAPI(title="Aura ML Recommendations API", version="1.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- DB INIT ---
USE_SUPABASE = os.environ.get("USE_SUPABASE", "false").lower() == "true"
if USE_SUPABASE:
    provider = SupabaseDataProvider(create_client(os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_KEY")))
else:
    provider = MockDataProvider()
ml_system = AuraMLEngine(data_provider=provider)

# Initialize and mount SeatSelectionRBA router if Supabase is available
try:
    if USE_SUPABASE and isinstance(provider, SupabaseDataProvider):
        madhev.rba_engine = madhev.SeatSelectionRBA(provider.supabase)
    else:
        madhev.rba_engine = madhev.MockSeatSelectionRBA()
    app.include_router(madhev.seat_router, prefix="/rba")
    owner.init_owner_router(provider)
    app.include_router(owner.owner_router, prefix="/owner")
except Exception as _e:
    logger.warning(f"Could not initialize routers: {_e}")

# --- REQUEST / RESPONSE JSON MODELS ---
class MovieProfileModel(BaseModel):
    is_action: bool = False
    is_scifi: bool = False
    is_comedy: bool = False
    is_horror: bool = False
    is_drama: bool = False
    is_romance: bool = False
    is_thriller: bool = False
    is_animation: bool = False
    is_fantasy: bool = False
    is_family: bool = False
    runtime_min: int = 120

class RankingRequestModel(BaseModel):
    movie_name: str
    user_lat: Optional[float] = None
    user_lon: Optional[float] = None
    guessed_format: Optional[str] = "" 
    needs_accessibility: bool = False
    movie_profile: MovieProfileModel

class TheaterRankingResponseModel(BaseModel):
    id: str
    name: str
    distance_km: float
    matched_format: str
    reason: str
    lift: float
    score: float
    showtimes: List[Dict[str, Any]] = []

class MovieAnalyzeRequestModel(BaseModel):
    title: str

class MovieAnalyzeResponseModel(BaseModel):
    status: str
    movie: str
    ratio: str
    recommended_format: str
    snippet_preview: str
    source: str
    movie_profile: MovieProfileModel

class APIResponseModel(BaseModel):
    status: str
    movie: str
    is_cold_start: bool
    optimized_format_target: str
    rankings: List[TheaterRankingResponseModel]

class NowShowingMovieModel(BaseModel):
    title: str
    guessed_format: str
    runtime_min: int

class NowShowingResponseModel(BaseModel):
    status: str
    movies: List[NowShowingMovieModel]

# --- API ROUTES ---
@app.get("/")
def health_check():
    return {"status": "online", "service": "Aura ML API"}

@app.get("/movies/now-showing", response_model=NowShowingResponseModel)
def now_showing_movies():
    return {
        "status": "success",
        "movies": provider.get_now_showing_movies()
    }

@app.post("/movies/analyze", response_model=MovieAnalyzeResponseModel)
def analyze_movie(req: MovieAnalyzeRequestModel):
    if not req.title.strip():
        raise HTTPException(status_code=400, detail="title cannot be empty.")
    scraped = scraper.analyze_format_from_live_data(req.title.strip())
    requested_format, profile = scraper.map_scraper_output_to_ml_inputs(scraped)
    return {
        "status": "success",
        "movie": req.title.strip(),
        "ratio": scraped.get("ratio", ""),
        "recommended_format": requested_format,
        "snippet_preview": scraped.get("snippet_preview", ""),
        "source": scraped.get("source", ""),
        "movie_profile": profile,
    }

@app.post("/recommend", response_model=APIResponseModel)
def get_recommendations(req: RankingRequestModel):
    if not req.movie_name.strip():
        raise HTTPException(status_code=400, detail="movie_name cannot be empty.")

    clean_guess = req.guessed_format.strip().upper() if req.guessed_format else ""
    requested_format = clean_guess if clean_guess else "__COLD_START_UNKNOWN__"

    results = ml_system.rank_theaters_for_user(
        requested_format=requested_format,
        needs_accessibility=req.needs_accessibility,
        movie_profile=req.movie_profile.model_dump(),
        movie_name=req.movie_name,
        user_lat=req.user_lat,
        user_lon=req.user_lon
    )

    all_showtimes = provider.get_movie_showtimes(req.movie_name)
    showtimes_by_cinema: Dict[str, List[Dict[str, Any]]] = {}
    for slot in all_showtimes:
        showtimes_by_cinema.setdefault(slot["cinema_id"], []).append({
            "showtime_id": slot["showtime_id"],
            "screen_id": slot["screen_id"],
            "starts_at": slot["starts_at"],
            "format_label": slot["format_label"],
        })

    enriched = []
    for theater in results:
        enriched.append({**theater, "showtimes": showtimes_by_cinema.get(theater["id"], showtimes_by_cinema.get(str(theater["id"]), []))})

    return {
        "status": "success",
        "movie": req.movie_name,
        "is_cold_start": clean_guess == "",
        "optimized_format_target": requested_format,
        "rankings": enriched
    }

if __name__ == "__main__":
    logger.info("Starting REST API on port 8000...")
    uvicorn.run(app, host="0.0.0.0", port=8000)