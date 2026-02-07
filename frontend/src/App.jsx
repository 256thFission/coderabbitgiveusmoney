import { useState, useEffect } from 'react'
import './App.css'
import Scoreboard from './Scoreboard.jsx'
import RoastModal from './RoastModal.jsx'

function rankScore(user) {
  return (user.stars * user.commits_last_year) / (user.sus_score_percentile + 1)
}

function App() {
  const [data, setData] = useState(null)
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

      <p className="made-with-love">Made with love and spite by Phillip, Zackery and Hummam</p>

      {/* Main scoreboard */}
      <Scoreboard
        users={data}
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
