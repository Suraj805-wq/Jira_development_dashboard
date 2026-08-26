import React, { useEffect, useRef, useState } from 'react'
import { api } from '../api.js'

const JOBS = [
  { id: 'discover', icon: '🔭', label: 'Discover', remainingKey: 'unscraped', hint: 'New organisations' },
  { id: 'scrape', icon: '🕷', label: 'Scrape', remainingKey: 'unscraped', hint: 'Sites not yet crawled' },
  { id: 'people', icon: '👤', label: 'People', remainingKey: 'zero_people', hint: 'Orgs with 0 executives' },
  { id: 'verify', icon: '✓', label: 'Verify', remainingKey: 'pending_verify', hint: 'Emails still unchecked' },
]

function elapsed(iso) {
  if (!iso) return ''
  const t = new Date(iso.endsWith('Z') ? iso : iso + 'Z').getTime()
  if (Number.isNaN(t)) return ''
  const s = Math.max(0, Math.round((Date.now() - t) / 1000))
  if (s < 60) return `${s}s`
  const m = Math.floor(s / 60)
  return `${m}m ${s % 60}s`
}

function jobLabel(activity) {
  return {
    discover: '🔭 Discovering organisations',
    scrape: '🕷 Scraping websites',
    people: '👤 Finding decision makers',
    verify: '✓ Verifying emails',
    idle: '⏸ Idle — waiting for next cycle',
    system: '⚙ Worker',
  }[activity] || activity || '—'
}

export default function DiscoveryPanel({ worker, onChange }) {
  const [busy, setBusy] = useState(false)
  const logRef = useRef(null)
  const snap = worker?.snapshot || {}
  const thread = worker?.thread || {}
  const running = Boolean(worker?.running && thread.alive)
  const pipeline = snap.pipeline || {}
  const log = worker?.log || []

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = 0
  }, [log[0]?.id])

  const toggle = async () => {
    setBusy(true)
    try {
      if (running) await api.post('/worker/stop')
      else await api.post('/worker/start')
      if (onChange) await onChange()
    } catch {}
    setBusy(false)
  }

  const runNow = async () => {
    setBusy(true)
    try {
      await api.post('/worker/run-now')
      if (onChange) await onChange()
    } catch {}
    setBusy(false)
  }

  const remaining = {
    unscraped: snap.unscraped ?? pipeline.scrape_remaining ?? 0,
    zero_people: snap.zero_people ?? pipeline.people_remaining ?? 0,
    pending_verify: snap.pending_verify ?? pipeline.verify_remaining ?? 0,
  }

  return (
    <section className={`discovery-panel ${running ? 'live' : 'paused'}`}>
      <div className="discovery-head">
        <div className="discovery-title">
          <span className={`worker-dot ${running ? 'on' : ''}`} />
          <div>
            <h2>Discovery engine</h2>
            <p className="discovery-sub">
              {running ? (
                <>
                  <strong>LIVE</strong>
                  {thread.name && (
                    <> · thread <code>{thread.name}</code>#{thread.ident}</>
                  )}
                  {worker?.heartbeat && <> · heartbeat {elapsed(worker.heartbeat)} ago</>}
                  {worker?.cycle != null && <> · cycle {worker.cycle}</>}
                </>
              ) : (
                'Paused — no background thread is discovering new data'
              )}
            </p>
          </div>
        </div>
        <div className="discovery-actions">
          <button className="btn ghost" onClick={toggle} disabled={busy}>
            {running ? 'Pause thread' : 'Start thread'}
          </button>
          <button className="btn primary" onClick={runNow} disabled={busy}>
            Run cycle now
          </button>
        </div>
      </div>

      <div className="discovery-now">
        <div className="now-label">{jobLabel(worker?.activity)}</div>
        <div className="now-detail">
          {worker?.detail || 'Waiting for the next job…'}
          {worker?.activity_started_at && running && worker?.activity !== 'idle' && (
            <span className="now-elapsed"> · running {elapsed(worker.activity_started_at)}</span>
          )}
        </div>
      </div>

      <div className="pipeline-grid">
        {JOBS.map((job) => {
          const left = remaining[job.remainingKey] ?? 0
          const active = worker?.activity === job.id
          return (
            <div key={job.id} className={`pipe-card ${active ? 'active' : ''}`}>
              <div className="pipe-top">
                <span>{job.icon} {job.label}</span>
                {active && <span className="pipe-live">in progress</span>}
              </div>
              <div className="pipe-value">{job.id === 'discover' ? (snap.countries ?? '—') : left}</div>
              <div className="pipe-hint">
                {job.id === 'discover' ? 'Countries in warehouse' : `${left} remaining · ${job.hint}`}
              </div>
              <div className="pipe-bar">
                <span style={{ width: job.id === 'discover' ? '70%' : `${Math.min(100, left ? 100 : 8)}%` }} />
              </div>
            </div>
          )
        })}
      </div>

      <div className="discovery-kpis">
        <Kpi label="Organisations" value={snap.companies} />
        <Kpi label="Decision makers" value={snap.people} />
        <Kpi label="SMTP-verified" value={snap.verified_emails} note="real mailboxes only" />
        <Kpi label="Derived emails" value={snap.derived_people} note="guessed, unverified" />
        <Kpi label="Unscraped" value={snap.unscraped} />
        <Kpi label="0 people" value={snap.zero_people} />
      </div>

      <div className="discovery-log-wrap">
        <h3>Live thread log</h3>
        <div className="discovery-log" ref={logRef}>
          {log.length === 0 ? (
            <div className="log-empty">No events yet — start the thread to watch discovery.</div>
          ) : (
            log.map((row) => (
              <div key={row.id} className={`log-row ${row.level || 'info'}`}>
                <span className="log-ts">{(row.ts || '').replace('T', ' ').slice(0, 19)}</span>
                <span className="log-job">{row.job}</span>
                <span className="log-msg">{row.message}</span>
              </div>
            ))
          )}
        </div>
      </div>
    </section>
  )
}

function Kpi({ label, value, note }) {
  return (
    <div className="disc-kpi">
      <div className="disc-kpi-value">{value ?? '—'}</div>
      <div className="disc-kpi-label">{label}</div>
      {note && <div className="disc-kpi-note">{note}</div>}
    </div>
  )
}
