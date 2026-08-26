import React, { useCallback, useEffect, useState } from 'react'
import {
  api,
  CATEGORY_COLORS,
  SOCIAL_META,
  EMAIL_CATEGORY_COLORS,
  fmtEmployees,
  fmtTime,
} from '../api.js'

export default function CompanyDrawer({ company, onClose, onToast, onStatsChanged, onSettingsOpen, onBlocked }) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [verifying, setVerifying] = useState(false)
  const [blocking, setBlocking] = useState(false)

  const blockCompany = async () => {
    setBlocking(true)
    try {
      await api.post(`/companies/${company.id}/block`)
      onToast(`“${company.name}” excluded from your data warehouse`)
      if (onBlocked) await onBlocked()
    } catch (err) {
      onToast('Block failed: ' + err.message)
    } finally {
      setBlocking(false)
    }
  }

  const load = useCallback(
    async (refresh) => {
      if (refresh) setRefreshing(true)
      else setLoading(true)
      try {
        const res = await api.get(`/companies/${company.id}/contacts?refresh=${refresh ? 'true' : 'false'}`)
        setData(res)
        if (onStatsChanged) onStatsChanged()
      } catch (err) {
        onToast('Scrape failed: ' + err.message)
      } finally {
        setLoading(false)
        setRefreshing(false)
      }
    },
    [company.id, onStatsChanged, onToast],
  )

  useEffect(() => {
    load(false)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [company.id])

  const copy = async (text, label) => {
    try {
      await navigator.clipboard.writeText(text)
      onToast(`${label} copied`)
    } catch {
      onToast('Copy failed — please copy manually')
    }
  }

  const verifyEmails = async () => {
    setVerifying(true)
    try {
      const res = await api.post(`/companies/${company.id}/verify`)
      onToast(
        `Verified ${res.total}: ${res.deliverable} deliverable, ${res.risky} risky, ${res.mx_ok} MX-only, ${res.disposable} disposable`,
      )
      await load(false)
    } catch (err) {
      onToast('Verification failed: ' + err.message)
    } finally {
      setVerifying(false)
    }
  }

  const color = CATEGORY_COLORS[company.category] || '#64748b'
  const hasAny =
    data && (data.emails.length || data.phones.length || data.people.length || data.socials.length)

  return (
    <div className="drawer-overlay" onClick={onClose}>
      <div className="drawer" onClick={(e) => e.stopPropagation()}>
        <div className="drawer-head">
          <div className="company-avatar big" style={{ background: color + '22', color }}>
            {company.name.slice(0, 2).toUpperCase()}
          </div>
          <div className="drawer-title">
            <h2>{company.name}</h2>
            <a href={company.website} target="_blank" rel="noreferrer">
              {company.website}
            </a>
          </div>
          <button className="close-btn" onClick={onClose}>
            ✕
          </button>
        </div>

        <div className="drawer-sub">
          <span className="meta-item">📍 {company.country} · {company.city || '—'}</span>
          <span className="meta-item">👥 {fmtEmployees(company.employees)} employees</span>
          <span className="meta-item">📅 Founded {company.founded || '—'}</span>
          <span className="cat-badge" style={{ background: color + '1f', color }}>
            {company.category}
          </span>
        </div>

        <p className="drawer-desc">{company.description}</p>

        <div className="drawer-toolbar">
          <h3>Contact data</h3>
          <div className="drawer-actions">
            <button className="btn ghost" onClick={() => onSettingsOpen()}>
              ⚙ Scraper options
            </button>
            <button className="btn ghost" onClick={verifyEmails} disabled={verifying}>
              {verifying ? 'Verifying…' : '✓ Verify emails'}
            </button>
            <button className="btn ghost danger" onClick={blockCompany} disabled={blocking}>
              {blocking ? 'Excluding…' : '🚫 Exclude'}
            </button>
            <button className="btn primary" onClick={() => load(true)} disabled={refreshing}>
              {refreshing ? 'Scraping…' : '↻ Re-scrape'}
            </button>
          </div>
        </div>

        {loading ? (
          <div className="drawer-loading">
            <div className="spinner" />
            <p>Scraping {company.domain}… checking their published contact pages.</p>
          </div>
        ) : (
          <>
            {data && (
              <ScrapeStatus data={data} />
            )}

            {!hasAny && (
              <div className="empty">
                <div className="empty-icon">📭</div>
                <h3>No contact details found</h3>
                <p>
                  {data?.status === 'failed'
                    ? data.message || 'The site could not be scraped.'
                    : 'This company does not publish emails/phones/social links on the pages we checked.'}
                </p>
                <button className="btn primary" onClick={() => load(true)}>
                  Try re-scraping
                </button>
              </div>
            )}

            {data?.emails?.length > 0 && (
              <section className="info-section">
                <h4>📧 Email addresses <span className="pill">{data.emails.length}</span></h4>
                <div className="info-list">
                  {data.emails.map((e) => (
                    <InfoRow
                      key={e.id}
                      badge={e.category}
                      badgeColor={EMAIL_CATEGORY_COLORS[e.category] || '#64748b'}
                      value={e.email}
                      onCopy={() => copy(e.email, 'Email')}
                      source={e.source_url}
                      verify={e}
                    />
                  ))}
                </div>
              </section>
            )}

            {data?.phones?.length > 0 && (
              <section className="info-section">
                <h4>☎️ Phone numbers <span className="pill">{data.phones.length}</span></h4>
                <div className="info-list">
                  {data.phones.map((p) => (
                    <InfoRow
                      key={p.id}
                      badge="phone"
                      badgeColor="#0ea5e9"
                      value={p.phone}
                      onCopy={() => copy(p.phone, 'Phone')}
                      source={p.source_url}
                    />
                  ))}
                </div>
              </section>
            )}

            {data?.people?.length > 0 && (
              <section className="info-section">
                <h4>👤 Decision makers <span className="pill">{data.people.length}</span></h4>
                <div className="info-list">
                  {data.people.map((p) => (
                    <div className="person-row" key={p.id}>
                      <div className="person-avatar">
                        {p.name.split(' ').map((x) => x[0]).slice(0, 2).join('').toUpperCase()}
                      </div>
                      <div className="person-main">
                        <div className="person-name">{p.name}</div>
                        {p.title && <div className="person-title">{p.title}</div>}
                        {p.email && (
                          <button
                            className="person-email"
                            onClick={() => copy(p.email, 'Email')}
                            title="Click to copy"
                          >
                            ✉ {p.email}
                            <PersonEmailBadge status={p} />
                          </button>
                        )}
                        {p.phone && (
                          <button
                            className="person-phone"
                            onClick={() => copy(p.phone, 'Phone')}
                            title="Click to copy"
                          >
                            ☎ {p.phone}
                            <span className="published-badge">
                              {p.phone_label === 'Direct line' ? 'direct line' : 'published'}
                            </span>
                          </button>
                        )}
                        {p.linkedin_url && (
                          <a
                            className="person-linkedin"
                            href={p.linkedin_url}
                            target="_blank"
                            rel="noreferrer"
                            title={p.linkedin_type === 'profile' ? 'LinkedIn profile' : 'Open LinkedIn people-search'}
                          >
                            🔗 LinkedIn{p.linkedin_type === 'search' ? ' (search)' : ''} ↗
                          </a>
                        )}
                      </div>
                      {p.source_url && <SourceLink url={p.source_url} />}
                    </div>
                  ))}
                </div>
              </section>
            )}

            {data?.socials?.length > 0 && (
              <section className="info-section">
                <h4>🌐 Social profiles <span className="pill">{data.socials.length}</span></h4>
                <div className="social-list">
                  {data.socials.map((s) => {
                    const meta = SOCIAL_META[s.network] || { label: s.network, icon: '↗', color: '#64748b' }
                    return (
                      <a
                        key={s.id}
                        className="social-chip"
                        href={s.url}
                        target="_blank"
                        rel="noreferrer"
                        style={{ borderColor: meta.color + '66' }}
                      >
                        <span className="social-icon" style={{ background: meta.color }}>
                          {meta.icon}
                        </span>
                        {meta.label}
                      </a>
                    )
                  })}
                </div>
              </section>
            )}
          </>
        )}

        <p className="source-note">
          Names, titles, phones and published emails come from the company's public website
          (each row links to its source page). A <strong>✓ verified</strong> badge means SMTP
          confirmed the mailbox. <strong>derived</strong> means the address was guessed from the
          name pattern and has <em>not</em> been confirmed — treat it as a lead, not a fact.
          Catch-all domains accept any address, so they cannot be confirmed individually.
        </p>
      </div>
    </div>
  )
}

