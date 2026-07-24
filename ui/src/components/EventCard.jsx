import { fmtTime } from '../api.js'

// Per-outcome presentation for a remediation card: dot color, tag text, and the
// result chip. Keeps the timeline honest — a "checked, nothing wrong" run no
// longer masquerades as a "fix applied".
const OUTCOME = {
  healed: { dot: 'var(--acid)', tag: 'fix applied', chip: 'good', result: '✓ fixed' },
  no_action: { dot: 'var(--cyan)', tag: 'checked', chip: 'good', result: '✓ all good' },
  held: { dot: 'var(--amber)', tag: 'needs review', chip: 'warn', result: '⚠ needs a human' },
  failed: { dot: 'var(--red)', tag: 'fix failed', chip: 'bad', result: '✗ not fixed' },
}

const TYPE = {
  alert: { dot: 'var(--amber)', label: 'problem detected' },
  auto_detected: { dot: 'var(--amber)', label: 'auto-detected' },
  manual_trigger: { dot: 'var(--cyan)', label: 'check started' },
  remediation: { dot: 'var(--acid)', label: 'result' },
  proposed: { dot: 'var(--amber)', label: 'approval requested' },
  approved: { dot: 'var(--acid)', label: 'approved by human' },
  rejected: { dot: 'var(--muted)', label: 'rejected by human' },
}

function outcomeOf(detail) {
  if (detail.outcome && OUTCOME[detail.outcome]) return { key: detail.outcome, ...OUTCOME[detail.outcome] }
  // back-compat for events recorded before outcomes existed
  const healthy = (detail.recovery || {}).healthy
  return healthy === false
    ? { key: 'failed', ...OUTCOME.failed }
    : { key: 'healed', ...OUTCOME.healed }
}

function Remediation({ detail }) {
  const dec = detail.decision || {}
  const tok = dec._tokens || {}
  const conf = typeof dec.confidence === 'number' ? dec.confidence : null
  const o = outcomeOf(detail)
  const acted = dec.action && !['none', 'None', ''].includes(dec.action)
  const attempts = Array.isArray(detail.attempts) ? detail.attempts.length : 0
  return (
    <>
      {dec.diagnosis && <div className="diag">&ldquo;{dec.diagnosis}&rdquo;</div>}
      <div className="rowchips">
        <span className="chip">fix <b>{acted ? dec.action : 'none needed'}</b></span>
        {typeof dec._cost_usd === 'number' && <span className="chip">AI cost <b>${dec._cost_usd.toFixed(4)}</b></span>}
        {tok.in != null && <span className="chip">AI usage <b>{tok.in} in / {tok.out} out tokens</b></span>}
        {attempts > 1 && <span className="chip">took <b>{attempts} tries</b></span>}
        <span className={'chip ' + o.chip}>result <b>{o.result}</b></span>
      </div>
      {conf !== null && (
        <div className="conf">
          AI confidence
          <div className="bar"><i style={{ width: Math.round(conf * 100) + '%' }} /></div>
          {Math.round(conf * 100)}%
        </div>
      )}
    </>
  )
}

export default function EventCard({ ev, index }) {
  let meta = TYPE[ev.type] || { dot: 'var(--muted)', label: ev.type }
  // A remediation card takes its color + label from the run's outcome.
  if (ev.type === 'remediation' && ev.detail) {
    const o = outcomeOf(ev.detail)
    meta = { dot: o.dot, label: o.tag }
  }
  const hasDetail = ev.detail && Object.keys(ev.detail).length > 0
  const alertName =
    ev.detail && (ev.detail.alertname || (ev.detail.labels && ev.detail.labels.alertname))

  return (
    <div
      className="ev"
      style={{ '--dot': meta.dot, animationDelay: Math.min(index * 40, 400) + 'ms' }}
    >
      <div className="card">
        <div className="top">
          <span className="tag">{meta.label}</span>
          <span className="ts">{fmtTime(ev.ts)}</span>
        </div>

        {ev.type === 'remediation' && ev.detail && <Remediation detail={ev.detail} />}
        {ev.type === 'alert' && (
          <div className="headline">
            {alertName ? alertName : 'A problem was detected'} — starting a check
          </div>
        )}
        {ev.type === 'manual_trigger' && (
          <div className="headline">Check started manually</div>
        )}
        {ev.type === 'auto_detected' && (
          <div className="headline">Watchdog spotted a problem — investigating automatically</div>
        )}
        {ev.type === 'proposed' && (
          <div className="headline">
            Agent proposed <b>{ev.detail?.decision?.action || 'an action'}</b> — waiting for approval
          </div>
        )}
        {ev.type === 'approved' && (
          <div className="headline">You approved <b>{ev.detail?.action}</b> — running it now</div>
        )}
        {ev.type === 'rejected' && (
          <div className="headline">You rejected <b>{ev.detail?.action}</b> — no change made</div>
        )}

        {hasDetail && (
          <details className="raw">
            <summary>technical details</summary>
            <pre>{JSON.stringify(ev.detail, null, 2)}</pre>
          </details>
        )}
      </div>
    </div>
  )
}
