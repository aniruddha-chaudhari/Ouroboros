const PHASES = ['Diagnose', 'Decide', 'Act', 'Verify']

// The centerpiece: a rotating ring cycling DIAGNOSE → DECIDE → ACT → VERIFY,
// with the live health orb and status in the core. What each step means is
// spelled out in the <Legend> next to it, not crammed onto the ring itself —
// there isn't room here to render a full sentence without it overlapping the
// ring graphic or the center panel.
export default function Ring({ status, note, state, working, activePhase }) {
  return (
    <div className={'ringstage' + (working ? ' working' : '')}>
      <div className="ring" />
      <div className="sweep" />
      {PHASES.map((label, i) => (
        <div key={i} className={`phase p${i}${working && activePhase === i ? ' on' : ''}`}>
          {label}
        </div>
      ))}
      <div className={'core ' + state}>
        <div className="orb" />
        <div className="status">{status}</div>
        <div className="statusnote">{note}</div>
      </div>
    </div>
  )
}
