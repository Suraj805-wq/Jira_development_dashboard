import React, { useEffect, useState } from 'react'
import { api } from '../api.js'

export default function SettingsModal({ onClose, onSaved }) {
  const [form, setForm] = useState({
    respect_robots: true,
    request_delay: 1.0,
    max_pages: 10,
    derive_emails: true,
    verify_on_save: true,
    smtp_timeout: 8,
    max_email_candidates: 11,
    find_names_web: true,
    proxy_url: '',
  })
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    api
      .get('/settings')
      .then(setForm)
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  const save = async () => {
    setSaving(true)
    try {
      const updated = await api.put('/settings', form)
      setForm(updated)
      onSaved()
    } catch {}
    setSaving(false)
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h2>⚙ Scraper & verification options</h2>
          <button className="close-btn" onClick={onClose}>✕</button>
        </div>

        <p className="modal-intro">
          FleetLeads reads contact details from public company websites, then <strong>verifies
          emails before saving</strong> (MX + SMTP + catch-all detection). If a guessed email
          fails, it tries other name combinations until one works.
        </p>

        {loading ? (
          <div className="drawer-loading">Loading…</div>
        ) : (
          <div className="option-list">
            <label className="option-row">
              <div className="option-info">
                <div className="option-title">Verify emails before saving</div>
                <div className="option-desc">
                  Check every email's MX + SMTP + catch-all status and keep only working ones.
                  Turn off to save everything without checking.
                </div>
              </div>
              <input
                type="checkbox"
                checked={form.verify_on_save}
                onChange={(e) => setForm((f) => ({ ...f, verify_on_save: e.target.checked }))}
              />
            </label>

            <label className="option-row">
              <div className="option-info">
                <div className="option-title">Derive & verify executive emails</div>
                <div className="option-desc">
                  For each decision maker, try name combinations (first.last, f.last, flast…)
                  and save the one the mail server confirms.
                </div>
              </div>
              <input
                type="checkbox"
                checked={form.derive_emails}
                onChange={(e) => setForm((f) => ({ ...f, derive_emails: e.target.checked }))}
              />
            </label>

            <label className="option-row">
              <div className="option-info">
                <div className="option-title">Max email combinations per person</div>
                <div className="option-desc">How many name patterns to try (1–20).</div>
              </div>
              <input
                type="number"
                min="1"
                max="20"
                value={form.max_email_candidates}
                onChange={(e) => setForm((f) => ({ ...f, max_email_candidates: parseInt(e.target.value, 10) || 11 }))}
              />
            </label>

            <label className="option-row">
              <div className="option-info">
                <div className="option-title">SMTP timeout (seconds)</div>
                <div className="option-desc">Per-mailbox handshake timeout during verification.</div>
              </div>
              <input
                type="number"
                min="2"
                max="30"
                value={form.smtp_timeout}
                onChange={(e) => setForm((f) => ({ ...f, smtp_timeout: parseInt(e.target.value, 10) || 8 }))}
              />
            </label>

            <label className="option-row">
              <div className="option-info">
                <div className="option-title">Find decision makers from open web</div>
                <div className="option-desc">
                  When an organisation's own site lists no leadership, look up
                  executives on Wikipedia + open-web search (never scrapes LinkedIn
                  member pages — uses public search results only).
                </div>
              </div>
              <input
                type="checkbox"
                checked={form.find_names_web}
                onChange={(e) => setForm((f) => ({ ...f, find_names_web: e.target.checked }))}
              />
            </label>

            <label className="option-row">
              <div className="option-info">
                <div className="option-title">Proxy URL (optional)</div>
                <div className="option-desc">
                  Route scraping through a proxy/VPN egress, e.g. http://host:port or
                  socks5://user:pass@host:port. Comma-separate a pool with "pool:".
                  Leave empty for direct connection.
                </div>
              </div>
              <input
                type="text"
                placeholder="socks5://… or http://…"
                value={form.proxy_url || ''}
                onChange={(e) => setForm((f) => ({ ...f, proxy_url: e.target.value }))}
              />
            </label>

            <label className="option-row">
              <div className="option-info">
                <div className="option-title">Respect robots.txt</div>
                <div className="option-desc">Skip paths the site disallows for bots.</div>
              </div>
              <input
                type="checkbox"
                checked={form.respect_robots}
                onChange={(e) => setForm((f) => ({ ...f, respect_robots: e.target.checked }))}
              />
            </label>

            <label className="option-row">
              <div className="option-info">
                <div className="option-title">Delay between requests</div>
                <div className="option-desc">Seconds between page fetches (0–10).</div>
              </div>
              <input
                type="number"
                min="0"
                max="10"
                step="0.5"
                value={form.request_delay}
                onChange={(e) => setForm((f) => ({ ...f, request_delay: parseFloat(e.target.value) || 0 }))}
              />
            </label>

            <label className="option-row">
              <div className="option-info">
                <div className="option-title">Max pages per company</div>
                <div className="option-desc">Homepage + leadership/contact/news pages (1–15).</div>
              </div>
              <input
                type="number"
                min="1"
                max="15"
                value={form.max_pages}
                onChange={(e) => setForm((f) => ({ ...f, max_pages: parseInt(e.target.value, 10) || 10 }))}
              />
            </label>
          </div>
        )}

        <div className="modal-foot">
          <span className="muted">
            Note: a real VPN changes the machine's IP at OS level and can't be installed by Python.
            Proxies are the portable equivalent — plug in any HTTP/SOCKS proxy (or residential
            proxy) above and scraping will route through it.
          </span>
          <div>
            <button className="btn ghost" onClick={onClose}>Cancel</button>
            <button className="btn primary" onClick={save} disabled={saving}>
              {saving ? 'Saving…' : 'Save'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
