import time
import math
import random
import numpy as np
import pandas as pd
from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional, Iterable
from collections import Counter
from sklearn.ensemble import RandomForestRegressor

# --- NEW: FastAPI Imports ---
from fastapi import FastAPI
from pydantic import BaseModel
import uvicorn

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
                "distance_km": 12.8,  # Far away, but has premium screens
                "has_step_free_access": True,
                "screens": ["IMAX_2D", "PVR_PXL", "STANDARD_2D"]
            },
            {
                "id": "TH-104",
                "name": "Navrang Local Talkies",
                "distance_km": 0.8,  # Very close, standard only
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
            res = self.supabase.table('format_dictionary').select('*').execute()
            kb = {}
            for row in res.data:
                kb[row['format_name']] = {
                    "tier": row['base_tier'],
                    "has_motion": row['has_motion_seats']
                }
            return kb
        except Exception as e:
            print(f"⚠️ Supabase Error: Could not fetch knowledge base. ({e})")
            return {}

    def get_available_theaters(self) -> List[Dict[str, Any]]:
        try:
            res = self.supabase.table('theaters').select('*, theater_screens(format_name)').execute()
            theaters = []
            for row in res.data:
                screens = [s['format_name'] for s in row.get('theater_screens', [])]
                theaters.append({
                    "id": row['id'],
                    "name": row['name'],
                    "distance_km": row['distance_km'],
                    "has_step_free_access": row['has_step_free_access'],
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
            res = (
                self.supabase.table('training_feedback')
                .select('selected_theater_id, format_name, genre_bucket, query_id, created_at')
                .execute()
            )
            history = []
            for row in res.data:
                history.append({
                    "theater_id": row.get('selected_theater_id'),
                    "format_name": row.get('format_name'),
                    "genre_bucket": row.get('genre_bucket', 'general'),
                    "film_id": row.get('query_id'),
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
# 6. FASTAPI APPLICATION SETUP
# =====================================================================

app = FastAPI(title="Aura ML API Engine", description="Recommends the best theaters using ML.")

# Initialize Provider & Engine ONE time when server starts (prevents re-training on every API hit)
USE_SUPABASE = False 
provider = SupabaseDataProvider("", "") if USE_SUPABASE else MockDataProvider()
ml_system = AuraMLEngine(data_provider=provider)

# --- Pydantic Data Models (Defines the exact JSON structure the scraper sends) ---
class MovieProfileModel(BaseModel):
    is_action: bool = False
    is_scifi: bool = False
    is_comedy: bool = False
    runtime_min: int = 120

class RankingRequestModel(BaseModel):
    movie_name: str
    guessed_format: Optional[str] = "" 
    needs_accessibility: bool = False
    movie_profile: MovieProfileModel


@app.post("/recommend")
def get_recommendations(req: RankingRequestModel):
    """
    Endpoint for the Scraper/Frontend to get theater rankings.
    """
    # Safety map to prevent scraper from sending junk format names
    format_map = {
        "IMAX_LASER": "IMAX_LASER",
        "IMAX_2D": "IMAX_2D",
        "DOLBY_CINEMA": "DOLBY_CINEMA",
        "4DX": "4DX",
        "PVR_PXL": "PVR_PXL",
        "STANDARD_2D": "STANDARD_2D",
    }
    
    clean_guess = req.guessed_format.strip().upper() if req.guessed_format else ""
    is_cold_start = clean_guess == ""
    
    # If the scraper didn't give a format, default to the safe cold-start fallback
    requested_format = format_map.get(clean_guess, "__COLD_START_UNKNOWN__")

    # Run Inference
    results = ml_system.rank_theaters_for_user(
        requested_format=requested_format,
        needs_accessibility=req.needs_accessibility,
        movie_profile=req.movie_profile.dict()
    )

    return {
        "status": "success",
        "movie": req.movie_name,
        "is_cold_start": is_cold_start,
        "optimized_format_target": requested_format,
        "rankings": results
    }

# =====================================================================
# 7. SERVER RUNNER
# =====================================================================
if __name__ == "__main__":
    # DO NOT paste this file using terminal `<<EOF`! Save it in your text editor.
    # To run the API server, run this in your terminal:
    # python THE_BACKEND/ibin.py
    print("\n🚀 Starting FastAPI Server on port 8000...")
    uvicorn.run(app, host="0.0.0.0", port=8000)
