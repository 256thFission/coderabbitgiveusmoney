import { useEffect } from 'react'

function toxicityLevel(score) {
  if (score < 0.2) return 'toxicity-low'
  if (score < 0.5) return 'toxicity-mid'
  return 'toxicity-high'
}

export default function RoastModal({ user, onClose }) {
  // Close on Escape
  useEffect(() => {
    function handleKey(e) {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  }, [onClose])

  const allBadges = [
    ...(user.badges || []),
    ...(user.coderabbit_badge ? [user.coderabbit_badge] : []),
  ]

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={e => e.stopPropagation()}>
        <button className="modal-close" onClick={onClose}>x</button>

        {/* User header */}
        <div className="modal-user-header">
          <img
            className="modal-avatar"
            src={user.avatar_url}
            alt=""
          />
          <div className="modal-user-meta">
            <h2>{user.name || user.username}</h2>
            <p>
              <a
                href={`https://github.com/${user.username}`}
                target="_blank"
                rel="noopener noreferrer"
              >
                @{user.username}
              </a>
            </p>
            {user.bio && <p>{user.bio}</p>}
          </div>
        </div>

        {/* The Verdict */}
        {user.verdict ? (
          <div className="verdict-section">
            <span className="verdict-label">THE VERDICT (by Linus)</span>
            <p>"{user.verdict}"</p>
          </div>
        ) : (
          <div className="verdict-section">
            <span className="verdict-label">THE VERDICT</span>
            <p>Pending review...</p>
          </div>
        )}

        {/* Badges */}
        {allBadges.length > 0 && (
          <div className="badges-row">
            {user.badges.map(b => (
              <span key={b} className="badge-tag">{b}</span>
            ))}
            {user.coderabbit_badge && (
              <span className="badge-tag ai-badge">{user.coderabbit_badge}</span>
            )}
          </div>
        )}

        {/* Stats grid */}
        <div className="stats-grid">
          <div className="stat-box">
            <span className="stat-value">{user.stars}</span>
            <span className="stat-label">Total Stars</span>
          </div>
          <div className="stat-box">
            <span className="stat-value">{user.commits_last_year}</span>
            <span className="stat-label">Commits (Year)</span>
          </div>
          <div className="stat-box">
            <span className="stat-value">{user.quality_grade || '...'}</span>
            <span className="stat-label">Quality Grade</span>
          </div>
          <div className="stat-box">
            <span className="stat-value">{user.top_repo?.language || '?'}</span>
            <span className="stat-label">Top Repo Language</span>
          </div>
        </div>

        {/* Top Repo */}
        {user.top_repo && (
          <p style={{ fontSize: '0.85em', color: '#666' }}>
            Top repo: <strong>{user.top_repo.name}</strong> ({user.top_repo.stars} stars)
            {user.top_repo.description && ` — ${user.top_repo.description}`}
          </p>
        )}

        {/* Toxicity Meter */}
        <div className="toxicity-section">
          <h4>Toxicity Meter (worst commit)</h4>
          <div className="toxicity-bar">
            <div
              className={`toxicity-bar-fill ${toxicityLevel(user.worst_commit_toxicity)}`}
              style={{ width: `${Math.min(user.worst_commit_toxicity * 100, 100)}%` }}
            />
          </div>
          <div className="toxicity-commit">
            {user.worst_commit_msg
              ? `"${user.worst_commit_msg}"`
              : 'No commit data'}
          </div>
        </div>
      </div>
    </div>
  )
}
