import { useCallback, useEffect, useState } from 'react'
import { chatWithRoamly, checkAlerts, createCommunityReport, findNearby, getPlaceIntelligence, getSmartRoute, getWeather, realityCheck, verifyCommunityReport } from './api'
import MapView from './components/MapView'
import PlaceCard from './components/PlaceCard'

const categories = [
  ['Food', 'restaurant', '🍔'],
  ['Cafes', 'cafe', '☕'],
  ['Grocery', 'grocery_store', '🛒'],
  ['Pharmacy', 'pharmacy', '💊'],
  ['Hospitals', 'hospital', '🏥'],
  ['Washrooms', 'public_bathroom', '🚻'],
  ['Parking', 'parking', '🅿️'],
  ['ATMs', 'atm', '🏧']
]

const contextOptions = [
  ['senior_companion', '👴 With a senior'],
  ['stroller', '👶 Stroller'],
  ['wheelchair', '♿ Wheelchair'],
  ['avoid_stairs', '🚫 Avoid stairs'],
  ['low_walking', '👣 Less walking'],
  ['in_a_hurry', '⚡ In a hurry'],
  ['night_travel', '🌙 At night'],
  ['needs_rest', '🪑 Need rest']
]

const transportModes = [
  ['WALK', '🚶 Walking'],
  ['DRIVE', '🚗 Driving'],
  ['BICYCLE', '🚲 Cycling']
]

const demoPrompt = "I'm new here. It's raining, I'm with my grandmother, we need food and a washroom, she can't walk much, and I don't want stairs."

const formatDuration = (value) => {
  if (!value) return ''
  const sec = Number(String(value).replace('s', ''))
  const min = Math.round(sec / 60)
  if (min < 60) return `${min} min`
  const hrs = Math.floor(min / 60)
  const remMin = min % 60
  return `${hrs} hr ${remMin} min`
}

const formatDistance = (meters) => {
  if (!meters) return ''
  if (meters < 1000) return `${Math.round(meters)} m`
  return `${(meters / 1000).toFixed(1)} km`
}

