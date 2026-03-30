import { useState, useEffect } from "react"

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
const HOURS = Array.from({ length: 24 }, (_, i) => i)

function formatHour(h) {
  const ampm = h < 12 ? "AM" : "PM"
  const display = h % 12 || 12
  return `${display}:00 ${ampm}`
}

function slotsToGrid(slots) {
  const grid = { 1: {}, 2: {} }
  for (let w = 1; w <= 2; w++)
    for (let d = 0; d < 7; d++) {
      grid[w][d] = {}
      for (let h = 0; h < 24; h++) grid[w][d][h] = ""
    }
  for (const s of slots) grid[s.week][s.day][s.hour] = s.tour_internalname
  return grid
}

function gridToSlots(grid, isTwoWeek) {
  const slots = []
  const weeks = isTwoWeek ? [1, 2] : [1]
  for (const w of weeks)
    for (let d = 0; d < 7; d++)
      for (let h = 0; h < 24; h++)
        if (grid[w][d][h]) slots.push({ week: w, day: d, hour: h, tour_internalname: grid[w][d][h] })
  return slots
}

const css = `
  @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&display=swap');

  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  :root {
    --bg:           #f0f4ff;
    --surface:      #ffffff;
    --surface2:     #e8edf8;
    --border:       #c8d0e8;
    --border2:      #b0bcd8;
    --text:         #0f1a3a;
    --text-muted:   #5a6888;
    --text-dim:     #a0aac8;
    --accent:       #2355d4;
    --accent-soft:  rgba(35,85,212,0.07);
    --accent-mid:   rgba(35,85,212,0.18);
    --cell-filled:  rgba(35,85,212,0.06);
    --cell-filled-h:rgba(35,85,212,0.12);
    --shadow:       0 1px 4px rgba(35,85,212,0.07), 0 4px 16px rgba(35,85,212,0.04);
    --shadow-lg:    0 2px 12px rgba(35,85,212,0.1), 0 12px 40px rgba(35,85,212,0.06);
  }

  @media (prefers-color-scheme: dark) {
    :root {
      --bg:           #080d1a;
      --surface:      #0e1525;
      --surface2:     #141d30;
      --border:       #1e2d4a;
      --border2:      #2a3d60;
      --text:         #dce8ff;
      --text-muted:   #6878a8;
      --text-dim:     #2a3a58;
      --accent:       #4d7fff;
      --accent-soft:  rgba(77,127,255,0.08);
      --accent-mid:   rgba(77,127,255,0.2);
      --cell-filled:  rgba(77,127,255,0.07);
      --cell-filled-h:rgba(77,127,255,0.14);
      --shadow:       0 1px 4px rgba(0,0,0,0.3), 0 4px 16px rgba(0,0,0,0.2);
      --shadow-lg:    0 2px 12px rgba(0,0,0,0.4), 0 12px 40px rgba(0,0,0,0.3);
    }
  }

  /* mobile layout for toggle */
  @media (max-width: 600px) {
    .toggle-container {
        width: 100%;
        margin-left: 0;
        margin-top: 6px;
    }
  }

  body {
    background: var(--bg);
    color: var(--text);
    font-family: 'IBM Plex Mono', monospace;
    font-size: 12px;
    min-height: 100vh;
  }

  .app {
    max-width: 1400px;
    margin: 0 auto;
    padding: 28px 20px 80px;
  }

  /* Navbar */
  .navbar {
    position: sticky;
    top: 0;
    z-index: 10;
    background: var(--surface);
    border-bottom: 1px solid var(--border);
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 20px;
    height: 44px;
    box-shadow: var(--shadow);
    flex-wrap: wrap;   
    gap: 8px;
  }

  .navbar-left {
    display: flex;
    align-items: center;
    gap: 16px;
    min-width: 0;
  }

  .navbar-title {
    font-size: 13px;
    font-weight: 600;
    color: var(--text);
    white-space: nowrap;
    flex-shrink: 0;
  }

  .navbar-title span { color: var(--accent); }

  .navbar-divider {
    width: 1px;
    height: 16px;
    background: var(--border2);
    flex-shrink: 0;
  }

  .navbar-user {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 11px;
    color: var(--text-muted);
    min-width: 0;
  }

  .room-tag {
    background: var(--accent-soft);
    border: 1px solid var(--accent-mid);
    color: var(--accent);
    padding: 1px 7px;
    border-radius: 3px;
    font-size: 10px;
    letter-spacing: 0.5px;
    white-space: nowrap;
    flex-shrink: 0;
  }

  .sep { color: var(--border2); flex-shrink: 0; }

  .logout-btn {
    background: none;
    border: 1px solid var(--border2);
    color: var(--text-muted);
    cursor: pointer;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 10px;
    padding: 2px 8px;
    border-radius: 3px;
    transition: all 0.15s;
    white-space: nowrap;
    flex-shrink: 0;
  }

  .logout-btn:hover {
    border-color: var(--accent);
    color: var(--accent);
    background: var(--accent-soft);
  }

  /* Week toggle */
  .toggle-wrap {
    display: flex;
    align-items: center;
    gap: 10px;
    font-size: 11px;
    color: var(--text-muted);
    cursor: pointer;
    user-select: none;
  }

  .toggle {
    position: relative;
    width: 34px;
    height: 18px;
    flex-shrink: 0;
  }

  .toggle input { display: none; }

  .toggle-track {
    position: absolute;
    inset: 0;
    background: var(--border2);
    border-radius: 999px;
    transition: background 0.2s;
  }

  .toggle input:checked + .toggle-track { background: var(--accent); }

  .toggle-thumb {
    position: absolute;
    top: 2px; left: 2px;
    width: 14px; height: 14px;
    background: white;
    border-radius: 50%;
    transition: transform 0.2s;
    pointer-events: none;
  }
  
  .toggle-container {
    margin-left: auto;
  }
  .toggle input:checked ~ .toggle-thumb { transform: translateX(16px); }

  /* Week label */
  .week-label {
    font-size: 10px;
    letter-spacing: 2px;
    text-transform: uppercase;
    color: var(--text-muted);
    margin-bottom: 8px;
  }

  .week-label b { color: var(--accent); font-weight: 600; }

  /* Grid */
  .grid-wrap {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 6px;
    overflow: hidden;
    margin-bottom: 16px;
    box-shadow: var(--shadow);
  }

  .grid-scroll {
    overflow-x: auto;
    overflow-y: auto;
    max-height: 540px;
  }

  .grid {
    display: grid;
    grid-template-columns: 68px repeat(7, minmax(96px, 1fr));
    min-width: 750px;
  }

  .grid-corner {
    background: var(--surface2);
    border-bottom: 1px solid var(--border);
    border-right: 1px solid var(--border);
    position: sticky; top: 0; left: 0;
    z-index: 3;
  }

  .grid-day {
    background: var(--surface2);
    border-bottom: 1px solid var(--border);
    border-right: 1px solid var(--border);
    padding: 9px 4px;
    text-align: center;
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 1.5px;
    text-transform: uppercase;
    color: var(--text-muted);
    position: sticky; top: 0;
    z-index: 2;
  }

  .grid-day:last-child { border-right: none; }

  .grid-time {
    background: var(--surface2);
    border-right: 1px solid var(--border);
    border-bottom: 1px solid var(--border);
    padding: 0 8px;
    display: flex;
    align-items: center;
    justify-content: flex-end;
    font-size: 9px;
    color: var(--text-dim);
    position: sticky; left: 0;
    z-index: 1;
    min-height: 32px;
    white-space: nowrap;
  }

  .grid-cell {
    border-right: 1px solid var(--border);
    border-bottom: 1px solid var(--border);
    min-height: 32px;
    display: flex;
    align-items: center;
    padding: 2px 4px;
    transition: background 0.1s;
  }

  .grid-cell:last-child { border-right: none; }
  .grid-cell:hover { background: var(--surface2); }
  .grid-cell.filled { background: var(--cell-filled); }
  .grid-cell.filled:hover { background: var(--cell-filled-h); }

  .grid-cell select {
    width: 100%;
    background: transparent;
    border: none;
    color: var(--text-dim);
    font-family: 'IBM Plex Mono', monospace;
    font-size: 11px;
    cursor: pointer;
    outline: none;
    appearance: none;
    -webkit-appearance: none;
    padding: 2px 0;
  }

  .grid-cell.filled select { color: var(--accent); }
  .grid-cell select:focus { color: var(--text); }
  .grid-cell select option { background: var(--surface); color: var(--text); }

  /* Actions */
  .actions {
    display: flex;
    gap: 8px;
    justify-content: flex-end;
  }

  .btn {
    padding: 7px 16px;
    border-radius: 4px;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 11px;
    font-weight: 500;
    cursor: pointer;
    border: none;
    transition: all 0.15s;
    letter-spacing: 0.2px;
  }

  .btn-primary {
    background: var(--accent);
    color: white;
  }

  .btn-primary:hover { opacity: 0.88; transform: translateY(-1px); }
  .btn-primary:disabled { opacity: 0.4; cursor: not-allowed; transform: none; }

  .btn-ghost {
    background: transparent;
    color: var(--text-muted);
    border: 1px solid var(--border2);
  }

  .btn-ghost:hover { background: var(--surface2); color: var(--text); }

  /* Toast */
  .toast {
    position: fixed;
    bottom: 20px; right: 20px;
    padding: 9px 16px;
    border-radius: 4px;
    font-size: 11px;
    font-weight: 500;
    animation: slideUp 0.2s ease;
    z-index: 100;
    box-shadow: var(--shadow-lg);
  }

  .toast.success { background: var(--accent); color: white; }
  .toast.error   { background: #d32f2f; color: white; }

  /* Center pages */
  .center-page {
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
    background: var(--bg);
  }

  .card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 40px;
    width: 100%;
    max-width: 400px;
    box-shadow: var(--shadow-lg);
  }

  .card h1 {
    font-size: 16px;
    font-weight: 600;
    color: var(--text);
    margin-bottom: 6px;
  }

  .card h1 span { color: var(--accent); }

  .card p {
    font-size: 11px;
    color: var(--text-muted);
    margin-bottom: 24px;
    line-height: 1.7;
  }

  .card code {
    background: var(--accent-soft);
    border: 1px solid var(--accent-mid);
    color: var(--accent);
    padding: 1px 5px;
    border-radius: 3px;
    font-family: 'IBM Plex Mono', monospace;
  }

  .card .note {
    margin-top: 16px;
    padding: 10px 12px;
    background: var(--accent-soft);
    border: 1px solid var(--accent-mid);
    border-radius: 4px;
    font-size: 10px;
    color: var(--text-muted);
    line-height: 1.6;
  }

  .input {
    width: 100%;
    background: var(--surface2);
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 9px 11px;
    color: var(--text);
    font-family: 'IBM Plex Mono', monospace;
    font-size: 12px;
    outline: none;
    margin-bottom: 10px;
    transition: border-color 0.15s;
  }

  .input:focus { border-color: var(--accent); }
  .err { font-size: 11px; color: #d32f2f; margin-bottom: 10px; }

  .loading {
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--text-muted);
    font-size: 11px;
    letter-spacing: 1px;
    background: var(--bg);
  }

  @keyframes slideUp {
    from { opacity: 0; transform: translateY(6px); }
    to   { opacity: 1; transform: translateY(0); }
  }

  @keyframes fadeIn {
    from { opacity: 0; transform: translateY(4px); }
    to   { opacity: 1; transform: translateY(0); }
  }

  .fade-in { animation: fadeIn 0.25s ease; }

  ::-webkit-scrollbar { width: 5px; height: 5px; }
  ::-webkit-scrollbar-track { background: transparent; }
  ::-webkit-scrollbar-thumb { background: var(--border2); border-radius: 999px; }
`

