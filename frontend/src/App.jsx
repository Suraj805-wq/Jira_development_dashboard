import React, { useCallback, useEffect, useRef, useState } from 'react'
import { api, flagFromCode, CATEGORY_COLORS, fmtEmployees } from './api.js'
import CompanyDrawer from './components/CompanyDrawer.jsx'
import SettingsModal from './components/SettingsModal.jsx'
import BlocklistModal from './components/BlocklistModal.jsx'
import DiscoveryPanel from './components/DiscoveryPanel.jsx'

const PAGE_SIZE = 24

export default function App() {
  const [companies, setCompanies] = useState([])
  const [facets, setFacets] = useState({ countries: [], categories: [] })
  const [stats, setStats] = useState(null)
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)

  const [country, setCountry] = useState('')
  const [category, setCategory] = useState('')
  const [query, setQuery] = useState('')

  const [selected, setSelected] = useState(null)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [blocklistOpen, setBlocklistOpen] = useState(false)
  const [loading, setLoading] = useState(true)
  const [toast, setToast] = useState(null)
  const [scraping, setScraping] = useState(false)
  const [lookupQuery, setLookupQuery] = useState('')
  const [lookupLoading, setLookupLoading] = useState(false)
  const [discoverCountry, setDiscoverCountry] = useState('')
  const [discovering, setDiscovering] = useState(false)
  const [worker, setWorker] = useState(null)

  const toastTimer = useRef(null)
  const showToast = useCallback((msg) => {
    setToast(msg)
    clearTimeout(toastTimer.current)
    toastTimer.current = setTimeout(() => setToast(null), 4000)
  }, [])

  const loadStats = useCallback(async () => {
    try {
      setStats(await api.get('/stats'))
    } catch {}
  }, [])

  const loadCompanies = useCallback(async () => {
    setLoading(true)
    try {
      const params = new URLSearchParams({ page: String(page), page_size: String(PAGE_SIZE) })
      if (country) params.set('country', country)
      if (category) params.set('category', category)
      if (query) params.set('q', query)
      const data = await api.get(`/companies?${params.toString()}`)
      setCompanies(data.items)
      setFacets(data.facets)
      setTotal(data.total)
    } catch (err) {
      showToast('Failed to load companies: ' + err.message)
    } finally {
      setLoading(false)
    }
  }, [country, category, query, page, showToast])

  useEffect(() => {
    loadCompanies()
  }, [loadCompanies])

  useEffect(() => {
    loadStats()
  }, [loadStats])

  const refreshWorker = useCallback(async () => {
    try {
      setWorker(await api.get('/worker/status'))
    } catch {}
  }, [])

  // poll the discovery thread every 2s so the live log actually moves
  useEffect(() => {
    refreshWorker()
    const t = setInterval(refreshWorker, 2000)
    const t2 = setInterval(loadStats, 8000)
    return () => {
      clearInterval(t)
      clearInterval(t2)
    }
  }, [refreshWorker, loadStats])

  useEffect(() => {
    setPage(1)
  }, [country, category, query])

  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  const doLookup = async () => {
    const q = lookupQuery.trim()
    if (!q) return
    setLookupLoading(true)
    try {
      const res = await api.post('/companies/lookup', { query: q })
      if (res.blocked) {
        showToast(`“${res.company.name}” is on your blocklist — not shown`)
        setLookupQuery('')
        return
      }
      showToast(
        res.existing
          ? 'Company already in directory'
          : `Added “${res.company.name}” and scraped it`,
      )
      setSelected(res.company)
      await loadStats()
      await loadCompanies()
    } catch (err) {
      showToast('Search failed: ' + err.message)
    } finally {
      setLookupLoading(false)
    }
  }

  const doDiscover = async () => {
    const country = discoverCountry.trim()
    if (!country) return
    setDiscovering(true)
    showToast(`Discovering fleet organisations in ${country}… this can take a minute.`)
    try {
      const res = await api.post('/discover', { country, scrape: true })
      showToast(
        `${country}: found ${res.verified} organisations → added ${res.added.length} new, scraped ${res.scrape_summary.ok} (${res.scrape_summary.failed} failed)`,
      )
      setDiscoverCountry('')
      await loadStats()
      await loadCompanies()
    } catch (err) {
      showToast('Discovery failed: ' + err.message)
    } finally {
      setDiscovering(false)
    }
  }

  const exportCsv = async () => {
    try {
      const params = new URLSearchParams()
      if (country) params.set('country', country)
      if (category) params.set('category', category)
      if (query) params.set('q', query)
      const res = await fetch(`/api/export/contacts?${params.toString()}`)
      if (!res.ok) throw new Error('Export failed')
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = 'fleet-contact-data.csv'
      a.click()
      URL.revokeObjectURL(url)
      showToast('CSV exported')
    } catch (err) {
      showToast('Export failed: ' + err.message)
    }
  }

  const scrapeAll = async () => {
    setScraping(true)
    showToast('Scraping company websites… this can take a few minutes.')
    try {
      const params = new URLSearchParams()
      if (country) params.set('country', country)
      if (category) params.set('category', category)
      params.set('limit', '200')
      const res = await api.post(`/enrich?${params.toString()}`)
      showToast(`Done — ${res.processed} scraped, ${res.failed} failed`)
      await loadStats()
      await loadCompanies()
    } catch (err) {
      showToast('Bulk scrape failed: ' + err.message)
    } finally {
      setScraping(false)
    }
  }

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <div className="logo">⚡</div>
          <div>
            <h1>FleetLeads</h1>
            <p>Fleet & telematics contact finder — 100% open-source</p>
          </div>
        </div>
        <div className="topbar-actions">
          <button className="btn ghost" onClick={() => setBlocklistOpen(true)}>
            🚫 Excluded ({stats?.blocked ?? 0})
          </button>
          <button className="btn ghost" onClick={() => setSettingsOpen(true)}>
            ⚙ Scraper
          </button>
          <button className="btn ghost" onClick={exportCsv}>⬇ CSV</button>
          <button className="btn primary" onClick={scrapeAll} disabled={scraping}>
            {scraping ? 'Scraping…' : '✦ Scrape all'}
          </button>
        </div>
      </header>

      <div className="stats-row">
        <StatCard icon="🏢" label="Fleet organisations" value={stats?.companies ?? '—'} />
        <StatCard icon="🌍" label="Countries covered" value={stats?.countries ?? '—'} />
        <StatCard icon="👤" label="Decision makers" value={stats?.people ?? '—'} accent />
        <StatCard icon="📧" label="Published emails" value={stats?.emails ?? '—'} />
        <StatCard icon="☎️" label="Phone numbers" value={stats?.phones ?? '—'} />
        <StatCard icon="✅" label="SMTP-verified" value={stats?.verified ?? '—'} />
        <StatCard icon="❔" label="Derived (unverified)" value={stats?.derived ?? '—'} />
      </div>

      <DiscoveryPanel worker={worker} onChange={refreshWorker} />

      <div className="global-search">
        <input
          placeholder="Search ANY company worldwide — enter a name or domain (e.g. Trimble, fleetx.io) and it will be scraped live"
          value={lookupQuery}
          onChange={(e) => setLookupQuery(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && doLookup()}
        />
        <button className="btn primary" onClick={doLookup} disabled={lookupLoading}>
          {lookupLoading ? 'Searching…' : '🔍 Search & scrape'}
        </button>
        <input
          placeholder="Target a country — e.g. Spain, Poland, UAE"
          value={discoverCountry}
          onChange={(e) => setDiscoverCountry(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && doDiscover()}
        />
        <button className="btn primary" onClick={doDiscover} disabled={discovering}>
          {discovering ? 'Gathering…' : '🌍 Gather country'}
        </button>
      </div>

      <div className="layout">
        <aside className="sidebar">
          <div className="side-section">
            <h3>Countries</h3>
            <button
              className={`country-item ${!country ? 'active' : ''}`}
              onClick={() => setCountry('')}
            >
              <span className="flag">🌐</span>
              <span className="label">All countries</span>
              <span className="count">{total}</span>
            </button>
            {facets.countries.map((c) => (
              <button
                key={c.country}
                className={`country-item ${country === c.country ? 'active' : ''}`}
                onClick={() => setCountry(c.country)}
              >
                <span className="flag">{flagFromCode(c.country_code)}</span>
                <span className="label">{c.country}</span>
                <span className="count">{c.c}</span>
              </button>
            ))}
          </div>

          <div className="side-section">
            <h3>Category</h3>
            <button
              className={`cat-item ${!category ? 'active' : ''}`}
              onClick={() => setCategory('')}
            >
              <span className="dot" style={{ background: '#64748b' }} />
              All categories
            </button>
            {facets.categories.map((c) => (
              <button
                key={c.category}
                className={`cat-item ${category === c.category ? 'active' : ''}`}
                onClick={() => setCategory(c.category)}
              >
                <span className="dot" style={{ background: CATEGORY_COLORS[c.category] || '#64748b' }} />
                {c.category}
                <span className="count">{c.c}</span>
              </button>
            ))}
          </div>
        </aside>

        <main className="content">
          <div className="toolbar">
            <input
              className="search"
              placeholder="Search company, domain, city…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
            {country && (
              <span className="chip active-chip" onClick={() => setCountry('')}>
                {flagFromCode(facets.countries.find((c) => c.country === country)?.country_code)} {country} ✕
              </span>
            )}
            {category && (
              <span className="chip active-chip" onClick={() => setCategory('')}>
                {category} ✕
              </span>
            )}
            <span className="results-count">{total} organisations</span>
          </div>

          {loading ? (
            <div className="skeleton-grid">
              {Array.from({ length: 8 }).map((_, i) => (
                <div className="skeleton-card" key={i} />
              ))}
            </div>
          ) : companies.length === 0 ? (
            <div className="empty">
              <div className="empty-icon">🔍</div>
              <h3>No organisations match your filters</h3>
              <p>Try a different country, category, or search term.</p>
            </div>
          ) : (
            <div className="card-grid">
              {companies.map((c) => (
                <CompanyCard key={c.id} company={c} onOpen={setSelected} />
              ))}
            </div>
          )}

          {pages > 1 && (
            <div className="pagination">
              <button className="btn ghost" disabled={page <= 1} onClick={() => setPage(page - 1)}>
                ‹ Prev
              </button>
              <span>
                Page {page} of {pages}
              </span>
              <button className="btn ghost" disabled={page >= pages} onClick={() => setPage(page + 1)}>
                Next ›
              </button>
            </div>
          )}
        </main>
      </div>

      {selected && (
        <CompanyDrawer
          company={selected}
          onClose={() => setSelected(null)}
          onToast={showToast}
          onStatsChanged={loadStats}
          onSettingsOpen={() => setSettingsOpen(true)}
          onBlocked={async () => {
            await loadStats()
            await loadCompanies()
            setSelected(null)
          }}
        />
      )}

      {settingsOpen && (
        <SettingsModal
          onClose={() => setSettingsOpen(false)}
          onSaved={() => {
            showToast('Scraper options updated')
          }}
        />
      )}

      {blocklistOpen && (
        <BlocklistModal
          onClose={() => setBlocklistOpen(false)}
          onChanged={async () => {
            await loadStats()
            await loadCompanies()
          }}
        />
      )}

      {toast && <div className="toast">{toast}</div>}
    </div>
  )
}