export default function App() {
  const [location, setLocation] = useState(null)
  const [places, setPlaces] = useState([])
  const [selected, setSelected] = useState(null)
  const [route, setRoute] = useState(null)
  const [routePlan, setRoutePlan] = useState(null)
  const [transportMode, setTransportMode] = useState('WALK')
  const [showSteps, setShowSteps] = useState(true)
  const [query, setQuery] = useState('')
  const [status, setStatus] = useState('Finding your location...')
  const [reply, setReply] = useState('Ask what you can actually do nearby...')
  const [reality, setReality] = useState(null)
  const [intelligence, setIntelligence] = useState(null)
  const [weather, setWeather] = useState(null)
  const [tripContext, setTripContext] = useState({})
  const [alerts, setAlerts] = useState([])
  const [reportType, setReportType] = useState('local_problem')
  const [reportText, setReportText] = useState('')
  const [loading, setLoading] = useState(false)

  // Get current browser position
  useEffect(() => {
    if (!navigator.geolocation) {
      setStatus('Location is unavailable in this browser.')
      return
    }
    navigator.geolocation.getCurrentPosition(
      ({ coords }) => {
        setLocation({ lat: coords.latitude, lng: coords.longitude })
        setStatus('Ready • Location detected')
      },
      () => {
        // Fallback default (London center) if permission is denied
        setLocation({ lat: 51.5074, lng: -0.1278 })
        setStatus('Default location set (London)')
      },
      { enableHighAccuracy: true, timeout: 10000 }
    )
  }, [])

  // Fetch local weather when location is established
  useEffect(() => {
    if (location) {
      getWeather(location.lat, location.lng).then(setWeather).catch(() => setWeather(null))
    }
  }, [location])

  // Periodic alert check for selected place
  useEffect(() => {
    if (!location || !selected?.location) return undefined
    const poll = () => {
      checkAlerts({
        origin_lat: location.lat,
        origin_lng: location.lng,
        destination_lat: selected.location.latitude,
        destination_lng: selected.location.longitude,
        destination_place_id: selected.id,
        trip_context: tripContext
      }).then(data => setAlerts(data.alerts || [])).catch(() => {})
    }
    poll()
    const timer = setInterval(poll, 60000)
    return () => clearInterval(timer)
  }, [location, selected, tripContext])

  const clearSelection = () => {
    setSelected(null)
    setRoute(null)
    setRoutePlan(null)
    setReality(null)
    setIntelligence(null)
    setAlerts([])
  }

  const toggleContext = (key) => {
    setTripContext(curr => ({ ...curr, [key]: !curr[key] }))
  }

  // Select place and automatically calculate smart route + intelligence
  const selectPlace = useCallback(async (place, mode = transportMode, ctx = tripContext) => {
    setSelected(place)
    setReality(null)
    setIntelligence(null)
    setRoutePlan(null)

    if (location && place.location) {
      try {
        const [plan, intel] = await Promise.all([
          getSmartRoute(location, place.location, ctx, mode),
          getPlaceIntelligence(place.id, ctx)
        ])
        setRoutePlan(plan)
        setRoute(plan.recommended)
        setIntelligence(intel)
      } catch (err) {
        console.error('Route calculation error:', err)
        setRoute(null)
      }
    }
  }, [location, transportMode, tripContext])

  const changeTransportMode = async (newMode) => {
    setTransportMode(newMode)
    if (location && selected?.location) {
      try {
        const plan = await getSmartRoute(location, selected.location, tripContext, newMode)
        setRoutePlan(plan)
        setRoute(plan.recommended)
      } catch {
        // Keep current route on error
      }
    }
  }

  // Ask AI: Search places and auto-route to the best nearby match
  const ask = async (message, overrideContext) => {
    if (!location) {
      setReply('Please wait for location detection or allow location access.')
      return
    }
    setLoading(true)
    setStatus('Analyzing intent and searching nearby OpenStreetMap places...')
    try {
      const context = overrideContext || tripContext
      const result = await chatWithRoamly(message, location.lat, location.lng, context)
      const foundPlaces = result.places || []
      setPlaces(foundPlaces)
      const updatedContext = result.trip_context || context
      setTripContext(updatedContext)
      setReply([result.message, ...(result.context_notes || [])].join(' '))
      if (result.weather) setWeather(result.weather)

      if (foundPlaces.length > 0) {
        // Automatically select the closest matching place and calculate its OSRM route.
        setStatus(`Found ${foundPlaces.length} places • Best match selected`)
        await selectPlace(foundPlaces[0], transportMode, updatedContext)
      } else {
        clearSelection()
        setStatus('No matching places found')
      }
    } catch (error) {
      const detail = error.response?.data?.detail || 'Search failed. Please try again.'
      setStatus(detail)
      setReply(detail)
    } finally {
      setLoading(false)
    }
  }

  // Category browse: Search and auto-route to best place
  const browse = async (label, type) => {
    if (!location) return ask(`Find ${label}`)
    setLoading(true)
    setStatus(`Finding nearby ${label}...`)
    try {
      const results = await findNearby(location.lat, location.lng, type)
      setPlaces(results || [])
      setReply(`Here are the closest ${label.toLowerCase()} found nearby.`)
      if (results && results.length > 0) {
        setStatus(`${results.length} ${label.toLowerCase()} found • Best match selected`)
        await selectPlace(results[0], transportMode)
      } else {
        clearSelection()
        setStatus(`No nearby ${label.toLowerCase()} found`)
      }
    } catch (error) {
      setReply(error.response?.data?.detail || 'Search failed.')
    } finally {
      setLoading(false)
    }
  }

  const runDemo = () => {
    const demoContext = { senior_companion: true, low_walking: true, avoid_stairs: true, needs_rest: true }
    setTripContext(demoContext)
    ask(demoPrompt, demoContext)
  }

  const checkReality = async () => {
    if (!selected) return
    setLoading(true)
    try {
      setReality(await realityCheck(selected.id))
    } catch (error) {
      setReality({ error: error.response?.data?.detail || 'Reality Layer is unavailable.' })
    } finally {
      setLoading(false)
    }
  }

  const submitReport = async (event) => {
    event.preventDefault()
    if (!selected || !reportText.trim()) return
    setLoading(true)
    try {
      await createCommunityReport({
        place_id: selected.id,
        latitude: selected.location?.latitude,
        longitude: selected.location?.longitude,
        category: reportType,
        content: reportText,
        confidence: 0.5
      })
      setReportText('')
      setReply('Your report is recorded into the Reality Layer with active verification.')
      checkReality()
    } catch (error) {
      setReply(error.response?.data?.detail || 'Report could not be submitted.')
    } finally {
      setLoading(false)
    }
  }

  const verifyReport = async (id, verdict) => {
    try {
      const update = await verifyCommunityReport(id, verdict)
      setReality(current => current ? {
        ...current,
        reports: current.reports.map(r => r.id === id ? { ...r, confidence: update.confidence, verifications: update.verifications } : r)
      } : current)
    } catch {
      setReply('Verification could not be saved.')
    }
  }

  const chooseRoute = (candidate) => {
    setRoute(candidate)
    setRoutePlan(plan => ({
      ...plan,
      all_routes: plan.all_routes.map(item => ({ ...item, recommended: item.id === candidate.id }))
    }))
  }

  // Optional OpenStreetMap directions handoff; the route is already rendered in Roamly.
  const osmEngine = transportMode === 'WALK' ? 'fossgis_osrm_foot' : transportMode === 'BICYCLE' ? 'fossgis_osrm_bike' : 'fossgis_osrm_car'
  const osmDirectionsUrl = location && selected?.location
    ? `https://www.openstreetmap.org/directions?engine=${osmEngine}&route=${location.lat}%2C${location.lng}%3B${selected.location.latitude}%2C${selected.location.longitude}`
    : '#'

  return (
    <main className="app-shell">
      <aside className="sidebar">
        {/* Brand */}
        <div className="brand">
          <span>R</span>
          <div>
            ROAMLY
            <small>AI City Companion & Directions</small>
          </div>
        </div>

        {/* Demo button */}
        <button className="demo-button" onClick={runDemo}>
          ✨ Run the accessibility & rain demo
        </button>

        {/* Status */}
        <div className="location-status">
          <i />
          <span>{status}</span>
        </div>

        {/* Proactive alert banner */}
        {alerts.length > 0 && (
          <div className="alert-banner">
            <b>⚠️ Active route/destination conditions</b>
            {alerts.map(alert => (
              <span key={alert.id}>
                • {alert.category.replace('_', ' ')}: {alert.content} ({Math.round(alert.confidence * 100)}% verified)
              </span>
            ))}
          </div>
        )}

        {/* Weather widget */}
        {weather && (
          <section className="weather-card">
            <div>
              <p className="section-label">LIVE WEATHER</p>
              <b>{weather.current?.temperature_c ?? '--'}°C</b>
              <span>{weather.current?.condition}</span>
            </div>
            <div className="weather-detail">
              Feels {weather.current?.feels_like_c ?? '--'}°C<br />
              {weather.current?.precipitation_mm ?? 0} mm rain
            </div>
            <small>
              {weather.next_hours?.[1]
                ? `Next hour: ${weather.next_hours[1].precipitation_probability}% precipitation chance`
                : 'Live Open-Meteo feed'}
            </small>
          </section>
        )}

        {/* Temporary Trip Context */}
        <section>
          <p className="section-label">ACTIVE TRIP CRITERIA</p>
          <div className="context-chips">
            {contextOptions.map(([key, label]) => (
              <button
                className={tripContext[key] ? 'active' : ''}
                key={key}
                onClick={() => toggleContext(key)}
              >
                {label}
              </button>
            ))}
          </div>
        </section>

        {/* AI Assistant response */}
        <div className="assistant-bubble">
          <span>AI</span>
          <div>{reply}</div>
        </div>

        {/* Search / AI Query Box */}
        <form
          onSubmit={(e) => {
            e.preventDefault()
            if (query.trim()) {
              ask(query)
              setQuery('')
            }
          }}
          className="search-box"
        >
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Ask AI (e.g. Find quiet cafe with wifi)..."
          />
          <button aria-label="Search">➔</button>
        </form>

        {/* Category buttons */}
        <section>
          <p className="section-label">EXPLORE NEARBY</p>
          <div className="categories">
            {categories.map(([label, type, icon]) => (
              <button key={type} onClick={() => browse(label, type)}>
                <span>{icon} {label}</span>
              </button>
            ))}
          </div>
        </section>

        {/* Selected destination and OSRM directions panel */}
        {selected && (
          <section className="directions-panel">
            <div className="dest-header">
              <div>
                <span className="badge-best">⭐ SELECTED DESTINATION</span>
                <h3>{selected.name}</h3>
                <p className="dest-address">{selected.address || 'OpenStreetMap Location'}</p>
              </div>
              <button className="btn-close" onClick={clearSelection} title="Clear selection">✕</button>
            </div>

            {/* Transport mode selector tabs */}
            <div className="mode-tabs">
              {transportModes.map(([mKey, mLabel]) => (
                <button
                  key={mKey}
                  className={`mode-btn ${transportMode === mKey ? 'active' : ''}`}
                  onClick={() => changeTransportMode(mKey)}
                >
                  {mLabel}
                </button>
              ))}
            </div>

            {/* Route ETA / Distance Overview */}
            {route && (
              <div className="eta-banner">
                <div className="eta-main">
                  <span className="eta-time">{formatDuration(route.duration)}</span>
                  <span className="eta-dist">({formatDistance(route.distanceMeters)})</span>
                </div>
                <a
                  href={osmDirectionsUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="btn-osm-nav"
                >
                  ↗ Open in OpenStreetMap
                </a>
              </div>
            )}

            {/* Turn-by-Turn Directions list */}
            {route?.steps && route.steps.length > 0 && (
              <div className="steps-container">
                <button
                  className="steps-toggle"
                  onClick={() => setShowSteps(s => !s)}
                >
                  <span>📍 Turn-by-Turn Directions ({route.steps.length} steps)</span>
                  <span>{showSteps ? '▲' : '▼'}</span>
                </button>

                {showSteps && (
                  <div className="steps-list">
                    {route.steps.map((step, idx) => (
                      <div key={idx} className="step-item">
                        <span className="step-icon">
                          {step.icon === 'left' ? '↰' : step.icon === 'right' ? '↱' : step.icon === 'arrive' ? '🏁' : '↑'}
                        </span>
                        <div className="step-content">
                          <p className="step-instruction">{step.instruction}</p>
                          {step.distanceMeters > 0 && (
                            <span className="step-meta">{formatDistance(step.distanceMeters)}</span>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Alternative routes if available */}
            {routePlan?.all_routes?.length > 1 && (
              <div className="route-plan">
                <strong>Alternative route options:</strong>
                {routePlan.all_routes.map(cand => (
                  <button
                    className={cand.recommended ? 'chosen' : ''}
                    key={cand.id}
                    onClick={() => chooseRoute(cand)}
                  >
                    {cand.recommended ? '✓ Best Score: ' : 'Alternative: '}
                    {formatDuration(cand.duration)} • {formatDistance(cand.distanceMeters)}
                    <small style={{ display: 'block', marginTop: '2px', color: '#666' }}>
                      {cand.reasons?.join(' • ')}
                    </small>
                  </button>
                ))}
              </div>
            )}

            {/* Place Intelligence */}
            {intelligence && (
              <div className="intelligence-card">
                <strong>Verified Capabilities & Facilities</strong>
                {intelligence.features.map(f => (
                  <span key={f.id}>
                    • <b>{f.type.replace('_', ' ')}</b>: {f.details} <small>({f.source}, {Math.round(f.confidence * 100)}%)</small>
                  </span>
                ))}
                {intelligence.unknown_capabilities.length > 0 && (
                  <p>Not yet verified: {intelligence.unknown_capabilities.map(i => i.replace('_', ' ')).join(', ')}.</p>
                )}
                <small>{intelligence.evidence_note}</small>
              </div>
            )}

            {/* Action buttons */}
            <div className="action-row">
              <button className="btn-secondary" onClick={checkReality}>🔍 Reality check</button>
              <button className="btn-secondary" onClick={clearSelection}>Clear route</button>
            </div>

            {/* Reality check results */}
            {reality && (
              <div className={`reality-card ${reality.conflict ? 'conflict' : ''}`}>
                {reality.error || (
                  <>
                    <strong>{reality.conflict ? '⚠️ Status Conflict' : 'Reality Layer Verification'}</strong>
                    <p>{reality.answer}</p>
                    {reality.reports?.map(report => (
                      <div className="report" key={report.id}>
                        <b>{report.category.replace('_', ' ')}</b>
                        <span>{report.content}</span>
                        <small>
                          {report.source} • {Math.round(report.confidence * 100)}% confidence • {report.freshness} • {report.verifications || 0} confirm(s)
                        </small>
                        <div style={{ marginTop: '4px' }}>
                          <button onClick={() => verifyReport(report.id, 'confirm')}>👍 Confirm</button>
                          <button onClick={() => verifyReport(report.id, 'dispute')}>👎 Dispute</button>
                        </div>
                      </div>
                    ))}
                  </>
                )}
              </div>
            )}

            {/* Report form */}
            <form className="report-form" onSubmit={submitReport}>
              <b>Report a local condition at this place</b>
              <select value={reportType} onChange={e => setReportType(e.target.value)}>
                <option value="accessibility">Accessibility barrier</option>
                <option value="elevator">Broken elevator</option>
                <option value="entrance">Blocked entrance</option>
                <option value="sidewalk">Sidewalk obstruction</option>
                <option value="flooding">Flooding / water hazard</option>
                <option value="temporary_closure">Temporary closure</option>
                <option value="public_facility">Closed washroom</option>
                <option value="parking">Full parking</option>
                <option value="crowding">Heavy crowding</option>
                <option value="local_problem">General local problem</option>
              </select>
              <input
                value={reportText}
                onChange={e => setReportText(e.target.value)}
                placeholder="Describe condition (e.g. ramp is blocked)..."
              />
              <button type="submit">Submit report</button>
            </form>
          </section>
        )}

        {/* All Nearby Places List */}
        <section className="results">
          <div className="flex items-center justify-between" style={{ marginBottom: '8px' }}>
            <p className="section-label" style={{ margin: 0 }}>
              NEARBY PLACES ({places.length})
            </p>
            {loading && <span className="text-xs text-emerald-600">Loading...</span>}
          </div>
          {places.length ? (
            places.map((place, index) => (
              <PlaceCard
                key={place.id}
                place={place}
                isBest={index === 0}
                active={selected?.id === place.id}
                onClick={() => selectPlace(place)}
              />
            ))
          ) : (
            <p className="empty">Select a category or ask AI to find places and get directions.</p>
          )}
        </section>
      </aside>

      {/* Map display */}
      <section className="map-area">
        <MapView
          userLocation={location}
          places={places}
          selectedPlace={selected}
          route={route}
          onSelect={selectPlace}
        />
        <div className="map-caption">
          {selected
            ? `🗺️ Route to ${selected.name} (${transportMode})`
            : 'Explore nearby places and directions'}
        </div>
      </section>
    </main>
  )
}
