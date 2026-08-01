import { useCallback, useEffect, useMemo, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import {
  analyzeMovie,
  fetchNowShowingMovies,
  formatLabel,
  POSTER_GRADIENTS,
  recommendSeats,
  recommendTheaters,
  type GenreFlags,
  type MovieAnalyzeResponse,
  type NowShowingMovie,
  type RecommendationResponse,
  type SeatRecommendation,
  type ShowtimeSlot,
  type TheaterRanking,
} from '../lib/api';

type Step = 'movies' | 'scan' | 'prefs' | 'theaters' | 'seats' | 'done';

const STEP_ORDER: Step[] = ['movies', 'scan', 'prefs', 'theaters', 'seats', 'done'];

function activeGenres(profile: GenreFlags): string[] {
  const map: [keyof GenreFlags, string][] = [
    ['is_action', 'Action'],
    ['is_scifi', 'Sci-Fi'],
    ['is_comedy', 'Comedy'],
    ['is_horror', 'Horror'],
    ['is_drama', 'Drama'],
    ['is_romance', 'Romance'],
    ['is_thriller', 'Thriller'],
    ['is_animation', 'Animation'],
    ['is_fantasy', 'Fantasy'],
    ['is_family', 'Family'],
  ];
  return map.filter(([k]) => profile[k]).map(([, label]) => label);
}

function SeatMap({ seats, allRows }: { seats: SeatRecommendation[]; allRows: string[] }) {
  const picked = new Set(seats.map((s) => `${s.row_label}-${s.seat_number}`));
  const rows = allRows.length ? allRows : ['A', 'B', 'C', 'D', 'E'];

  return (
    <div className="seat-map">
      <div className="screen-curve">SCREEN</div>
      {rows.map((row) => (
        <div key={row} className="seat-row">
          <span className="row-label">{row}</span>
          {Array.from({ length: 8 }, (_, i) => i + 1).map((num) => {
            const key = `${row}-${num}`;
            const isRec = picked.has(key);
            return (
              <div key={key} className={isRec ? 'seat rec' : 'seat'} title={isRec ? 'Recommended' : ''}>
                {isRec ? '★' : ''}
              </div>
            );
          })}
        </div>
      ))}
    </div>
  );
}

export default function MoviegoerApp({ onExit }: { onExit: () => void }) {
  const [step, setStep] = useState<Step>('movies');
  const [movies, setMovies] = useState<NowShowingMovie[]>([]);
  const [selectedMovie, setSelectedMovie] = useState<NowShowingMovie | null>(null);
  const [analysis, setAnalysis] = useState<MovieAnalyzeResponse | null>(null);
  const [needsAccess, setNeedsAccess] = useState(false);
  const [userId, setUserId] = useState('');
  const [seatCount, setSeatCount] = useState(2);
  const [coords, setCoords] = useState<{ lat: number; lon: number } | null>(null);
  const [theaterResult, setTheaterResult] = useState<RecommendationResponse | null>(null);
  const [pickedTheater, setPickedTheater] = useState<TheaterRanking | null>(null);
  const [pickedShowtime, setPickedShowtime] = useState<ShowtimeSlot | null>(null);
  const [seats, setSeats] = useState<SeatRecommendation[]>([]);
  const [loading, setLoading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchNowShowingMovies()
      .then((r) => setMovies(r.movies))
      .catch(() => setError('Could not load movies — is the backend running on :8000?'));
  }, []);

  const stepIndex = STEP_ORDER.indexOf(step);

  const pickMovie = async (movie: NowShowingMovie) => {
    setSelectedMovie(movie);
    setError(null);
    setStep('scan');
    setLoading('scan');
    try {
      const result = await analyzeMovie(movie.title);
      setAnalysis(result);
      setStep('prefs');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Scraper failed');
      setStep('movies');
    } finally {
      setLoading(null);
    }
  };

  const useLocation = () => {
    if (!navigator.geolocation) {
      setError('Geolocation not supported');
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setCoords({ lat: pos.coords.latitude, lon: pos.coords.longitude });
        setError(null);
      },
      () => setError('Location denied — rankings will use default distance'),
    );
  };

  const rankTheaters = async () => {
    if (!selectedMovie || !analysis) return;
    setLoading('theaters');
    setError(null);
    try {
      const res = await recommendTheaters({
        movie_name: selectedMovie.title,
        guessed_format: analysis.recommended_format,
        needs_accessibility: needsAccess,
        user_lat: coords?.lat,
        user_lon: coords?.lon,
        movie_profile: analysis.movie_profile,
      });
      setTheaterResult(res);
      setStep('theaters');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'ML ranking failed');
    } finally {
      setLoading(null);
    }
  };

  const pickTheater = (t: TheaterRanking) => {
    setPickedTheater(t);
    setPickedShowtime(t.showtimes[0] ?? null);
  };

  const fetchSeats = async () => {
    if (!pickedShowtime) return;
    setLoading('seats');
    setError(null);
    try {
      const res = await recommendSeats({
        showtime_id: pickedShowtime.showtime_id,
        screen_id: pickedShowtime.screen_id,
        user_id: userId.trim() ? Number(userId) : undefined,
        count: seatCount,
      });
      setSeats(res.recommended_seats);
      setStep('seats');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Seat RBA failed');
    } finally {
      setLoading(null);
    }
  };

  const genres = useMemo(() => (analysis ? activeGenres(analysis.movie_profile) : []), [analysis]);

  const goBack = useCallback(() => {
    const idx = STEP_ORDER.indexOf(step);
    if (idx > 0) setStep(STEP_ORDER[idx - 1]);
  }, [step]);

  return (
    <div className="mg-shell">
      <div className="marquee-border" />
      <header className="mg-header">
        <button type="button" className="ghost-btn" onClick={onExit}>← Portal</button>
        <div className="logo-burst">XILO</div>
        <div className="step-dots">
          {STEP_ORDER.slice(0, -1).map((s, i) => (
            <span key={s} className={i <= stepIndex ? 'dot on' : 'dot'} />
          ))}
        </div>
      </header>

      {error && <div className="flash-error">{error}</div>}

      <AnimatePresence mode="wait">
        {step === 'movies' && (
          <motion.section key="movies" className="mg-panel" initial={{ opacity: 0, x: 40 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -40 }}>
            <h1 className="mega-title">Pick Your<br />Blockbuster</h1>
            <p className="sub-glow">Tap a film — we scan the web for format DNA, then ML finds your perfect theater.</p>
            <div className="poster-wall">
              {movies.map((m, i) => (
                <button key={m.title} type="button" className="poster-card" style={{ background: POSTER_GRADIENTS[i % POSTER_GRADIENTS.length] }} onClick={() => pickMovie(m)}>
                  <span className="poster-format">{formatLabel(m.guessed_format)}</span>
                  <strong>{m.title}</strong>
                  <small>{m.runtime_min} min</small>
                </button>
              ))}
            </div>
          </motion.section>
        )}

        {step === 'scan' && selectedMovie && (
          <motion.section key="scan" className="mg-panel scan-panel" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
            <div className="radar">
              <div className="radar-sweep" />
              <div className="radar-core">{selectedMovie.title.slice(0, 2).toUpperCase()}</div>
            </div>
            <h2 className="pulse-text">{loading === 'scan' ? 'Scanning the web…' : 'Signal locked'}</h2>
            <p className="sub-glow">DuckDuckGo scraper extracting aspect ratio, format & genre signals</p>
          </motion.section>
        )}

        {step === 'prefs' && analysis && selectedMovie && (
          <motion.section key="prefs" className="mg-panel" initial={{ opacity: 0, y: 30 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
            <h2 className="section-title">Format DNA</h2>
            <div className="dna-card">
              <div className="dna-row"><span>Film</span><strong>{selectedMovie.title}</strong></div>
              <div className="dna-row"><span>Best format</span><strong className="gold">{formatLabel(analysis.recommended_format)}</strong></div>
              <div className="dna-row"><span>Aspect</span><strong>{analysis.ratio}</strong></div>
              <div className="dna-row"><span>Runtime</span><strong>{analysis.movie_profile.runtime_min} min</strong></div>
              {genres.length > 0 && (
                <div className="tag-row">{genres.map((g) => <span key={g} className="genre-tag">{g}</span>)}</div>
              )}
              <p className="snippet">{analysis.snippet_preview}</p>
            </div>

            <label className="toggle-line">
              <input type="checkbox" checked={needsAccess} onChange={(e) => setNeedsAccess(e.target.checked)} />
              I need accessibility-friendly hosting (priority in ML + RBA)
            </label>

            <div className="action-row">
              <button type="button" className="ghost-btn" onClick={useLocation}>📍 Use my location</button>
              {coords && <span className="loc-ok">Location locked</span>}
            </div>

            <label className="field">
              User ID (optional — unlocks disability seat match in RBA)
              <input value={userId} onChange={(e) => setUserId(e.target.value)} placeholder="e.g. 12" />
            </label>

            <label className="field">
              How many seats?
              <input type="number" min={1} max={10} value={seatCount} onChange={(e) => setSeatCount(Number(e.target.value))} />
            </label>

            <div className="action-row">
              <button type="button" className="ghost-btn" onClick={goBack}>Back</button>
              <button type="button" className="neon-btn" onClick={rankTheaters} disabled={loading === 'theaters'}>
                {loading === 'theaters' ? 'ML ranking…' : 'Find my theaters →'}
              </button>
            </div>
          </motion.section>
        )}

        {step === 'theaters' && theaterResult && (
          <motion.section key="theaters" className="mg-panel" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
            <h2 className="section-title">Theater Arena</h2>
            <p className="sub-glow">ML ranked {theaterResult.rankings.length} venues for {formatLabel(theaterResult.optimized_format_target)}</p>
            <ul className="arena-list">
              {theaterResult.rankings.map((t, i) => (
                <li key={t.id}>
                  <button type="button" className={pickedTheater?.id === t.id ? 'arena-card active' : 'arena-card'} onClick={() => pickTheater(t)}>
                    <div className="rank-badge">{i + 1}</div>
                    <div className="arena-body">
                      <strong>{t.name}</strong>
                      <span>{formatLabel(t.matched_format)} · {t.distance_km} km · lift {t.lift}x</span>
                      <small>{t.reason}</small>
                    </div>
                    <div className="score-ring"><span>{Math.round(t.score)}</span></div>
                  </button>
                </li>
              ))}
            </ul>

            {pickedTheater && (
              <div className="showtime-picker">
                <h3>Showtimes at {pickedTheater.name}</h3>
                <div className="showtime-row">
                  {pickedTheater.showtimes.length === 0 ? (
                    <p className="sub-glow">No showtimes returned — using demo slots.</p>
                  ) : (
                    pickedTheater.showtimes.map((st) => (
                      <button
                        key={st.showtime_id}
                        type="button"
                        className={pickedShowtime?.showtime_id === st.showtime_id ? 'showtime-chip active' : 'showtime-chip'}
                        onClick={() => setPickedShowtime(st)}
                      >
                        {st.starts_at}<br /><small>{st.format_label}</small>
                      </button>
                    ))
                  )}
                </div>
              </div>
            )}

            <div className="action-row">
              <button type="button" className="ghost-btn" onClick={goBack}>Back</button>
              <button type="button" className="neon-btn" onClick={fetchSeats} disabled={!pickedShowtime || loading === 'seats'}>
                {loading === 'seats' ? 'RBA computing…' : 'Rank my seats →'}
              </button>
            </div>
          </motion.section>
        )}

        {step === 'seats' && (
          <motion.section key="seats" className="mg-panel" initial={{ opacity: 0, scale: 0.96 }} animate={{ opacity: 1, scale: 1 }}>
            <h2 className="section-title">Your Best Seats</h2>
            <p className="sub-glow">RBA spatial engine + accessibility override</p>
            <SeatMap seats={seats} allRows={['A', 'B', 'C', 'D', 'E']} />
            <ul className="seat-picks">
              {seats.map((s) => (
                <li key={s.seat_id} className={s.is_accessible_match ? 'seat-pick accessible' : 'seat-pick'}>
                  <strong>{s.row_label}{s.seat_number}</strong>
                  <span>{s.rba_score} pts</span>
                  <small>{s.reasons.join(' · ')}</small>
                  {s.is_accessible_match && <em>♿ Accessible match</em>}
                </li>
              ))}
            </ul>
            <button type="button" className="neon-btn wide" onClick={() => setStep('done')}>Confirm booking ✦</button>
          </motion.section>
        )}

        {step === 'done' && selectedMovie && pickedTheater && (
          <motion.section key="done" className="mg-panel done-panel" initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }}>
            <div className="confetti-burst">✦</div>
            <h2 className="mega-title small">You're In!</h2>
            <div className="ticket">
              <p>{selectedMovie.title}</p>
              <p>{pickedTheater.name}</p>
              <p>{pickedShowtime?.starts_at} · {seats.map((s) => `${s.row_label}${s.seat_number}`).join(', ')}</p>
            </div>
            <button type="button" className="neon-btn" onClick={() => { setStep('movies'); setSelectedMovie(null); setAnalysis(null); setTheaterResult(null); setSeats([]); }}>Book another</button>
          </motion.section>
        )}
      </AnimatePresence>
    </div>
  );
}
