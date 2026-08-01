export type GenreFlags = {
  is_action: boolean;
  is_scifi: boolean;
  is_comedy: boolean;
  is_horror: boolean;
  is_drama: boolean;
  is_romance: boolean;
  is_thriller: boolean;
  is_animation: boolean;
  is_fantasy: boolean;
  is_family: boolean;
  runtime_min: number;
};

export type ShowtimeSlot = {
  showtime_id: number;
  screen_id: number;
  starts_at: string;
  format_label: string;
};

export type TheaterRanking = {
  id: string;
  name: string;
  distance_km: number;
  matched_format: string;
  reason: string;
  lift: number;
  score: number;
  showtimes: ShowtimeSlot[];
};

export type RecommendationResponse = {
  status: string;
  movie: string;
  is_cold_start: boolean;
  optimized_format_target: string;
  rankings: TheaterRanking[];
};

export type SeatRecommendation = {
  seat_id: number;
  row_label: string;
  seat_number: number;
  is_accessible_match: boolean;
  rba_score: number;
  reasons: string[];
};

export type SeatResponse = {
  status: string;
  recommended_seats: SeatRecommendation[];
};

export type NowShowingMovie = {
  title: string;
  guessed_format: string;
  runtime_min: number;
};

export type NowShowingResponse = {
  status: string;
  movies: NowShowingMovie[];
};

export type MovieAnalyzeResponse = {
  status: string;
  movie: string;
  ratio: string;
  recommended_format: string;
  snippet_preview: string;
  source: string;
  movie_profile: GenreFlags;
};

export type FormatDemandItem = {
  format_name: string;
  booking_count: number;
  share_pct: number;
};

export type AreaDemandItem = {
  area_label: string;
  latitude: number;
  longitude: number;
  demand_score: number;
  top_format: string;
};

export type DisabilityBookingItem = {
  booking_id: string;
  user_id: number | null;
  cinema_name: string;
  movie_title: string;
  showtime_label: string;
  assistance_needed: boolean;
};

export type OwnerDashboardResponse = {
  status: string;
  total_bookings: number;
  disability_bookings_today: number;
  format_demand: FormatDemandItem[];
  area_heatmap: AreaDemandItem[];
  disability_feed: DisabilityBookingItem[];
  profitability_hint: string;
};

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000';

async function parseJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `Request failed with ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export async function fetchNowShowingMovies(): Promise<NowShowingResponse> {
  const response = await fetch(`${apiBaseUrl}/movies/now-showing`);
  return parseJson<NowShowingResponse>(response);
}

export async function analyzeMovie(title: string): Promise<MovieAnalyzeResponse> {
  const response = await fetch(`${apiBaseUrl}/movies/analyze`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title }),
  });
  return parseJson<MovieAnalyzeResponse>(response);
}

export async function recommendTheaters(payload: {
  movie_name: string;
  guessed_format: string;
  needs_accessibility: boolean;
  user_lat?: number;
  user_lon?: number;
  movie_profile: GenreFlags;
}): Promise<RecommendationResponse> {
  const response = await fetch(`${apiBaseUrl}/recommend`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  return parseJson<RecommendationResponse>(response);
}

export async function recommendSeats(payload: {
  showtime_id: number;
  screen_id: number;
  user_id?: number;
  count: number;
}): Promise<SeatResponse> {
  const response = await fetch(`${apiBaseUrl}/rba/seats/recommend`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  return parseJson<SeatResponse>(response);
}

export async function fetchOwnerDashboard(): Promise<OwnerDashboardResponse> {
  const response = await fetch(`${apiBaseUrl}/owner/dashboard`);
  return parseJson<OwnerDashboardResponse>(response);
}

export const FORMAT_LABELS: Record<string, string> = {
  IMAX_LASER: 'IMAX Laser',
  IMAX_2D: 'IMAX 2D',
  DOLBY_CINEMA: 'Dolby Cinema',
  '4DX': '4DX Motion',
  PVR_PXL: 'PVR PXL',
  SCREENX: 'ScreenX',
  STANDARD_2D: 'Standard 2D',
};

export function formatLabel(code: string): string {
  return FORMAT_LABELS[code] || code.replace(/_/g, ' ');
}

export const POSTER_GRADIENTS = [
  'linear-gradient(135deg, #ff006e 0%, #8338ec 50%, #3a0ca3 100%)',
  'linear-gradient(135deg, #ffd700 0%, #ff006e 60%, #03045e 100%)',
  'linear-gradient(135deg, #06d6a0 0%, #118ab2 50%, #073b4c 100%)',
  'linear-gradient(135deg, #fb5607 0%, #ff006e 45%, #3a0ca3 100%)',
  'linear-gradient(135deg, #7209b7 0%, #f72585 50%, #4cc9f0 100%)',
  'linear-gradient(135deg, #ffc300 0%, #ff006e 40%, #03071e 100%)',
];
