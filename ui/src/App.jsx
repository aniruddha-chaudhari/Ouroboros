import { useCallback, useEffect, useMemo, useState } from 'react'
import Ring from './components/Ring.jsx'
import StatStrip from './components/StatStrip.jsx'
import Timeline from './components/Timeline.jsx'
import ApprovalCard from './components/ApprovalCard.jsx'
import Hero from './components/Hero.jsx'
import { fetchTimeline, setAuto, approve, reject, summarize } from './api.js'

const isConsoleRoute = () => window.location.hash === '#console'

export default function App() {
  // The hero's animated ASCII canvas keeps its rAF loop running for as long as
  // it's mounted. Routing the console to its own hash (instead of scrolling
  // both onto one page) unmounts the hero entirely once you're in the console,
  // which was competing with the timeline polling for main-thread time.
  const [page, setPage] = useState(isConsoleRoute() ? 'console' : 'hero')
  const [events, setEvents] = useState([])
  const [watch, setWatch] = useState(null)
  const [pending, setPending] = useState([])
  const [busyId, setBusyId] = useState(null)
  const [connected, setConnected] = useState(null) // null = connecting
  const [activePhase, setActivePhase] = useState(0)
  const [clock, setClock] = useState('')

  useEffect(() => {
    const onHashChange = () => setPage(isConsoleRoute() ? 'console' : 'hero')
    window.addEventListener('hashchange', onHashChange)
    return () => window.removeEventListener('hashchange', onHashChange)
  }, [])

  const summary = useMemo(() => summarize(events), [events])
  // The watchdog is the trigger now — the ring "works" whenever it's mid-heal.
  const working = !!watch && watch.enabled && watch.healthy === false

  const poll = useCallback(async () => {
    try {
      const { events: ev, watch: w, pending: p } = await fetchTimeline()
      setEvents(ev)
      setWatch(w)
      setPending(p)
      setConnected(true)
    } catch {
      setConnected(false)
    }
  }, [])

  const onApprove = useCallback(async (id) => {
    setBusyId(id)
    try {
      await approve(id)      // executes the real action server-side (may take ~10s)
      await poll()
    } catch {
      setConnected(false)
    } finally {
      setBusyId(null)
    }
  }, [poll])

  const onReject = useCallback(async (id) => {
    setBusyId(id)
    try {
      await reject(id)
      await poll()
    } catch {
      setConnected(false)
    } finally {
      setBusyId(null)
    }
  }, [poll])

  const toggleWatch = useCallback(async () => {
    const next = !(watch && watch.enabled)
    setWatch((w) => ({ ...(w || {}), enabled: next })) // optimistic
    try {
      await setAuto(next)
      await poll()
    } catch {
      setConnected(false)
    }
  }, [watch, poll])

  // Poll the timeline every 2.5s — only while the console is actually on screen.
  useEffect(() => {
    if (page !== 'console') return
    poll()
    const id = setInterval(poll, 2500)
    return () => clearInterval(id)
  }, [poll, page])

  // Cycle the loop phases while the agent is working.
  useEffect(() => {
    if (!working || page !== 'console') return
    const id = setInterval(() => setActivePhase((p) => (p + 1) % 4), 120)
    return () => clearInterval(id)
  }, [working, page])

  // Footer clock.
  useEffect(() => {
    const tick = () => setClock(new Date().toLocaleTimeString([], { hour12: false }) + ' local')
    tick()
    const id = setInterval(tick, 1000)
    return () => clearInterval(id)
  }, [])

  const hasPending = pending.length > 0
  const status = hasPending ? 'NEEDS YOU' : working ? 'FIXING' : summary.status
  const note = hasPending
    ? 'the agent needs your approval to act'
    : working ? 'a problem was found — healing…' : summary.note
  // Green is a genuine "healthy" signal, not decoration — it only appears here.
  const coreState = hasPending ? 'crit' : summary.degraded ? 'crit' : working ? 'busy' : summary.status === 'HEALTHY' ? 'ok' : 'idle'
  const connClass = connected === null ? 'conn' : connected ? 'conn live' : 'conn dead'
  const connText = connected === null ? 'Connecting…' : connected ? 'Connected' : 'Disconnected'

  const watchOn = !!watch && watch.enabled
  const watchNote = !watchOn
    ? 'Monitoring paused'
    : watch.healthy === false
    ? 'Problem detected — healing automatically…'
    : watch.cooldown
    ? 'Just healed — settling before the next check'
    : watch.healthy === true
    ? 'Watching continuously · all clear'
    : 'Watching continuously…'

  const enterConsole = () => {
    window.location.hash = 'console'
    setPage('console')
  }
  const backToHero = () => {
    window.location.hash = ''
    setPage('hero')
  }

  if (page === 'hero') {
    return <Hero onEnter={enterConsole} />
  }

  return (
      <div className="wrap" id="console-top">
      <header>
        <div
          className="brand"
          onClick={backToHero}
          onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && backToHero()}
          role="button"
          tabIndex={0}
        >
          <svg className="mark" viewBox="0 0 40 40" aria-hidden="true">
            <defs>
              <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
                <stop offset="0" stopColor="var(--chrome)" />
                <stop offset="1" stopColor="var(--cyan)" />
              </linearGradient>
            </defs>
            <circle cx="20" cy="20" r="15" fill="none" strokeWidth="2.4" stroke="url(#g)"
              strokeDasharray="80 14" strokeLinecap="round">
              <animateTransform attributeName="transform" type="rotate"
                from="0 20 20" to="360 20 20" dur="9s" repeatCount="indefinite" />
            </circle>
            <circle cx="35" cy="20" r="2.6" fill="var(--chrome)">
              <animateTransform attributeName="transform" type="rotate"
                from="0 20 20" to="360 20 20" dur="9s" repeatCount="indefinite" />
            </circle>
          </svg>
          <div>
            <h1>Ouro<b>boros</b></h1>
            <div className="sub">Finds problems, fixes them, checks its own work</div>
          </div>
        </div>
        <div className={connClass}>
          <span className="led" />
          <span>{connText}</span>
        </div>
      </header>

      <section className="console">
        <Ring status={status} note={note} state={coreState} working={working} activePhase={activePhase} />
        <aside>
          <p className="lead">Autonomous incident response. No clicks needed.</p>

          <div className={'watch-panel' + (watchOn ? ' on' : '')}>
            <div className="watch-row">
              <span className="watch-led" />
              <span className="watch-label">Watch {watchOn ? 'ON' : 'OFF'}</span>
              <button className="watch-toggle" onClick={toggleWatch}>
                {watchOn ? 'Pause' : 'Resume'}
              </button>
            </div>
            <div className="watch-note">{watchNote}</div>
          </div>
        </aside>
      </section>

      {connected === false && (
        <div className="offline">
          ⚠ Can't reach the backend. Start it with{' '}
          <code>source .venv/bin/activate &amp;&amp; make trigger</code>.
        </div>
      )}

      {pending.map((item) => (
        <ApprovalCard
          key={item.id}
          item={item}
          onApprove={onApprove}
          onReject={onReject}
          busy={busyId === item.id}
        />
      ))}

      <StatStrip s={summary} />

      <Timeline events={events} />

      <footer>
        <span>OUROBOROS · "Agents of SigNoz" · Track 01 — AI &amp; Agent Observability</span>
        <span>{clock}</span>
      </footer>
      </div>
  )
}
