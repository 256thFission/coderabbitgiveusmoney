import { useState, useEffect } from 'react'
import './App.css'
import Scoreboard from './Scoreboard.jsx'
import RoastModal from './RoastModal.jsx'

const FILTERS = ['All', 'Judges', 'Organizers', 'Participants']

function rankScore(user) {
  return (user.stars * user.commits_last_year) / (user.sus_score_percentile + 1)
}

function App() {
  const [data, setData] = useState(null)
  const [filter, setFilter] = useState('All')
  const [selected, setSelected] = useState(null)
  const [toast, setToast] = useState(null)

  useEffect(() => {
    fetch('/data.json')
      .then(res => res.json())
      .then(raw => {
        const ranked = raw
          .map(u => ({ ...u, rank_score: rankScore(u) }))
          .sort((a, b) => b.rank_score - a.rank_score)
        setData(ranked)
      })
  }, [])

  const filterRole = {
    All: null,
    Judges: 'judge',
    Organizers: 'organizer',
    Participants: 'participant',
  }

  const filtered = data
    ? filterRole[filter]
      ? data.filter(u => u.role === filterRole[filter])
      : data
    : []

  function handleRescrape() {
    setToast('Wait your turn. It\'s a static site :p')
    setTimeout(() => setToast(null), 2500)
  }

  if (!data) {
    return <div className="loading">Scribbling the wall...</div>
  }

  return (
    <>
      <header className="app-header">
        <img src="/doodle/star.svg" alt="" className="star-icon" />
        <h1>The Wall of Shame</h1>
        <p className="subtitle">A totally fair and unbiased code review</p>
      </header>

      {/* Filter bar */}
      <div className="filter-bar">
        {FILTERS.map(f => (
          <button
            key={f}
            className={filter === f ? 'active' : ''}
            onClick={() => setFilter(f)}
          >
            {f}
          </button>
        ))}
      </div>

      {/* Main scoreboard */}
      <Scoreboard
        users={filtered}
        onSelect={setSelected}
      />

      <button className="rescrape-btn" onClick={handleRescrape}>
        Re-Scrape
      </button>

      {/* Detail modal */}
      {selected && (
        <RoastModal
          user={selected}
          onClose={() => setSelected(null)}
        />
      )}

      {/* Toast */}
      {toast && <div className="toast">{toast}</div>}
    </>
  )
}

export default App
