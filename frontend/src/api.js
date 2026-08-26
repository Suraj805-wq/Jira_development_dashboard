const BASE = '/api'

async function request(path, options = {}) {
  const res = await fetch(BASE + path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      detail = body.detail || detail
    } catch {}
    throw new Error(detail)
  }
  if (res.status === 204) return null
  return res.json()
}

export const api = {
  get: (path) => request(path),
  post: (path, body) =>
    request(path, { method: 'POST', body: body ? JSON.stringify(body) : undefined }),
  put: (path, body) =>
    request(path, { method: 'PUT', body: body ? JSON.stringify(body) : undefined }),
}

export function flagFromCode(code) {
  const cc = (code || '').toUpperCase()
  if (!cc) return '🌐'
  return String.fromCodePoint(...[...cc].map((c) => 127397 + c.charCodeAt(0)))
}

export const CATEGORY_COLORS = {
  'Fleet Management Software': '#6366f1',
  'GPS Tracking / Telematics': '#0ea5e9',
  'Video Telematics / Dashcam': '#f59e0b',
  'ELD & Compliance': '#10b981',
  'Asset & Cargo Tracking': '#8b5cf6',
  'Fleet Maintenance': '#14b8a6',
  'Field Service Management': '#ef4444',
  'Transportation Management (TMS)': '#ec4899',
}

export const SOCIAL_META = {
  linkedin: { label: 'LinkedIn', icon: 'in', color: '#0a66c2' },
  x: { label: 'X', icon: '𝕏', color: '#0f1419' },
  twitter: { label: 'Twitter', icon: '𝕏', color: '#1da1f2' },
  facebook: { label: 'Facebook', icon: 'f', color: '#1877f2' },
  instagram: { label: 'Instagram', icon: '◉', color: '#e1306c' },
  youtube: { label: 'YouTube', icon: '▶', color: '#ff0000' },
}

export const EMAIL_CATEGORY_COLORS = {
  Sales: '#10b981',
  Support: '#0ea5e9',
  Careers: '#8b5cf6',
  Billing: '#f59e0b',
  General: '#64748b',
}

export function fmtEmployees(n) {
  if (!n) return '—'
  if (n >= 1000) return (n / 1000).toFixed(n % 1000 === 0 ? 0 : 1) + 'k'
  return String(n)
}

export function fmtTime(iso) {
  if (!iso) return ''
  const d = new Date(iso.endsWith('Z') ? iso : iso + 'Z')
  if (isNaN(d)) return iso
  const mins = Math.round((Date.now() - d.getTime()) / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.round(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  return d.toLocaleDateString()
}