function ScrapeStatus({ data }) {
  if (!data.scraped) return null
  const statusMap = {
    ok: { icon: '✅', cls: 'ok', text: 'Scraped successfully' },
    partial: { icon: '🟡', cls: 'partial', text: 'Scraped — limited data found' },
    failed: { icon: '❌', cls: 'fail', text: 'Scrape failed' },
  }
  const s = statusMap[data.status] || statusMap.failed
  return (
    <div className={`scrape-status ${s.cls}`}>
      <span>{s.icon} {s.text}</span>
      {data.base_url && (
        <span className="base-url">
          from {data.base_url.replace(/^https?:\/\//, '')} · {data.pages_checked} pages ·{' '}
          {fmtTime(data.scraped_at)}
        </span>
      )}
    </div>
  )
}

function InfoRow({ badge, badgeColor, value, onCopy, source, verify }) {
  return (
    <div className="info-row">
      <span className="info-badge" style={{ background: badgeColor + '22', color: badgeColor }}>
        {badge}
      </span>
      <button className="info-value" onClick={onCopy} title="Click to copy">
        {value}
      </button>
      {verify && <VerifyBadge status={verify} />}
      {source && <SourceLink url={source} />}
    </div>
  )
}

function VerifyBadge({ status }) {
  const s = status || {}
  if (s.disposable === 'yes') return <span className="vbadge disposable">⛔ disposable</span>
  if (s.verdict === 'deliverable') return <span className="vbadge ok">✓ verified</span>
  if (s.verdict === 'catchall' || s.catchall === 'yes') return <span className="vbadge catchall">◌ catch-all</span>
  if (s.smtp_status === 'deliverable') return <span className="vbadge ok">✓ deliverable</span>
  if (s.smtp_status === 'rejected') return <span className="vbadge risky">⚠ rejected</span>
  if (s.mx_status === 'ok') return <span className="vbadge mx">MX ✓</span>
  if (s.mx_status === 'missing') return <span className="vbadge invalid">✗ no MX</span>
  return null
}

function PersonEmailBadge({ status: p }) {
  const badges = []
  // how the email was obtained
  if (p.email_status === 'verified') {
    badges.push(<span key="v" className="vbadge ok">✓ verified</span>)
  } else if (p.email_status === 'catchall') {
    badges.push(<span key="c" className="vbadge catchall">◌ catch-all</span>)
  } else if (p.email_status === 'published') {
    badges.push(<span key="p" className="published-badge">published</span>)
  } else if (p.email_status === 'pattern-derived') {
    badges.push(<span key="d" className="derived-badge">derived</span>)
  }
  // extra SMTP signal if present
  if (p.email_status !== 'verified' && p.email_status !== 'catchall' && p.smtp_status === 'rejected') {
    badges.push(<span key="r" className="vbadge risky">⚠ rejected</span>)
  }
  return <>{badges}</>
}

function SourceLink({ url }) {
  return (
    <a
      className="source-link"
      href={url}
      target="_blank"
      rel="noreferrer"
      title={url}
      onClick={(e) => e.stopPropagation()}
    >
      source ↗
    </a>
  )
}
