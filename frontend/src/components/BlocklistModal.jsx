import React, { useEffect, useState } from 'react'
import { api } from '../api.js'

export default function BlocklistModal({ onClose, onChanged }) {
  const [entries, setEntries] = useState(null)
  const [name, setName] = useState('')
  const [domain, setDomain] = useState('')
  const [busy, setBusy] = useState(false)

  const load = async () => {
    try {
      const res = await api.get('/blocklist')
      setEntries(res.entries)
    } catch {}
  }

  useEffect(() => {
    load()
  }, [])

  const add = async () => {
    if (!name.trim()) return
    setBusy(true)
    try {
      await api.post('/blocklist', { name: name.trim(), domain: domain.trim() || null })
      setName('')
      setDomain('')
      await load()
      if (onChanged) onChanged()
    } catch (e) {
      alert('Failed: ' + e.message)
    } finally {
      setBusy(false)
    }
  }

  const remove = async (id) => {
    setBusy(true)
    try {
      await api.delete(`/blocklist/${id}`)
      await load()
      if (onChanged) onChanged()
    } catch (e) {
      alert('Failed: ' + e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h2>🚫 Excluded organisations</h2>
          <button className="close-btn" onClick={onClose}>✕</button>
        </div>
        <p className="modal-intro">
          These organisations are excluded from your data warehouse. They won't appear in
          listings, stats, exports, or search results — and they can't be re-added by
          country-discovery or company search.
        </p>

        <div className="blocklist-add">
          <input
            placeholder="Organisation name (e.g. Locus)"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <input
            placeholder="Domain (optional, e.g. locus.sh)"
            value={domain}
            onChange={(e) => setDomain(e.target.value)}
          />
          <button className="btn primary" onClick={add} disabled={busy}>
            + Exclude
          </button>
        </div>

        {!entries ? (
          <div className="drawer-loading">Loading…</div>
        ) : (
          <div className="blocklist-entries">
            {entries.map((e) => (
              <div className="blocklist-row" key={e.id}>
                <div className="blocklist-info">
                  <div className="blocklist-name">{e.name}</div>
                  <div className="blocklist-domain">{e.domain || '—'}</div>
                  {e.blocks_companies?.length > 0 && (
                    <div className="blocklist-blocks">
                      blocks: {e.blocks_companies.map((c) => c.name).join(', ')}
                    </div>
                  )}
                </div>
                <button className="btn ghost" onClick={() => remove(e.id)} disabled={busy}>
                  Restore
                </button>
              </div>
            ))}
          </div>
        )}

        <div className="modal-foot">
          <span className="muted">Excluding an organisation removes it from every view but keeps its data in the database, so you can restore it anytime.</span>
          <button className="btn ghost" onClick={onClose}>Close</button>
        </div>
      </div>
    </div>
  )
}
