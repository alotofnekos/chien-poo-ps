import { useState, useEffect, useRef } from "react"
import meowLogo from "./assets/meow-logo-temp.png"
import "./App.css"

// ─── Tour type options ────────────────────────────────────────────────────────
const TOUR_TYPES = [
  // gen 9
  "gen9monotype", "gen9monotyperandombattle", "gen9ou", "gen9uu", "gen9ru", "gen9nu", "gen9pu",
  "gen9nationaldex", "gen9nationaldexmonotype",
  "gen9randombattle", "gen9doublesou", "gen9doublesuu",
  // gen 8
  "gen8monotype", "gen8ou", "gen8randombattle", "gen8nationaldex",
  // gen 7
  "gen7monotype", "gen7ou", "gen7randombattle", 
  // gen 6
  "gen6monotype", "gen6ou", "gen6randombattle",
  // gen 5 and below
  "gen5monotype", "gen5ou", "gen4ou", "gen3ou", "gen2ou", "gen1ou",
]

const EXCLUDED_OFFICIAL = ["National Dex OU", "Monotype Cats"]

// ─── Helpers ─────────────────────────────────────────────────────────────────
function buildPreviewLines(tour) {
  const { internalname, type, name, clauses, bans, unbans, misc } = tour
  if (!type || !name) return []

  const lines = []
  lines.push({ cls: "preview-line-cmd", text: `/tour new ${type}, elim,,,${name}` })
  misc.forEach(m => lines.push({ cls: "preview-line-misc", text: m }))

  const ruleParts = [
    ...clauses,
    ...bans.map(b => `-${b}`),
    ...unbans.map(u => `+${u}`),
  ]
  if (ruleParts.length)
    lines.push({ cls: "preview-line-rule", text: `/tour rules ${ruleParts.join(", ")}` })

  const isExcluded = EXCLUDED_OFFICIAL.some(x => name.includes(x))
  if (!isExcluded) lines.push({ cls: "preview-line-official", text: ".official" })

  return lines
}

function emptyTour() {
  return { internalname: "", type: "", name: "", clauses: [], bans: [], unbans: [], misc: [] }
}

// ─── TagInput ─────────────────────────────────────────────────────────────────
function TagInput({ tags, onAdd, onRemove, placeholder, tagClass }) {
  const [val, setVal] = useState("")
  const inputRef = useRef()

  const commit = () => {
    const items = val.split(",").map(s => s.trim()).filter(Boolean)
    items.forEach(onAdd)
    setVal("")
  }

  return (
    <div className="tag-area" onClick={() => inputRef.current?.focus()}>
      {tags.map(t => (
        <span key={t} className={`tag ${tagClass}`}>
          {t}
          <button className="tag-remove" onClick={e => { e.stopPropagation(); onRemove(t) }}>×</button>
        </span>
      ))}
      <input
        ref={inputRef}
        className="tag-input"
        value={val}
        placeholder={tags.length === 0 ? placeholder : ""}
        onChange={e => setVal(e.target.value)}
        onKeyDown={e => {
          if (e.key === "Enter" || e.key === ",") { e.preventDefault(); commit() }
          if (e.key === "Backspace" && !val && tags.length) onRemove(tags[tags.length - 1])
        }}
        onBlur={commit}
      />
    </div>
  )
}

