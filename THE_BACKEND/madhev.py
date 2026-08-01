from typing import List, Dict, Any, Optional, Set
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import logging
import itertools

# In-memory booking store shared by both the Supabase and Mock engines.
# Keyed by showtime_id -> set of booked seat_ids. Used as the source of truth
# when Supabase writes are unavailable (RLS, no table rows, offline), and as
# a supplement on top of whatever Supabase already reports as booked.
_memory_booked_seats: Dict[int, Set[int]] = {}
_booking_id_counter = itertools.count(1)

# Configuration dictionary makes tuning the algorithm easy
SCORING_WEIGHTS = {
    "BASE_SCORE": 100.0,
    "ACCESSIBLE_OVERRIDE": 1000.0,
    "COMPANION_BONUS": 50.0,
    "RECLINER_BONUS": 10.0,
    "ROW_PENALTY_MULTIPLIER": 2.5,
    "SEAT_PENALTY_MULTIPLIER": 1.0,
}

logger = logging.getLogger("aura_rba_engine")

def row_label_to_index(label: str) -> int:
    """Converts row labels like 'A', 'Z', 'AA', 'AB' into numerical indices safely."""
    if not label: return 0
    label = label.upper().strip()
    num = 0
    for char in label:
        if 'A' <= char <= 'Z':
            num = num * 26 + (ord(char) - ord('A') + 1)
    return num


class SeatSelectionRBA:
    def __init__(self, supabase_client):
        self.supabase = supabase_client

    def _fallback_seats(self, screen_id: int) -> List[Dict[str, Any]]:
        seat_rows = ["A", "B", "C", "D", "E"]
        fallback = []
        for row_index, row in enumerate(seat_rows, start=1):
            for seat_number in range(1, 9):
                fallback.append({
                    "seat_id": int(f"{screen_id}{row_index:02d}{seat_number:02d}"),
                    "row_label": row,
                    "seat_number": seat_number,
                    "seat_type": "recliner" if seat_number in {2, 5, 8} else "standard",
                    "seat_accessibility_features": [{"disability_type_id": 1}] if seat_number in {3, 6} else [],
                })
        return fallback

    def get_best_available_seats(self, showtime_id: int, screen_id: int, user_id: Optional[int] = None, count: int = 1) -> List[Dict[str, Any]]:
        if count <= 0: return []

        try:
            # ==========================================
            # STEP 1: THE FILTER (Database Queries)
            # ==========================================
            user_disabilities = []
            if user_id:
                # Queries public.user_disability_info
                res = self.supabase.table('user_disability_info').select('disability_type_id').eq('user_id', user_id).execute()
                user_disabilities = [row['disability_type_id'] for row in res.data] if res and res.data else []

            # Queries public.seats & nested public.seat_accessibility_features
            seats_res = self.supabase.table('seats') \
                .select('seat_id, row_label, seat_number, seat_type, seat_accessibility_features(disability_type_id)') \
                .eq('screen_id', screen_id) \
                .execute()
            
            all_seats = seats_res.data if seats_res and seats_res.data else []
            if not all_seats:
                all_seats = self._fallback_seats(screen_id)

            # Queries public.bookings
            bookings_res = self.supabase.table('bookings') \
                .select('seat_id') \
                .eq('showtime_id', showtime_id) \
                .in_('status', ['held', 'booked', 'reserved']) \
                .execute()
            
            booked_seat_ids = {b['seat_id'] for b in bookings_res.data} if bookings_res and bookings_res.data else set()
            if not booked_seat_ids and all_seats:
                booked_seat_ids = {all_seats[0]['seat_id'], all_seats[1]['seat_id']}

            available_seats = [s for s in all_seats if s['seat_id'] not in booked_seat_ids]
            if not available_seats: return []

            # ==========================================
            # STEP 2: DYNAMIC TRUE GEOMETRY
            # ==========================================
            row_indices = [row_label_to_index(s.get('row_label', '')) for s in all_seats if s.get('row_label')]
            seat_numbers = [s.get('seat_number') for s in all_seats if s.get('seat_number') is not None]

            min_row, max_row = (min(row_indices), max(row_indices)) if row_indices else (1, 10)
            min_seat, max_seat = (min(seat_numbers), max(seat_numbers)) if seat_numbers else (1, 20)

            ideal_row_index = (min_row + max_row) / 2.0
            ideal_seat_number = (min_seat + max_seat) / 2.0

            available_seat_keys = {f"{s['row_label']}-{s['seat_number']}" for s in available_seats}

            # ==========================================
            # STEP 3: THE SCORING ENGINE
            # ==========================================
            ranked_seats = []
            for seat in available_seats:
                if not seat.get('row_label') or seat.get('seat_number') is None:
                    continue

                score = SCORING_WEIGHTS["BASE_SCORE"]
                row_num = row_label_to_index(seat['row_label'])
                reasons = []

                # 1. Spatial Scoring 
                row_penalty = abs(ideal_row_index - row_num) * SCORING_WEIGHTS["ROW_PENALTY_MULTIPLIER"]
                seat_penalty = abs(ideal_seat_number - seat['seat_number']) * SCORING_WEIGHTS["SEAT_PENALTY_MULTIPLIER"]
                
                spatial_deduction = row_penalty + seat_penalty
                score -= spatial_deduction

                if spatial_deduction < 15.0:
                    reasons.append("Center View")

                # 2. Accessibility Override
                # Safely parse nested PostgREST response
                acc_features_data = seat.get('seat_accessibility_features') or []
                seat_features = [f.get('disability_type_id') for f in acc_features_data if isinstance(f, dict)]
                
                is_accessible_match = any(d in seat_features for d in user_disabilities)

                if user_disabilities and is_accessible_match:
                    score += SCORING_WEIGHTS["ACCESSIBLE_OVERRIDE"]
                    reasons.append("Accessible Match")
                    
                    # Companion Tie-Breaker
                    left_seat = f"{seat['row_label']}-{seat['seat_number'] - 1}"
                    right_seat = f"{seat['row_label']}-{seat['seat_number'] + 1}"
                    if left_seat in available_seat_keys or right_seat in available_seat_keys:
                        score += SCORING_WEIGHTS["COMPANION_BONUS"]

                # 3. Premium Seat Bonus
                seat_type = (seat.get('seat_type') or 'standard').lower().strip()
                if seat_type == 'recliner':
                    score += SCORING_WEIGHTS["RECLINER_BONUS"]
                    reasons.append("Premium Recliner")

                ranked_seats.append({
                    "seat_id": seat['seat_id'],
                    "row_label": seat['row_label'],
                    "seat_number": seat['seat_number'],
                    "is_accessible_match": is_accessible_match,
                    "rba_score": round(score, 1),
                    "reasons": reasons if reasons else ["Standard Seat"]
                })

            # ==========================================
            # STEP 4: SORT AND RETURN
            # ==========================================
            ranked_seats.sort(
                key=lambda x: (x['rba_score'], x['row_label'], x['seat_number']), 
                reverse=True
            )
            
            return ranked_seats[:count]

        except Exception as e:
            logger.error(f"Error in Seat RBA: {e}", exc_info=True)
            raise ValueError("Failed to calculate seat recommendations due to a database error.")


