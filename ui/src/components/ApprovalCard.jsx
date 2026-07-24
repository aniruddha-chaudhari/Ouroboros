const ACTION_LABEL = {
  restart_service: 'Restart the service',
  clear_latency: 'Roll back the latency config',
  clear_errors: 'Roll back the error config',
}

// A pending approval — the agent diagnosed a problem and recommends an action,
// but it's high-impact (or it wasn't confident enough), so it waits for a human.
// This is the "approval-gated" tier of the autonomy model.
export default function ApprovalCard({ item, onApprove, onReject, busy }) {
  const d = item.decision || {}
  const conf = typeof d.confidence === 'number' ? Math.round(d.confidence * 100) : null
  return (
    <div className="approval">
      <div className="approval-head">
        <span className="approval-badge">Approval needed</span>
        <span className="approval-sub">the agent wants to act — your call</span>
      </div>

      {d.diagnosis && <div className="approval-diag">&ldquo;{d.diagnosis}&rdquo;</div>}

      <div className="approval-action">
        <span className="approval-verb">Proposed fix</span>
        <b>{ACTION_LABEL[item.action] || item.action}</b>
        {conf !== null && <span className="approval-conf">· {conf}% confident</span>}
      </div>
      {item.reason && <div className="approval-reason">{item.reason}</div>}

      <div className="approval-actions">
        <button className="btn-approve" onClick={() => onApprove(item.id)} disabled={busy}>
          {busy ? 'Working…' : '✓ Approve & run'}
        </button>
        <button className="btn-reject" onClick={() => onReject(item.id)} disabled={busy}>
          ✕ Reject
        </button>
      </div>
    </div>
  )
}
