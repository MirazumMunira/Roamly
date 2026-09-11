import axios from 'axios'

const api = axios.create({ baseURL: '/api' })
export const findNearby = (lat, lng, type) => api.get('/places/nearby', { params: { lat, lng, type } }).then(r => r.data.places)
export const getRoute = (origin, destination, mode = 'WALK') => api.get('/routes', { params: { origin_lat: origin.lat, origin_lng: origin.lng, destination_lat: destination.latitude, destination_lng: destination.longitude, mode } }).then(r => r.data.routes?.[0])
export const getSmartRoute = (origin, destination, tripContext = {}, mode = 'WALK') => api.post('/routes/smart', { origin_lat: origin.lat, origin_lng: origin.lng, destination_lat: destination.latitude, destination_lng: destination.longitude, mode, trip_context: tripContext }).then(r => r.data)
export const chatWithRoamly = (message, lat, lng, tripContext = {}) => api.post('/chat', { message, lat, lng, trip_context: tripContext }).then(r => r.data)
export const realityCheck = (placeId, question = 'Is this place actually open and are there any current issues?') => api.post(`/reality/places/${placeId}/answer`, { question }).then(r => r.data)
export const getWeather = (lat, lng) => api.get('/weather', { params: { lat, lng } }).then(r => r.data)
export const createCommunityReport = report => api.post('/reality/reports', report).then(r => r.data)
export const verifyCommunityReport = (reportId, verdict) => api.post(`/reality/reports/${reportId}/verify`, { verdict }).then(r => r.data)
export const checkAlerts = payload => api.post('/alerts/check', payload).then(r => r.data)
export const getPlaceIntelligence = (placeId, tripContext) => api.post(`/places/${placeId}/intelligence`, { trip_context: tripContext }).then(r => r.data)