// ─── TourEditor ───────────────────────────────────────────────────────────────
function TourEditor({ tour: initial, isNew, onSave, onDelete, saving, user, room, isOwner }) {
  const [tour, setTour] = useState(initial)

  useEffect(() => setTour(initial), [initial])

  const set = (key, val) => setTour(t => ({ ...t, [key]: val }))
  const addTag = (key, val) => setTour(t => ({ ...t, [key]: [...new Set([...t[key], val])] }))
  const removeTag = (key, val) => setTour(t => ({ ...t, [key]: t[key].filter(x => x !== val) }))

  const previewLines = buildPreviewLines(tour)
  const dirty = JSON.stringify(tour) !== JSON.stringify(initial)

  return (
    <div className="editor-panel fade-in">
      <div className="editor-header">
        <div className="editor-title">
          {isNew ? <><span>new</span> tour</> : <><span>{tour.internalname}</span></>}
        </div>
        <div className="editor-actions">
          {!isNew && isOwner && (
            <button className="btn btn-ghost btn-sm"
              onClick={() => setTour(initial)} disabled={!dirty}>
              reset
            </button>
          )}
          <button className="btn btn-primary btn-sm"
            onClick={() => onSave(tour)} disabled={saving || !tour.internalname || !tour.type || !tour.name}>
            {saving ? "saving..." : isNew ? "create tour →" : "save changes"}
          </button>
        </div>
      </div>

      {/* Basic info */}
      <div className="section">
        <div className="section-title">basic info</div>
        <div className="field-row">
          <div className="field">
            <div className="field-label">internal name <span className="required">*</span></div>
            <input className="field-input" value={tour.internalname}
              onChange={e => set("internalname", e.target.value.toLowerCase().replace(/\s+/g, ""))}
              placeholder="e.g. monocats"
              disabled={!isNew} style={!isNew ? { opacity: 0.5 } : {}}
            />
          </div>
          <div className="field">
            <div className="field-label">display name <span className="required">*</span></div>
            <input className="field-input" value={tour.name}
              onChange={e => set("name", e.target.value)}
              placeholder="e.g. Monotype Cats"
              disabled={!isNew} style={!isNew ? { opacity: 0.5 } : {}}
            />
          </div>
        </div>
        <div className="field">
        <div className="field-label">format / tour type <span className="required">*</span></div>
        <input
            className="field-input"
            list="tour-types-list"
            value={tour.type}
            onChange={e => set("type", e.target.value)}
            placeholder="e.g. gen9monotype"
            disabled={!isNew}
            style={!isNew ? { opacity: 0.5 } : {}}
        />
        <datalist id="tour-types-list">
            {TOUR_TYPES.map(t => <option key={t} value={t} />)}
        </datalist>
        </div>
        {!isNew && (
          <div style={{ fontSize: 10, color: "var(--text-dim)", marginTop: 6 }}>
            Take note: internal name, display name, and format cannot be changed after creation.
          </div>
        )}
      </div>

      {/* Ruleset */}
      <div className="section">
        <div className="section-title">ruleset</div>
        <div className="field">
          <div className="field-label">clauses — press <kbd>Enter</kbd> or <kbd>,</kbd> to add</div>
          <TagInput tags={tour.clauses} tagClass="tag-clause"
            placeholder="Sleep Clause Mod, Evasion Clause…"
            onAdd={v => addTag("clauses", v)} onRemove={v => removeTag("clauses", v)} />
        </div>
        <div className="field">
          <div className="field-label">bans (will be prefixed with <code>-</code>)</div>
          <TagInput tags={tour.bans} tagClass="tag-ban"
            placeholder="Flutter Mane, Shadow Tag…"
            onAdd={v => addTag("bans", v)} onRemove={v => removeTag("bans", v)} />
        </div>
        <div className="field">
          <div className="field-label">unbans (will be prefixed with <code>+</code>)</div>
          <TagInput tags={tour.unbans} tagClass="tag-unban"
            placeholder="Chien-Pao, Booster Energy…"
            onAdd={v => addTag("unbans", v)} onRemove={v => removeTag("unbans", v)} />
        </div>
      </div>

      {/* Misc commands */}
      <div className="section">
        <div className="section-title">misc commands</div>
        <div className="field">
          <div className="field-label">extra PS commands to run after creating the tour</div>
          <TagInput tags={tour.misc} tagClass="tag-misc"
            placeholder="/tour autostart 6, /tour autodq 2…"
            onAdd={v => addTag("misc", v)} onRemove={v => removeTag("misc", v)} />
        </div>
      </div>

      {/* Preview */}
      <div className="section">
        <div className="section-title">preview</div>
        {previewLines.length === 0
          ? <div style={{ color: "var(--text-dim)", fontSize: 11 }}>fill in the required fields to see a preview.</div>
          : <div className="preview-box">
              {previewLines.map((l, i) => (
                <div key={i} className={l.cls}>{l.text}</div>
              ))}
            </div>
        }
      </div>

      {/* Danger zone — only for existing tours */}
      {!isNew && (
        <div className="danger-section">
          <div className="danger-title">Danger Area!</div>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 8 }}>
            <span style={{ fontSize: 11, color: "var(--text-muted)" }}>
              permanently remove <b>{tour.internalname}</b> and all its bans / schedule slots.
            </span>
            <button className="btn btn-danger btn-sm" onClick={() => onDelete(tour.internalname)}>
              delete tour
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

// ─── ConfirmModal ─────────────────────────────────────────────────────────────
function ConfirmModal({ message, onConfirm, onCancel }) {
  return (
    <div className="modal-backdrop">
      <div className="modal">
        <h3>Are you sure?</h3>
        <p>{message}</p>
        <div className="modal-actions">
          <button className="btn btn-ghost btn-sm" onClick={onCancel}>cancel</button>
          <button className="btn btn-danger btn-sm" onClick={onConfirm}>yes, delete</button>
        </div>
      </div>
    </div>
  )
}

// ─── TourManager (main export) ────────────────────────────────────────────────
export default function TourManager({ user, room, rank, onBack }) {
  const [tours,    setTours]    = useState([])     // { tour_internalname, tour_type, tour_name }
  const [selected, setSelected] = useState(null)   // internalname | "__new__"
  const [detail,   setDetail]   = useState(null)   // full tour object
  const [saving,   setSaving]   = useState(false)
  const [toast,    setToast]    = useState(null)
  const [confirm,  setConfirm]  = useState(null)   // { message, action }
  const [search,   setSearch]   = useState("")

  const showToast = (msg, type = "success") => {
    setToast({ msg, type }); setTimeout(() => setToast(null), 2500)
  }

  // ── fetch tour list ──
  const loadTours = async () => {
    const res  = await fetch("/api/tours", { credentials: "include" })
    const data = await res.json()
    setTours(data)
    return data
  }

  // ── fetch single tour detail ──
  const loadDetail = async (internalname) => {
    const [infoRes, bansRes] = await Promise.all([
      fetch(`/api/tour/${internalname}`,      { credentials: "include" }),
      fetch(`/api/tour/${internalname}/bans`, { credentials: "include" }),
    ])
    const info = await infoRes.json()
    const bans = await bansRes.json()  // array of { ban } strings

    const clauseItems = [], banItems = [], unbanItems = []
    for (const b of bans) {
      if (b.ban.startsWith("-"))      banItems.push(b.ban.slice(1))
      else if (b.ban.startsWith("+")) unbanItems.push(b.ban.slice(1))
      else                             clauseItems.push(b.ban)
    }

    setDetail({
      internalname,
      type:    info.tour_type    || "",
      name:    info.tour_name    || "",
      clauses: clauseItems,
      bans:    banItems,
      unbans:  unbanItems,
      misc:    Array.isArray(info.misc_commands) ? info.misc_commands : [],
    })
  }

  useEffect(() => { loadTours() }, [])

  const handleSelect = async (internalname) => {
    setSelected(internalname)
    if (internalname === "__new__") {
      setDetail(emptyTour())
    } else {
      setDetail(null)
      await loadDetail(internalname)
    }
  }

  // ── save ──
  const handleSave = async (tour) => {
    setSaving(true)
    const isNew = selected === "__new__"
    const endpoint = isNew ? "/api/tour" : `/api/tour/${tour.internalname}`
    const method   = isNew ? "POST" : "PUT"

    const body = {
      tour_internalname: tour.internalname,
      tour_type:         tour.type,
      tour_name:         tour.name,
      bans: [
        ...tour.clauses,
        ...tour.bans.map(b  => `-${b}`),
        ...tour.unbans.map(u => `+${u}`),
      ],
      misc_commands: tour.misc,
    }

    const res  = await fetch(endpoint, {
      method, credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })
    const data = await res.json()
    setSaving(false)

    if (!res.ok) { showToast(data.error || "save failed.", "error"); return }

    showToast(isNew ? `tour "${tour.internalname}" created.` : "saved.")
    await loadTours()
    if (isNew) setSelected(tour.internalname)
  }

  // ── delete ──
  const handleDelete = (internalname) => {
    setConfirm({
      message: `This will permanently delete "${internalname}" and all its associated bans and schedule entries. This cannot be undone.`,
      action: async () => {
        setConfirm(null)
        const res = await fetch(`/api/tour/${internalname}`, {
          method: "DELETE", credentials: "include",
        })
        if (res.ok) {
          showToast(`"${internalname}" deleted.`)
          setSelected(null); setDetail(null)
          await loadTours()
        } else {
          const d = await res.json()
          showToast(d.error || "delete failed.", "error")
        }
      }
    })
  }

  const filtered = tours.filter(t =>
    t.tour_internalname.includes(search.toLowerCase()) ||
    (t.tour_name || "").toLowerCase().includes(search.toLowerCase())
  )

  return (
    <div>
      <nav className="navbar">
        <div className="navbar-left">
          <span className="navbar-title"><span>tour manager</span></span>
          <div className="navbar-divider" />
          <div className="navbar-user">
            <span>{user}</span>
            <span className="room-tag">{room}</span>
            {onBack && (
              <><span className="sep">·</span>
              <button className="ghost-btn" onClick={onBack}>← schedule</button></>
            )}
          </div>
        </div>
      </nav>

      <div className="manager-layout">
        {/* sidebar */}
        <aside className="sidebar">
          <div className="sidebar-header">
            <div className="sidebar-label">tours — {tours.length}</div>
            <input className="sidebar-search" placeholder="search…"
              value={search} onChange={e => setSearch(e.target.value)} />
          </div>

          <div className="sidebar-list">
            {filtered.map(t => (
              <div key={t.tour_internalname}
                className={`tour-item${selected === t.tour_internalname ? " active" : ""}`}
                onClick={() => handleSelect(t.tour_internalname)}>
                <span className="tour-item-name">{t.tour_internalname}</span>
                {t.tour_type && (
                  <span className="tour-item-type">{t.tour_type.replace("gen9", "").slice(0, 8)}</span>
                )}
              </div>
            ))}
          </div>

          <button className="sidebar-new-btn"
            onClick={() => handleSelect("__new__")}>
            + new tour
          </button>
        </aside>

        {/* editor */}
        {!selected ? (
          <div className="editor-panel">
            <div className="editor-empty">
              <img src={meowLogo} alt="meow" style={{ width: 64, height: 64, opacity: 0.25 }} />
              <span>select a tour to edit, or create a new one.</span>
            </div>
          </div>
        ) : detail === null ? (
          <div className="editor-panel">
            <div className="editor-empty">
              <span style={{ letterSpacing: 1 }}>loading...</span>
            </div>
          </div>
        ) : (
          <TourEditor
            key={selected}
            tour={detail}
            isNew={selected === "__new__"}
            onSave={handleSave}
            onDelete={handleDelete}
            saving={saving}
            user={user}
            room={room}
            isOwner={rank === "#"}
          />
        )}
      </div>

      {toast && <div className={`toast ${toast.type}`}>{toast.msg}</div>}

      {confirm && (
        <ConfirmModal
          message={confirm.message}
          onConfirm={confirm.action}
          onCancel={() => setConfirm(null)}
        />
      )}
    </div>
  )
}
