import { useState, useEffect } from "react"
import TourManager from "./TourManager"   
import "./App.css"

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
    if (res.ok) onConfirmed(data.user, data.room, data.rank)
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
function Dashboard({ user, room, onLogout, onNavigate }) {  // ← ADD onNavigate prop
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
            <button className="logout-btn" onClick={() => onNavigate("tours")}>manage tours</button>
            <span className="sep">·</span>
            <button className="logout-btn" onClick={handleLogout}>logout</button>
          </div>
        </div>

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
  const [rank,  setRank]  = useState(null) 
  useEffect(() => {
    fetch("/me", { credentials: "include" }).then(r => r.json()).then(data => {
      if (data.authenticated) {
        setUser(data.user); setRoom(data.room); setRank(data.rank ?? "+"); setState("dashboard")
      } else if (data.pending || window.location.pathname === "/confirm") {
        setState("confirm")
      } else {
        setState("unauthed")
      }
    })
  }, [])

  const handleConfirmed = (u, r, k) => { setUser(u); setRoom(r); setRank(k); setState("dashboard") }
  const handleLogout = () => { setUser(null); setRoom(null); setRank(null); setState("unauthed") }

  if (state === "loading") return (
    <><style>{css}</style><div className="loading">loading...</div></>
  )

  if (state === "confirm") return <ConfirmPage onConfirmed={handleConfirmed} />

  if (state === "dashboard") return (
    <Dashboard user={user} room={room} onLogout={handleLogout} onNavigate={setState} />
  )

  if (state === "tours") return (
    <TourManager user={user} room={room} rank={rank} onBack={() => setState("dashboard")} />
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
          All login links expires in 10 minutes and can only be used once.
          if you need to switch rooms, log out first then request a new link from the correct room.
        </div>
      </div>
    </div>
  )
}