export default function StatStrip({ s }) {
  return (
    <>
      <div className="stats-caption">Results from the most recent check</div>
      <section className="stats">
        <div className="stat">
          <div className="k">Status</div>
          <div className={'v sm ' + (s.degraded ? 'red' : 'acid')}>{s.health}</div>
        </div>
        <div className="stat">
          <div className="k">Fix applied</div>
          <div className="v sm">{s.action}</div>
        </div>
        <div className="stat">
          <div className="k">AI confidence</div>
          <div className="v">{s.confidence}</div>
        </div>
        <div className="stat">
          <div className="k">AI cost</div>
          <div className="v sm">{s.cost}</div>
        </div>
        <div className="stat">
          <div className="k">AI usage</div>
          <div className="v sm">{s.tokens}</div>
        </div>
      </section>
    </>
  )
}
