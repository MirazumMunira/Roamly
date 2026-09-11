import { useEffect } from 'react'
import { CircleMarker, MapContainer, Marker, Polyline, TileLayer, Tooltip, useMap } from 'react-leaflet'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'

const fallbackCenter = [23.8103, 90.4125]

const createPinIcon = (isSelected, isBest) => new L.DivIcon({
  className: `roamly-map-pin ${isSelected ? 'selected' : ''} ${isBest ? 'best' : ''}`,
  html: `<div class="pin-badge ${isSelected ? 'active-pin' : ''}">
    <span>${isSelected ? '📍' : '●'}</span>
  </div>`,
  iconSize: [28, 28],
  iconAnchor: [14, 28]
})

function ViewController({ userLocation, selectedPlace, routePoints, places }) {
  const map = useMap()

  useEffect(() => {
    if (userLocation && selectedPlace?.location) {
      const bounds = L.latLngBounds([
        [userLocation.lat, userLocation.lng],
        [selectedPlace.location.latitude, selectedPlace.location.longitude]
      ])
      if (routePoints && routePoints.length > 0) {
        routePoints.forEach(pt => bounds.extend(pt))
      }
      map.fitBounds(bounds, { padding: [50, 50], maxZoom: 16 })
    } else if (userLocation && places && places.length > 0) {
      const bounds = L.latLngBounds([[userLocation.lat, userLocation.lng]])
      places.forEach(p => {
        if (p.location) bounds.extend([p.location.latitude, p.location.longitude])
      })
      map.fitBounds(bounds, { padding: [40, 40], maxZoom: 15 })
    } else if (userLocation) {
      map.setView([userLocation.lat, userLocation.lng], 15)
    }
  }, [map, userLocation, selectedPlace, routePoints, places])

  return null
}

export default function MapView({ userLocation, places, selectedPlace, route, onSelect }) {
  const routePoints = route?.polyline?.geoJson?.coordinates?.map(([lng, lat]) => [lat, lng]) || []

  return (
    <MapContainer
      center={userLocation ? [userLocation.lat, userLocation.lng] : fallbackCenter}
      zoom={userLocation ? 15 : 12}
      className="h-full w-full"
      zoomControl
    >
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      <ViewController
        userLocation={userLocation}
        selectedPlace={selectedPlace}
        routePoints={routePoints}
        places={places}
      />

      {/* User Location */}
      {userLocation && (
        <CircleMarker
          center={[userLocation.lat, userLocation.lng]}
          radius={8}
          pathOptions={{ color: '#ffffff', weight: 3, fillColor: '#2563eb', fillOpacity: 1 }}
        >
          <Tooltip permanent direction="top" offset={[0, -10]} className="user-tooltip">
            You are here
          </Tooltip>
        </CircleMarker>
      )}

      {/* Place Markers */}
      {places.filter(place => place.location).map((place, idx) => {
        const isSelected = selectedPlace?.id === place.id
        const isBest = idx === 0
        return (
          <Marker
            key={place.id}
            position={[place.location.latitude, place.location.longitude]}
            icon={createPinIcon(isSelected, isBest)}
            eventHandlers={{ click: () => onSelect(place) }}
          >
            <Tooltip permanent={isSelected} direction="top" offset={[0, -20]}>
              <div style={{ fontWeight: isSelected ? '700' : '500' }}>
                {isBest && !isSelected && '⭐ '}
                {place.name}
              </div>
            </Tooltip>
          </Marker>
        )
      })}

      {/* OSRM route polyline */}
      {routePoints.length > 0 && (
        <>
          {/* Casing / Shadow */}
          <Polyline
            positions={routePoints}
            pathOptions={{ color: '#1e3a8a', weight: 8, opacity: 0.3 }}
          />
          {/* Main Route Line */}
          <Polyline
            positions={routePoints}
            pathOptions={{ color: '#2563eb', weight: 5, opacity: 0.95 }}
          />
        </>
      )}
    </MapContainer>
  )
}
