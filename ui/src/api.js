// API helpers for the trigger + timeline service.
// Relative paths work in dev (Vite proxies them to :8090) and in prod
// (FastAPI serves the built app from the same origin).

export async function fetchTimeline() {
  const r = await fetch('/timeline', { cache: 'no-store' })
  if (!r.ok) throw new Error(`timeline ${r.status}`)
  const data = await r.json()
  return { events: data.events || [], watch: data.watch || null, pending: data.pending || [] }
}

export async function triggerDiagnose() {
  const r = await fetch('/diagnose', { method: 'POST' })
  if (!r.ok) throw new Error(`diagnose ${r.status}`)
  return r.json()
}

export async function approve(id) {
  const r = await fetch('/approve', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ id }),
  })
  if (!r.ok) throw new Error(`approve ${r.status}`)
  return r.json()
}

export async function reject(id) {
  const r = await fetch('/reject', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ id }),
  })
  if (!r.ok) throw new Error(`reject ${r.status}`)
  return r.json()
}

export async function setAuto(enabled) {
  const r = await fetch('/auto', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ enabled }),
  })
  if (!r.ok) throw new Error(`auto ${r.status}`)
  return r.json()
}

// Map an agent outcome to human-readable status text + severity.
// Falls back to the old healthy-flag logic for events recorded before outcomes.
export function outcomeMeta(outcome, healthy) {
  switch (outcome) {
    case 'healed':
      return { label: 'FIXED', status: 'HEALTHY', note: 'a problem was found and fixed', degraded: false }
    case 'no_action':
      return { label: 'ALL GOOD', status: 'HEALTHY', note: 'checked — nothing needed fixing', degraded: false }
    case 'held':
      return { label: 'NEEDS REVIEW', status: 'NEEDS REVIEW', note: "AI wasn't confident enough to fix it on its own", degraded: true }
    case 'failed':
      return { label: 'STILL BROKEN', status: 'STILL BROKEN', note: "the fix didn't resolve it", degraded: true }
    default:
      if (healthy === false) return { label: 'STILL BROKEN', status: 'STILL BROKEN', note: "the fix didn't work yet", degraded: true }
      if (healthy === true) return { label: 'FIXED', status: 'HEALTHY', note: 'everything looks fine', degraded: false }
      return { label: '—', status: 'STANDBY', note: 'waiting for a check', degraded: false }
  }
}

// Derive the stat-strip summary from the most recent check.
export function summarize(events) {
  for (let i = events.length - 1; i >= 0; i--) {
    const e = events[i]
    if (e.type === 'remediation' && e.detail) {
      const d = e.detail.decision || {}
      const rec = e.detail.recovery || {}
      const tok = d._tokens || {}
      const m = outcomeMeta(e.detail.outcome, rec.healthy)
      const acted = d.action && !['none', 'None', ''].includes(d.action)
      return {
        health: m.label,
        degraded: m.degraded,
        action: acted ? d.action : 'none needed',
        confidence: typeof d.confidence === 'number' ? Math.round(d.confidence * 100) + '%' : '—',
        cost: typeof d._cost_usd === 'number' ? '$' + d._cost_usd.toFixed(4) : '—',
        tokens: tok.in != null && tok.out != null ? `${tok.in}↓ ${tok.out}↑` : '—',
        status: m.status,
        note: m.note,
      }
    }
  }
  return {
    health: '—', degraded: false, action: '—', confidence: '—', cost: '—', tokens: '—',
    status: 'STANDBY', note: 'waiting for a check',
  }
}

export function fmtTime(iso) {
  try { return new Date(iso).toLocaleTimeString([], { hour12: false }) } catch { return iso || '—' }
}
