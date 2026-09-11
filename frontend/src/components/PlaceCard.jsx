export default function PlaceCard({ place, active, isBest, onClick }) {
  return (
    <button onClick={onClick} className={`place-card ${active ? 'active' : ''}`}>
      <span className="place-icon">{isBest ? '⭐' : '📍'}</span>
      <span className="min-w-0 text-left flex-1">
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', justifyContent: 'space-between' }}>
          <strong>{place.name}</strong>
          {isBest && <span className="badge-best-mini">Best Match</span>}
        </div>
        <small>{place.address || 'OpenStreetMap location'}</small>
        <span className="meta">
          {place.types && place.types.length > 0 && (
            <span style={{ textTransform: 'capitalize', color: '#166534' }}>
              {place.types[0].replace('_', ' ')}
            </span>
          )}
          {place.isOpen !== null && place.isOpen !== undefined && (
            <span> • {place.isOpen ? '🟢 Open now' : '🔴 Closed'}</span>
          )}
        </span>
      </span>
    </button>
  )
}
