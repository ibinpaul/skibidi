import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { fetchOwnerDashboard, formatLabel, type OwnerDashboardResponse } from '../lib/api';

export default function ManagerApp({ onExit }: { onExit: () => void }) {
  const [data, setData] = useState<OwnerDashboardResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchOwnerDashboard()
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : 'Dashboard failed'))
      .finally(() => setLoading(false));
  }, []);

  const maxDemand = Math.max(...(data?.format_demand.map((f) => f.booking_count) ?? [1]), 1);

  return (
    <div className="mgr-shell">
      <header className="mgr-header">
        <button type="button" className="mgr-back" onClick={onExit}>← Portal</button>
        <div>
          <h1>Owner Command</h1>
          <p>Live ops — no ML, direct booking intelligence</p>
        </div>
      </header>

      {error && <div className="mgr-error">{error}</div>}
      {loading && <p className="mgr-loading">Pulling Supabase reporting…</p>}

      {data && (
        <motion.div className="mgr-grid" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
          <section className="mgr-kpi-row">
            <div className="mgr-kpi">
              <span>Total bookings</span>
              <strong>{data.total_bookings.toLocaleString()}</strong>
            </div>
            <div className="mgr-kpi alert">
              <span>Disability assist today</span>
              <strong>{data.disability_bookings_today}</strong>
            </div>
          </section>

          <section className="mgr-card">
            <h2>Format demand</h2>
            <div className="bar-chart">
              {data.format_demand.map((f) => (
                <div key={f.format_name} className="bar-item">
                  <div className="bar-meta">
                    <span>{formatLabel(f.format_name)}</span>
                    <span>{f.share_pct}% · {f.booking_count}</span>
                  </div>
                  <div className="bar-track">
                    <motion.div
                      className="bar-fill"
                      initial={{ width: 0 }}
                      animate={{ width: `${(f.booking_count / maxDemand) * 100}%` }}
                      transition={{ duration: 0.8, ease: 'easeOut' }}
                    />
                  </div>
                </div>
              ))}
            </div>
          </section>

          <section className="mgr-card">
            <h2>Demand heatmap</h2>
            <div className="heatmap">
              {data.area_heatmap.map((area) => (
                <div
                  key={area.area_label}
                  className="heat-cell"
                  style={{ '--heat': area.demand_score } as React.CSSProperties}
                  title={`${area.area_label}: ${Math.round(area.demand_score * 100)}% demand`}
                >
                  <strong>{area.area_label}</strong>
                  <span>{formatLabel(area.top_format)}</span>
                  <em>{Math.round(area.demand_score * 100)}%</em>
                </div>
              ))}
            </div>
          </section>

          <section className="mgr-card wide">
            <h2>Disability assistance feed</h2>
            <ul className="disability-feed">
              {data.disability_feed.map((item) => (
                <li key={item.booking_id}>
                  <div>
                    <strong>{item.cinema_name}</strong>
                    <span>{item.movie_title} · {item.showtime_label}</span>
                  </div>
                  <span className="assist-badge">Assist requested</span>
                </li>
              ))}
            </ul>
          </section>

          <section className="mgr-card wide hint">
            <h2>Profitability lens</h2>
            <p>{data.profitability_hint}</p>
          </section>
        </motion.div>
      )}
    </div>
  );
}