// --- Confirm page ---
function ConfirmPage({ onConfirmed }) {
  const [username, setUsername] = useState("")
  const [error, setError]       = useState("")
  const [loading, setLoading]   = useState(false)

  const handleConfirm = async () => {
    setLoading(true); setError("")
    const res  = await fetch("/confirm", {
      method: "POST", credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username }),
    })
    const data = await res.json()
    setLoading(false)
    if (res.ok) onConfirmed(data.user, data.room)
    else setError(data.error || "Username mismatch, please use the exact same capitalization as your PS username meow ;w;.")
  }

  return (
    <div className="center-page">
      <style>{css}</style>
      <div className="card">
        <h1>Confirm Identity</h1>
        <p>type your pokémon showdown username to verify it's you.</p>
        <input className="input" value={username}
          onChange={e => setUsername(e.target.value)}
          onKeyDown={e => e.key === "Enter" && handleConfirm()}
          placeholder="your PS username"
          autoComplete="off" autoFocus />
        {error && <p className="err">{error}</p>}
        <button className="btn btn-primary" style={{ width: "100%" }}
          onClick={handleConfirm} disabled={loading}>
          {loading ? "checking..." : "confirm →"}
        </button>
      </div>
    </div>
  )
}

// --- Schedule grid ---
function ScheduleGrid({ grid, week, onChange, tours }) {
  return (
    <div className="grid-wrap">
      <div className="grid-scroll">
        <div className="grid">
          <div className="grid-corner" />
          {DAYS.map(d => <div key={d} className="grid-day">{d}</div>)}
          {HOURS.map(hour => (
            <>
              <div key={`t${hour}`} className="grid-time">{formatHour(hour)}</div>
              {Array.from({ length: 7 }, (_, day) => {
                const val = grid[week][day][hour] || ""
                return (
                  <div key={`${day}-${hour}`} className={`grid-cell${val ? " filled" : ""}`}>
                    <select value={val} onChange={e => onChange(week, day, hour, e.target.value)}>
                      <option value="">—</option>
                      {tours.map(t => (
                        <option key={t.tour_internalname} value={t.tour_internalname}>
                          {t.tour_internalname}
                        </option>
                      ))}
                    </select>
                  </div>
                )
              })}
            </>
          ))}
        </div>
      </div>
    </div>
  )
}

