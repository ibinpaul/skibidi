import { useState } from 'react';
import { motion } from 'framer-motion';
import MoviegoerApp from './modes/MoviegoerApp';
import ManagerApp from './modes/ManagerApp';

type Mode = 'portal' | 'moviegoer' | 'manager';

export default function App() {
  const [mode, setMode] = useState<Mode>('portal');

  if (mode === 'moviegoer') {
    return <MoviegoerApp onExit={() => setMode('portal')} />;
  }

  if (mode === 'manager') {
    return <ManagerApp onExit={() => setMode('portal')} />;
  }

  return (
    <div className="portal-shell">
      <div className="portal-stars" />
      <div className="portal-glow portal-glow-a" />
      <div className="portal-glow portal-glow-b" />

      <motion.div className="portal-content" initial={{ opacity: 0, y: 24 }} animate={{ opacity: 1, y: 0 }}>
        <p className="portal-eyebrow">XILO V6</p>
        <h1 className="portal-title">
          Cinema<br />
          <span>Reimagined</span>
        </h1>
        <p className="portal-sub">Two worlds. One platform. Pick your path.</p>

        <div className="portal-doors">
          <motion.button
            type="button"
            className="portal-door moviegoer"
            whileHover={{ scale: 1.03, rotate: -1 }}
            whileTap={{ scale: 0.98 }}
            onClick={() => setMode('moviegoer')}
          >
            <span className="door-icon">🎬</span>
            <strong>I'm Watching</strong>
            <small>Scraper → ML theaters → RBA seats</small>
            <span className="door-shine" />
          </motion.button>

          <motion.button
            type="button"
            className="portal-door manager"
            whileHover={{ scale: 1.03, rotate: 1 }}
            whileTap={{ scale: 0.98 }}
            onClick={() => setMode('manager')}
          >
            <span className="door-icon">📊</span>
            <strong>I Run a Theater</strong>
            <small>Heatmaps · disability ops · format demand</small>
            <span className="door-shine" />
          </motion.button>
        </div>
      </motion.div>
    </div>
  );
}
