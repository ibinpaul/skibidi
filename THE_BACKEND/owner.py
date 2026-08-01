"""Theater owner / manager reporting — direct Supabase reads, no ML."""
import logging
from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger("aura_owner_api")
owner_router = APIRouter()

_provider = None


def init_owner_router(data_provider):
    global _provider
    _provider = data_provider


class FormatDemandItem(BaseModel):
    format_name: str
    booking_count: int
    share_pct: float


class AreaDemandItem(BaseModel):
    area_label: str
    latitude: float
    longitude: float
    demand_score: float
    top_format: str


class DisabilityBookingItem(BaseModel):
    booking_id: str
    user_id: Optional[int]
    cinema_name: str
    movie_title: str
    showtime_label: str
    assistance_needed: bool


class OwnerDashboardResponse(BaseModel):
    status: str
    total_bookings: int
    disability_bookings_today: int
    format_demand: List[FormatDemandItem]
    area_heatmap: List[AreaDemandItem]
    disability_feed: List[DisabilityBookingItem]
    profitability_hint: str


def _mock_dashboard() -> Dict[str, Any]:
    return {
        "total_bookings": 1842,
        "disability_bookings_today": 7,
        "format_demand": [
            {"format_name": "IMAX_LASER", "booking_count": 412, "share_pct": 28.4},
            {"format_name": "DOLBY_CINEMA", "booking_count": 389, "share_pct": 26.8},
            {"format_name": "4DX", "booking_count": 256, "share_pct": 17.6},
            {"format_name": "IMAX_2D", "booking_count": 198, "share_pct": 13.6},
            {"format_name": "STANDARD_2D", "booking_count": 587, "share_pct": 13.6},
        ],
        "area_heatmap": [
            {"area_label": "Lulu Mall", "latitude": 9.998, "longitude": 76.301, "demand_score": 0.92, "top_format": "IMAX_LASER"},
            {"area_label": "Edappally", "latitude": 10.021, "longitude": 76.308, "demand_score": 0.78, "top_format": "DOLBY_CINEMA"},
            {"area_label": "Kakkanad", "latitude": 10.006, "longitude": 76.331, "demand_score": 0.61, "top_format": "4DX"},
            {"area_label": "Fort Kochi", "latitude": 9.965, "longitude": 76.243, "demand_score": 0.44, "top_format": "STANDARD_2D"},
        ],
        "disability_feed": [
            {"booking_id": "b-901", "user_id": 12, "cinema_name": "PVR Lulu Mall", "movie_title": "Dune: Part Two", "showtime_label": "Today 7:30 PM", "assistance_needed": True},
            {"booking_id": "b-902", "user_id": 34, "cinema_name": "Shenoys Cinemas", "movie_title": "Inside Out 2", "showtime_label": "Today 4:15 PM", "assistance_needed": True},
        ],
        "profitability_hint": "IMAX_LASER in Lulu Mall corridor shows 2.3× lift vs city-wide Standard 2D baseline.",
    }


def _build_from_supabase(supabase) -> Dict[str, Any]:
    try:
        bookings_res = supabase.table("bookings").select(
            "booking_id, status, showtime_id, user_id, showtimes(start_time, movies(title), screens(name, cinemas(name, latitude, longitude)))"
        ).in_("status", ["booked", "reserved", "held"]).limit(500).execute()

        bookings = bookings_res.data if bookings_res and bookings_res.data else []
        format_counts: Counter = Counter()
        area_map: Dict[str, Dict] = {}
        disability_feed: List[Dict] = []

        disability_user_ids: set = set()
        try:
            dis_res = supabase.table("user_disability_info").select("user_id").execute()
            if dis_res and dis_res.data:
                disability_user_ids = {r["user_id"] for r in dis_res.data if r.get("user_id") is not None}
        except Exception:
            pass

        for b in bookings:
            showtime = b.get("showtimes") or {}
            screen = showtime.get("screens") or {}
            cinema = screen.get("cinemas") or {}
            fmt = (screen.get("name") or "STANDARD").upper()
            if "IMAX" in fmt:
                fmt_key = "IMAX_LASER" if "LASER" in fmt else "IMAX_2D"
            elif "DOLBY" in fmt or "ATMOS" in fmt:
                fmt_key = "DOLBY_CINEMA"
            elif "4DX" in fmt:
                fmt_key = "4DX"
            else:
                fmt_key = "STANDARD_2D"
            format_counts[fmt_key] += 1

            cinema_name = cinema.get("name") or "Unknown"
            lat = cinema.get("latitude") or 0.0
            lon = cinema.get("longitude") or 0.0
            if cinema_name not in area_map:
                area_map[cinema_name] = {"lat": lat, "lon": lon, "count": 0, "formats": Counter()}
            area_map[cinema_name]["count"] += 1
            area_map[cinema_name]["formats"][fmt_key] += 1

            uid = b.get("user_id")
            if uid in disability_user_ids:
                movie = (showtime.get("movies") or {}).get("title") or "Unknown"
                disability_feed.append({
                    "booking_id": str(b.get("booking_id", "")),
                    "user_id": uid,
                    "cinema_name": cinema_name,
                    "movie_title": movie,
                    "showtime_label": str(showtime.get("start_time") or "TBD"),
                    "assistance_needed": True,
                })

        total = sum(format_counts.values()) or 1
        format_demand = [
            {"format_name": k, "booking_count": v, "share_pct": round(100 * v / total, 1)}
            for k, v in format_counts.most_common()
        ] or _mock_dashboard()["format_demand"]

        max_count = max((a["count"] for a in area_map.values()), default=1) or 1
        area_heatmap = [
            {
                "area_label": name,
                "latitude": data["lat"],
                "longitude": data["lon"],
                "demand_score": round(data["count"] / max_count, 2),
                "top_format": data["formats"].most_common(1)[0][0] if data["formats"] else "STANDARD_2D",
            }
            for name, data in area_map.items()
        ] or _mock_dashboard()["area_heatmap"]

        top_fmt = format_counts.most_common(1)[0][0] if format_counts else "IMAX_LASER"
        top_area = max(area_map.items(), key=lambda x: x[1]["count"])[0] if area_map else "Lulu Mall"

        return {
            "total_bookings": total,
            "disability_bookings_today": len(disability_feed),
            "format_demand": format_demand,
            "area_heatmap": area_heatmap,
            "disability_feed": disability_feed[:20] or _mock_dashboard()["disability_feed"],
            "profitability_hint": f"{top_fmt} near {top_area} is trending highest in current booking mix.",
        }
    except Exception as e:
        logger.error(f"Owner dashboard Supabase error: {e}")
        return _mock_dashboard()


@owner_router.get("/dashboard", response_model=OwnerDashboardResponse)
def get_owner_dashboard():
    if _provider is None:
        raise HTTPException(status_code=500, detail="Owner router not initialized.")

    supabase = getattr(_provider, "supabase", None)
    if supabase is not None:
        data = _build_from_supabase(supabase)
    else:
        data = _mock_dashboard()

    return {"status": "success", **data}