// --- Dashboard ---
function Dashboard({ user, room, onLogout }) {
  const [tours,     setTours]     = useState([])
  const [grid,      setGrid]      = useState(slotsToGrid([]))
  const [isTwoWeek, setIsTwoWeek] = useState(false)
  const [saving,    setSaving]    = useState(false)
  const [toast,     setToast]     = useState(null)

  useEffect(() => {
    Promise.all([
      fetch("/api/tours",    { credentials: "include" }).then(r => r.json()),
      fetch("/api/schedule", { credentials: "include" }).then(r => r.json()),
    ]).then(([toursData, slots]) => {
      setTours(toursData)
      setGrid(slotsToGrid(slots))
      setIsTwoWeek(slots.some(s => s.week === 2))
    })
  }, [])

  const showToast = (msg, type = "success") => {
    setToast({ msg, type })
    setTimeout(() => setToast(null), 2500)
  }

  const handleChange = (week, day, hour, value) => {
    setGrid(prev => ({
      ...prev,
      [week]: { ...prev[week], [day]: { ...prev[week][day], [hour]: value } }
    }))
  }

  const handleSave = async () => {
    setSaving(true)
    const slots = gridToSlots(grid, isTwoWeek)
    const res   = await fetch("/api/schedule", {
      method: "POST", credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(slots),
    })
    const data = await res.json()
    setSaving(false)
    if (res.status === 401) {
      showToast("session expired — log in again.", "error")
      setTimeout(() => onLogout(), 2000)
    } else if (!res.ok) {
      showToast(data.error || "save failed.", "error")
    } else {
      showToast("saved.")
    }
  }

  const handleLogout = async () => {
    await fetch("/logout", { method: "POST", credentials: "include" })
    onLogout()
  }

  return (
    <div>
      <style>{css}</style>
      <nav className="navbar">
        <div className="navbar-left">
          <span className="navbar-title"><span>tour scheduler</span></span>
          <div className="navbar-divider" />
          <div className="navbar-user">
            <span>{user}</span>
            <span className="room-tag">{room}</span>
            <span className="sep">·</span>
            <button className="logout-btn" onClick={handleLogout}>logout</button>
          </div>
        </div>

        {/* Move toggle outside of navbar-left so it can go below on mobile */}
        <div className="toggle-container">
          <label className="toggle-wrap">
            2-week schedule
            <label className="toggle">
              <input type="checkbox" checked={isTwoWeek}
                onChange={e => setIsTwoWeek(e.target.checked)} />
              <div className="toggle-track" />
              <div className="toggle-thumb" />
            </label>
          </label>
        </div>
      </nav>
      <div className="app">

      <div className="week-label">week <b>A</b></div>
      <ScheduleGrid grid={grid} week={1} onChange={handleChange} tours={tours} />

      {isTwoWeek && (
        <div className="fade-in">
          <div className="week-label">week <b>B</b></div>
          <ScheduleGrid grid={grid} week={2} onChange={handleChange} tours={tours} />
        </div>
      )}

      <div className="actions">
        <button className="btn btn-ghost" onClick={() => setGrid(slotsToGrid([]))}>
          clear all
        </button>
        <button className="btn btn-primary" onClick={handleSave} disabled={saving}>
          {saving ? "saving..." : "save schedule"}
        </button>
      </div>

      {toast && <div className={`toast ${toast.type}`}>{toast.msg}</div>}
    </div>
    </div>
  )
}

