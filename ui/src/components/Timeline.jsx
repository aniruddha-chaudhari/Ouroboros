import EventCard from './EventCard.jsx'

export default function Timeline({ events }) {
  return (
    <>
      <div className="tl-head">
        <h2>History</h2>
        <span className="count">
          {events.length ? `${events.length} event${events.length > 1 ? 's' : ''}` : ''}
        </span>
      </div>
      <div className="timeline">
        {events.length === 0 ? (
          <div className="empty">
            <div className="big">Nothing has happened yet</div>
            <p>Click <b>▶ Check now</b> above to run the first check.</p>
          </div>
        ) : (
          [...events].reverse().map((ev, i) => (
            <EventCard key={`${ev.ts}-${i}`} ev={ev} index={i} />
          ))
        )}
      </div>
    </>
  )
}
