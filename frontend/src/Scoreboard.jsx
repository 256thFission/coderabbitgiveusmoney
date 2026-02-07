import { useState } from 'react'

// Convert letter grade to number for sorting
const GRADE_ORDER = {
  'A+': 13, 'A': 12, 'A-': 11,
  'B+': 10, 'B': 9,  'B-': 8,
  'C+': 7,  'C': 6,  'C-': 5,
  'D+': 4,  'D': 3,  'D-': 2,
  'F+': 1,  'F': 0,  'F-': -1,
}

function gradeToNum(grade) {
  return GRADE_ORDER[grade] ?? -2
}

function gradeClass(grade) {
  if (!grade) return ''
  const letter = grade.charAt(0).toUpperCase()
  if (letter === 'A') return 'grade-a'
  if (letter === 'B') return 'grade-b'
  if (letter === 'C') return 'grade-c'
  if (letter === 'D') return 'grade-d'
  return 'grade-f'
}

function RoleTag({ role }) {
  if (role === 'judge') return <span className="user-role-tag role-judge">Judge</span>
  if (role === 'organizer') return <span className="user-role-tag role-organizer">Org</span>
  return null
}

const SORT_COLUMNS = {
  stars:    { label: 'Stars',   get: u => u.stars },
  grade:    { label: 'Grade',   get: u => gradeToNum(u.quality_grade) },
  sus:      { label: 'Sus',     get: u => u.sus_score_percentile },
  toxicity: { label: 'Toxicity', get: u => u.worst_commit_toxicity },
}

function SortArrow({ column, sortBy, sortDir }) {
  if (sortBy !== column) return <span className="sort-arrow sort-arrow-inactive"> *</span>
  return <span className="sort-arrow"> {sortDir === 'desc' ? 'v' : '^'}</span>
}

export default function Scoreboard({ users, onSelect }) {
  const [sortBy, setSortBy] = useState(null)
  const [sortDir, setSortDir] = useState('desc')

  if (!users.length) {
    return <p style={{ textAlign: 'center', color: '#999' }}>No shamed developers found.</p>
  }

  function handleSort(col) {
    if (sortBy === col) {
      setSortDir(d => d === 'desc' ? 'asc' : 'desc')
    } else {
      setSortBy(col)
      setSortDir('desc')
    }
  }

  const sorted = sortBy
    ? [...users].sort((a, b) => {
        const av = SORT_COLUMNS[sortBy].get(a)
        const bv = SORT_COLUMNS[sortBy].get(b)
        return sortDir === 'desc' ? bv - av : av - bv
      })
    : users

  return (
    <table className="scoreboard-table">
      <thead>
        <tr>
          <th>#</th>
          <th>Username</th>
          <th>Name</th>
          <th className="sortable-th" onClick={() => handleSort('stars')}>
            Stars<SortArrow column="stars" sortBy={sortBy} sortDir={sortDir} />
          </th>
          <th className="sortable-th" onClick={() => handleSort('grade')}>
            Grade<SortArrow column="grade" sortBy={sortBy} sortDir={sortDir} />
          </th>
          <th className="sortable-th" onClick={() => handleSort('sus')}>
            Sus<SortArrow column="sus" sortBy={sortBy} sortDir={sortDir} />
          </th>
          <th className="sortable-th" onClick={() => handleSort('toxicity')}>
            Toxicity<SortArrow column="toxicity" sortBy={sortBy} sortDir={sortDir} />
          </th>
          <th>Badges</th>
        </tr>
      </thead>
      <tbody>
        {sorted.map((user, i) => {
          const allBadges = [
            ...(user.badges || []),
            ...(user.coderabbit_badge ? [user.coderabbit_badge] : []),
          ]
          return (
            <tr key={user.username} onClick={() => onSelect(user)}>
              <td>{i + 1}</td>
              <td>
                <div className="user-cell">
                  <img
                    className="user-avatar"
                    src={user.avatar_url}
                    alt=""
                    loading="lazy"
                  />
                  <div className="user-info">
                    <span className="user-handle">{user.username}</span>
                    <RoleTag role={user.role} />
                  </div>
                </div>
              </td>
              <td>{user.name || '—'}</td>
              <td>
                <div className="stars-cell">
                  <img src="/doodle/star.svg" alt="" className="star-inline" />
                  <span>{user.stars}</span>
                </div>
              </td>
              <td>
                <span className={`grade ${gradeClass(user.quality_grade)}`}>
                  {user.quality_grade || '...'}
                </span>
              </td>
              <td>
                <div className="sus-bar-container">
                  <div className="sus-bar">
                    <div
                      className="sus-bar-fill"
                      style={{ width: `${user.sus_score_percentile}%` }}
                    />
                  </div>
                  <span className="sus-label">{user.sus_score_percentile}</span>
                </div>
              </td>
              <td>
                <div className="worst-commit">
                  {user.worst_commit_msg
                    ? `"${user.worst_commit_msg}"`
                    : 'Pending...'}
                  <span className="toxicity-tag">
                    {(user.worst_commit_toxicity * 100).toFixed(0)}%
                  </span>
                </div>
              </td>
              <td>
                <div className="badges-tray">
                  {allBadges.length > 0
                    ? allBadges.map(b => (
                        <span
                          key={b}
                          className={`badge-chip ${b === user.coderabbit_badge ? 'badge-chip-ai' : ''}`}
                        >
                          {b}
                        </span>
                      ))
                    : <span className="no-badges">--</span>
                  }
                </div>
              </td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}