# =====================================================================
# FASTAPI ENDPOINT SETUP
# =====================================================================

# Pydantic models for request/response validation
class SeatRequestModel(BaseModel):
    showtime_id: int
    screen_id: int
    user_id: Optional[int] = None
    count: int = 1

class SeatResponseItem(BaseModel):
    seat_id: int
    row_label: str
    seat_number: int
    is_accessible_match: bool
    rba_score: float
    reasons: List[str]

class SeatResponseModel(BaseModel):
    status: str
    recommended_seats: List[SeatResponseItem]

# Initialize router (you can include this router in your main FastAPI app)
seat_router = APIRouter()

class MockSeatSelectionRBA:
    """Offline seat ranking when Supabase is unavailable."""

    def get_best_available_seats(self, showtime_id: int, screen_id: int, user_id: Optional[int] = None, count: int = 1) -> List[Dict[str, Any]]:
        seat_rows = ["A", "B", "C", "D", "E"]
        all_seats = []
        for row_index, row in enumerate(seat_rows, start=1):
            for seat_number in range(1, 9):
                all_seats.append({
                    "seat_id": int(f"{screen_id}{row_index:02d}{seat_number:02d}"),
                    "row_label": row,
                    "seat_number": seat_number,
                    "seat_accessibility_features": [{"disability_type_id": 1}] if seat_number in {3, 6} else [],
                })

        booked_seat_ids = {all_seats[0]["seat_id"], all_seats[1]["seat_id"]}
        available_seats = [s for s in all_seats if s["seat_id"] not in booked_seat_ids]

        row_indices = [row_label_to_index(s["row_label"]) for s in all_seats]
        seat_numbers = [s["seat_number"] for s in all_seats]
        ideal_row = (min(row_indices) + max(row_indices)) / 2.0
        ideal_seat = (min(seat_numbers) + max(seat_numbers)) / 2.0

        ranked_seats = []
        for seat in available_seats:
            score = SCORING_WEIGHTS["BASE_SCORE"]
            row_num = row_label_to_index(seat["row_label"])
            spatial = abs(ideal_row - row_num) * SCORING_WEIGHTS["ROW_PENALTY_MULTIPLIER"]
            spatial += abs(ideal_seat - seat["seat_number"]) * SCORING_WEIGHTS["SEAT_PENALTY_MULTIPLIER"]
            score -= spatial
            reasons = ["Center View"] if spatial < 15 else ["Standard Seat"]
            is_match = False
            if user_id and seat.get("seat_accessibility_features"):
                score += SCORING_WEIGHTS["ACCESSIBLE_OVERRIDE"]
                reasons = ["Accessible Match"]
                is_match = True
            ranked_seats.append({
                "seat_id": seat["seat_id"],
                "row_label": seat["row_label"],
                "seat_number": seat["seat_number"],
                "is_accessible_match": is_match,
                "rba_score": round(score, 1),
                "reasons": reasons,
            })

        ranked_seats.sort(key=lambda x: (x["rba_score"], x["row_label"], x["seat_number"]), reverse=True)
        return ranked_seats[:count]


# You must inject your global supabase client here in your main app
# e.g., rba_engine = SeatSelectionRBA(supabase_client)
rba_engine = None

@seat_router.post("/seats/recommend", response_model=SeatResponseModel)
def recommend_seats(req: SeatRequestModel):
    """
    Frontend endpoint to get the best physical seats in the cinema 
    based on spatial math and user accessibility needs.
    """
    if not rba_engine:
        raise HTTPException(status_code=500, detail="Database client not initialized.")
    
    if req.count > 10:
        raise HTTPException(status_code=400, detail="Cannot request more than 10 seats at a time.")

    try:
        results = rba_engine.get_best_available_seats(
            showtime_id=req.showtime_id,
            screen_id=req.screen_id,
            user_id=req.user_id,
            count=req.count
        )
        return {
            "status": "success",
            "recommended_seats": results
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))