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

export default function Scoreboard({ users, onSelect }) {
  if (!users.length) {
    return <p style={{ textAlign: 'center', color: '#999' }}>No shamed developers found.</p>
  }

  return (
    <table className="scoreboard-table">
      <thead>
        <tr>
          <th>#</th>
          <th>Name</th>
          <th>Grade</th>
          <th>Sus</th>
          <th>Worst Commit</th>
        </tr>
      </thead>
      <tbody>
        {users.map((user, i) => (
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
                  : 'Pending review...'}
              </div>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}
