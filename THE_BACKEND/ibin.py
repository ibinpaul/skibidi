import time
import math
import random
import numpy as np
import pandas as pd
from abc import ABC, abstractmethod
from typing import Dict, List, Any
from sklearn.ensemble import RandomForestRegressor

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
                "distance_km": 12.8, # Far away, but has premium screens
                "has_step_free_access": True,
                "screens": ["IMAX_2D", "PVR_PXL", "STANDARD_2D"]
            },
            {
                "id": "TH-104",
                "name": "Navrang Local Talkies",
                "distance_km": 0.8, # Very close, standard only
                "has_step_free_access": True,
                "screens": ["STANDARD_2D"]
            }
        ]
        self.interaction_logs = []

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


# =====================================================================
# 4. TRUE ML ENGINE (Trained on Synthetic Data with Multi-Genre Overlap)
# =====================================================================
class AuraMLEngine:
    def __init__(self, data_provider: BaseDataProvider):
        self.data_provider = data_provider
        self.model = RandomForestRegressor(n_estimators=50, max_depth=6, random_state=42)
        self.is_trained = False
        
        self._train_synthetic_model()

    def _train_synthetic_model(self):
        print("\n⚙️  [ML Pipeline] Generating 5,000 synthetic training records (Multi-Genre Overlap)...")
        
        X_train = []
        y_train = []
        
        for _ in range(5000):
            # 1. Randomize Features
            is_exact_match = random.choice([1, 0])
            screen_tier = random.randint(1, 5)
            has_motion = random.choice([1, 0])
            dist_km = round(random.uniform(0.5, 25.0), 1)
            needs_access = random.choice([1, 0])
            has_access = random.choice([1, 0])
            runtime_min = random.randint(85, 190)
            
            # --- FIX: Independent Probabilities for Genre Overlap ---
            is_action = 1 if random.random() < 0.40 else 0
            is_scifi = 1 if random.random() < 0.25 else 0
            is_comedy = 1 if random.random() < 0.35 else 0
            
            # 2. Simulate User Booking Behavior (Ground Truth)
            score = 30.0 
            
            if is_exact_match: score += 40.0
            score += (screen_tier * 4.0)
            
            # --- GENRE SPECIFIC BEHAVIORS ---
            # Action: Loves motion seats, unless it's too long
            if is_action and has_motion: 
                score += 15.0
            if has_motion and runtime_min > 150: 
                score -= 15.0 
                
            # Sci-Fi: Massive boost for premium large formats (Tier 4 & 5)
            if is_scifi and screen_tier >= 4:
                score += 18.0
                
            # Comedy: Doesn't care about premium screens, but HATES driving far
            # (If it's an Action-Comedy, the action boosts mitigate some distance penalty)
            if is_comedy and not is_action:
                score -= (dist_km * 3.5) # Heavy distance penalty for pure comedy
            else:
                score -= (dist_km * 1.5) # Normal distance penalty
            # --------------------------------
            
            if needs_access and not has_access:
                score = 0.0 # Dealbreaker
            elif needs_access and has_access:
                score += 20.0
                
            score += random.uniform(-5.0, 5.0) # Add noise
            score = max(0.0, min(100.0, score)) # Ensure bounds
            
            # 10-Feature Array
            X_train.append([
                is_exact_match, screen_tier, has_motion, dist_km, 
                needs_access, has_access, runtime_min, 
                is_action, is_scifi, is_comedy
            ])
            y_train.append(score)

        print("🧠 [ML Pipeline] Training RandomForestRegressor...")
        self.model.fit(X_train, y_train)
        self.is_trained = True
        print("✅ [ML Pipeline] Model successfully trained with independent genre data!")

    def rank_theaters_for_user(
        self,
        requested_format: str,
        needs_accessibility: bool,
        movie_profile: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        
        # Extract Genre Flags
        is_action = 1 if movie_profile.get("is_action") else 0
        is_scifi = 1 if movie_profile.get("is_scifi") else 0
        is_comedy = 1 if movie_profile.get("is_comedy") else 0
        needs_access_flag = 1 if needs_accessibility else 0
        runtime_min = float(movie_profile.get("runtime_min", 120))
        
        kb = self.data_provider.get_format_knowledge_base()
        theaters = self.data_provider.get_available_theaters()

        ranked_results = []
        
        for t in theaters:
            screens = [str(s) for s in t.get("screens", [])]
            if not screens:
                continue 

            dist_km = float(t.get("distance_km", 10.0))
            has_access_flag = 1 if t.get("has_step_free_access", False) else 0

            best_screen_score = 0.0
            best_matched_fmt = "NONE"

            # Evaluate every screen in the theater
            for screen_format in screens:
                screen_meta = kb.get(screen_format, {})
                
                # Construct the 10-feature array
                features = np.array([[
                    1 if screen_format == requested_format else 0,
                    float(screen_meta.get("tier", 1)),            
                    1 if screen_meta.get("has_motion") else 0,    
                    dist_km,                                      
                    needs_access_flag,                            
                    has_access_flag,                              
                    runtime_min,                                  
                    is_action,                                    
                    is_scifi,                                     
                    is_comedy                                     
                ]])
                
                # 🔥 ML INFERENCE PREDICTION 🔥
                ml_predicted_score = self.model.predict(features)[0]
                
                if ml_predicted_score > best_screen_score:
                    best_screen_score = ml_predicted_score
                    best_matched_fmt = screen_format

            reason = f"ML Score based on distance ({dist_km}km) & format"
            if needs_accessibility and has_access_flag == 0:
                reason = "Accessibility dealbreaker"

            ranked_results.append({
                "id": t["id"],
                "name": t["name"],
                "matched_format": best_matched_fmt,
                "reason": reason,
                "score": round(best_screen_score, 2)
            })

        return sorted(ranked_results, key=lambda x: x["score"], reverse=True)

    def record_booking_action(self, query_id: str, chosen_theater_id: str, score: float):
        self.data_provider.log_user_interaction(query_id, chosen_theater_id, score)


# =====================================================================
# 5. EXECUTION & THE TOGGLE SWITCH
# =====================================================================
if __name__ == "__main__":
    
    USE_SUPABASE = False 
    
    provider = SupabaseDataProvider("", "") if USE_SUPABASE else MockDataProvider()
    ml_system = AuraMLEngine(data_provider=provider)

    print("\n🎬 AURA CINEMA RECOMMENDER - COLD START CLI")
    movie_name = input("Enter movie name [default: Upcoming Release]: ").strip() or "Upcoming Release"

    print("\nChoose a guessed format (press Enter if the AI should stay cold-start and not guess):")
    print("  - IMAX_LASER")
    print("  - IMAX_2D")
    print("  - DOLBY_CINEMA")
    print("  - 4DX")
    print("  - PVR_PXL")
    print("  - STANDARD_2D")

    guessed_format = input("Format [default: UNKNOWN]: ").strip()
    format_map = {
        "IMAX_LASER": "IMAX_LASER",
        "IMAX_2D": "IMAX_2D",
        "DOLBY_CINEMA": "DOLBY_CINEMA",
        "4DX": "4DX",
        "PVR_PXL": "PVR_PXL",
        "STANDARD_2D": "STANDARD_2D",
    }
    requested_format = format_map.get(guessed_format, "STANDARD_2D")
    cold_start = guessed_format.strip() == ""

    if cold_start:
        print(f"\n🧠 Cold start for '{movie_name}': the AI does not yet know the best format, so it will rank theaters using a neutral fallback.")
    else:
        print(f"\n🧠 Initial format guess for '{movie_name}': {requested_format}")

    # ---------------------------------------------------------
    # TEST 1: PURE SCI-FI (User willing to travel for IMAX)
    # ---------------------------------------------------------
    print("\n--- TEST 1: Searching for 'Interstellar' (Sci-Fi, 169 mins) ---")
    results_scifi = ml_system.rank_theaters_for_user(
        requested_format=requested_format, 
        needs_accessibility=False,
        movie_profile={"is_action": False, "is_scifi": True, "is_comedy": False, "runtime_min": 169}
    )
    for rank, r in enumerate(results_scifi, start=1):
        print(f"Rank #{rank}: {r['name']:<22} | Format: {r['matched_format']:<12} | ML Score: {r['score']}")

    # ---------------------------------------------------------
    # TEST 2: PURE COMEDY (User wants closest screen)
    # ---------------------------------------------------------
    print("\n--- TEST 2: Searching for 'The Hangover' (Comedy, 100 mins) ---")
    results_comedy = ml_system.rank_theaters_for_user(
        requested_format=requested_format, 
        needs_accessibility=False,
        movie_profile={"is_action": False, "is_scifi": False, "is_comedy": True, "runtime_min": 100}
    )
    for rank, r in enumerate(results_comedy, start=1):
        print(f"Rank #{rank}: {r['name']:<22} | Format: {r['matched_format']:<12} | ML Score: {r['score']}")

    # ---------------------------------------------------------
    # TEST 3: MULTI-GENRE (Sci-Fi + Action + Long Runtime)
    # Model must balance motion-seat boost vs runtime exhaustion
    # ---------------------------------------------------------
    print("\n--- TEST 3: Searching for 'Dune: Part Two' (Sci-Fi + Action, 166 mins) ---")
    results_multi = ml_system.rank_theaters_for_user(
        requested_format=requested_format, 
        needs_accessibility=False,
        movie_profile={"is_action": True, "is_scifi": True, "is_comedy": False, "runtime_min": 166}
    )
    for rank, r in enumerate(results_multi, start=1):
        print(f"Rank #{rank}: {r['name']:<22} | Format: {r['matched_format']:<12} | ML Score: {r['score']}")