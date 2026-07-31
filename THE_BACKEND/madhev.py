from typing import List, Dict, Any, Optional

# Configuration dictionary makes tuning the algorithm easy
SCORING_WEIGHTS = {
    "BASE_SCORE": 100.0,
    "ACCESSIBLE_OVERRIDE": 1000.0,
    "COMPANION_BONUS": 50.0,
    "RECLINER_BONUS": 10.0,
    "ROW_PENALTY_MULTIPLIER": 2.5,
    "SEAT_PENALTY_MULTIPLIER": 1.0,
}

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

    def get_best_available_seats(self, showtime_id: int, screen_id: int, user_id: Optional[int] = None, count: int = 1) -> List[Dict[str, Any]]:
        if count <= 0: return []

        # ==========================================
        # STEP 1: THE FILTER (Database Queries)
        # ==========================================
        user_disabilities = []
        if user_id:
            res = self.supabase.table('user_disability_info').select('disability_type_id').eq('user_id', user_id).execute()
            user_disabilities = [row['disability_type_id'] for row in res.data]

        seats_res = self.supabase.table('seats') \
            .select('seat_id, row_label, seat_number, seat_type, seat_accessibility_features(disability_type_id)') \
            .eq('screen_id', screen_id) \
            .execute()
        all_seats = seats_res.data

        bookings_res = self.supabase.table('bookings') \
            .select('seat_id') \
            .eq('showtime_id', showtime_id) \
            .in_('status', ['held', 'booked']) \
            .execute()
        booked_seat_ids = {b['seat_id'] for b in bookings_res.data}

        available_seats = [s for s in all_seats if s['seat_id'] not in booked_seat_ids]
        if not available_seats: return []

        # ==========================================
        # STEP 2: DYNAMIC TRUE GEOMETRY
        # ==========================================
        # Filter out malformed seat data dynamically
        row_indices = [row_label_to_index(s.get('row_label', '')) for s in all_seats if s.get('row_label')]
        seat_numbers = [s.get('seat_number') for s in all_seats if s.get('seat_number') is not None]

        min_row, max_row = (min(row_indices), max(row_indices)) if row_indices else (1, 10)
        min_seat, max_seat = (min(seat_numbers), max(seat_numbers)) if seat_numbers else (1, 20)

        # Fix: True center using min + max (handles aisles and gaps)
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

            # 1. Spatial Scoring (Now applies to ALL seats, including accessible ones)
            row_penalty = abs(ideal_row_index - row_num) * SCORING_WEIGHTS["ROW_PENALTY_MULTIPLIER"]
            seat_penalty = abs(ideal_seat_number - seat['seat_number']) * SCORING_WEIGHTS["SEAT_PENALTY_MULTIPLIER"]
            
            spatial_deduction = row_penalty + seat_penalty
            score -= spatial_deduction

            if spatial_deduction < 15.0:  # Threshold for "Good View"
                reasons.append("Center View")

            # 2. Accessibility Override
            seat_features = [f['disability_type_id'] for f in seat.get('seat_accessibility_features', []) if f]
            is_accessible_match = any(d in seat_features for d in user_disabilities)

            if user_disabilities and is_accessible_match:
                score += SCORING_WEIGHTS["ACCESSIBLE_OVERRIDE"]
                reasons.append("Accessible Match")
                
                # Companion Tie-Breaker
                left_seat = f"{seat['row_label']}-{seat['seat_number'] - 1}"
                right_seat = f"{seat['row_label']}-{seat['seat_number'] + 1}"
                if left_seat in available_seat_keys or right_seat in available_seat_keys:
                    score += SCORING_WEIGHTS["COMPANION_BONUS"]

            # 3. Premium Seat Bonus (Case-insensitive check)
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
        # Sort by Score DESC, then fallback to Row and Seat to break exact ties deterministically
        ranked_seats.sort(
            key=lambda x: (x['rba_score'], x['row_label'], x['seat_number']), 
            reverse=True
        )
        
        return ranked_seats[:count]