// --- App router ---
export default function App() {
  const [state, setState] = useState("loading")
  const [user,  setUser]  = useState(null)
  const [room,  setRoom]  = useState(null)

  useEffect(() => {
    fetch("/me", { credentials: "include" }).then(r => r.json()).then(data => {
      if (data.authenticated) {
        setUser(data.user); setRoom(data.room); setState("dashboard")
      } else if (data.pending || window.location.pathname === "/confirm") {
        setState("confirm")
      } else {
        setState("unauthed")
      }
    })
  }, [])

  const handleConfirmed = (u, r) => { setUser(u); setRoom(r); setState("dashboard") }
  const handleLogout    = ()     => { setUser(null); setRoom(null); setState("unauthed") }

  if (state === "loading") return (
    <><style>{css}</style><div className="loading">loading...</div></>
  )

  if (state === "confirm") return <ConfirmPage onConfirmed={handleConfirmed} />

  if (state === "dashboard") return (
    <Dashboard user={user} room={room} onLogout={handleLogout} />
  )

  return (
    <div className="center-page">
      <style>{css}</style>
      <div className="card">
        <h1>Meow Schedule Editor</h1>
        <p>
          type <code>Meow edit schedule</code> in your room's chat to get a login link.
        </p>
        <div className="note">
          ⓘ each login link expires in 10 minutes and can only be used once.
          if you need to switch rooms, log out first then request a new link from the correct room.
        </div>
      </div>
    </div>
  )
}