function StatCard({ icon, label, value, accent }) {
  return (
    <div className={`stat-card ${accent ? 'accent' : ''}`}>
      <div className="stat-icon">{icon}</div>
      <div>
        <div className="stat-value">{value}</div>
        <div className="stat-label">{label}</div>
      </div>
    </div>
  )
}

function CompanyCard({ company, onOpen }) {
  const color = CATEGORY_COLORS[company.category] || '#64748b'
  const scraped = company.email_count > 0 || company.phone_count > 0 || company.people_count > 0 || company.social_count > 0
  return (
    <div className="company-card" onClick={() => onOpen(company)}>
      <div className="card-top">
        <div className="company-avatar" style={{ background: color + '22', color }}>
          {company.name.slice(0, 2).toUpperCase()}
        </div>
        <div className="company-title">
          <h3>{company.name}</h3>
          <a
            className="domain"
            href={company.website}
            target="_blank"
            rel="noreferrer"
            onClick={(e) => e.stopPropagation()}
          >
            {company.domain}
          </a>
        </div>
      </div>

      <div className="card-meta">
        <span className="meta-item">📍 {company.city || '—'}</span>
        <span className="meta-item">👥 {fmtEmployees(company.employees)}</span>
        <span className="meta-item">📅 {company.founded || '—'}</span>
      </div>

      <span className="cat-badge" style={{ background: color + '1f', color }}>
        {company.category}
      </span>

      <div className="card-bottom">
        {scraped ? (
          <span className="contact-count">
            ✉ {company.email_count} · ☎ {company.phone_count} · 👤 {company.people_count}
          </span>
        ) : (
          <span className="contact-count muted-text">Not scraped yet</span>
        )}
        <span className="open-link">Scrape →</span>
      </div>
    </div>
  )
}
