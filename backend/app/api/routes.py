from fastapi import APIRouter, Query
from datetime import datetime, timedelta, timezone
from typing import Literal
from pydantic import BaseModel, Field, model_validator
from app.services.chat import RoamlyChatService
from app.services.osm import OpenStreetMapService
from app.services.reality import RealityService
from app.services.weather import WeatherService
from app.services.preferences import PreferenceService
from app.services.routing import SmartRouteService
from app.services.place_intelligence import FEATURE_TYPES, PlaceIntelligenceService

router = APIRouter(prefix="/api", tags=["maps"])
maps = OpenStreetMapService()
chat = RoamlyChatService()
reality = RealityService()
weather = WeatherService()
preferences = PreferenceService()
smart_routes = SmartRouteService()
place_intelligence = PlaceIntelligenceService()


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=1000)
    lat: float
    lng: float
    trip_context: dict = Field(default_factory=dict)


class RealityQuestion(BaseModel):
    question: str = Field(min_length=1, max_length=1000)


class UserPreferencesRequest(BaseModel):
    preferred_categories: list[str] = Field(default_factory=list)
    preferred_transport_mode: str = "DRIVE"
    situation_defaults: dict = Field(default_factory=dict)


class SmartRouteRequest(BaseModel):
    origin_lat: float
    origin_lng: float
    destination_lat: float
    destination_lng: float
    mode: Literal["DRIVE", "WALK", "BICYCLE", "TRANSIT"] = "DRIVE"
    trip_context: dict = Field(default_factory=dict)
    preferences: dict = Field(default_factory=dict)


class ReportVerificationRequest(BaseModel):
    verifier_id: str | None = None
    verdict: Literal["confirm", "dispute"]


class AlertCheckRequest(BaseModel):
    origin_lat: float
    origin_lng: float
    destination_lat: float
    destination_lng: float
    destination_place_id: str | None = None
    trip_context: dict = Field(default_factory=dict)


class PlaceFeatureRequest(BaseModel):
    place_id: str
    feature_type: str
    details: str = Field(min_length=3, max_length=2000)
    source_kind: Literal["official", "partner", "community"] = "community"
    confidence: float = Field(default=.5, ge=0, le=1)
    observed_at: datetime | None = None
    expires_at: datetime | None = None
    metadata: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_feature(self):
        if self.feature_type not in FEATURE_TYPES: raise ValueError("Unsupported feature type")
        self.observed_at = self.observed_at or datetime.now(timezone.utc)
        return self


class IntelligenceRequest(BaseModel):
    question: str = Field(default="What can I actually do here?", max_length=1000)
    trip_context: dict = Field(default_factory=dict)


class RealityReportRequest(BaseModel):
    place_id: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    category: Literal["accessibility", "entrance", "elevator", "facility", "road_closure", "flooding", "sidewalk", "construction", "temporary_closure", "parking", "public_facility", "traffic_light", "crowding", "local_problem"]
    content: str = Field(min_length=5, max_length=3000)
    source_kind: Literal["user_report", "official", "partner"] = "user_report"
    reported_at: datetime | None = None
    expires_at: datetime | None = None
    confidence: float = Field(default=.5, ge=0, le=1)
    metadata: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_location_and_dates(self):
        if not self.place_id and (self.latitude is None or self.longitude is None):
            raise ValueError("A place_id or latitude/longitude is required")
        self.reported_at = self.reported_at or datetime.now(timezone.utc)
        self.expires_at = self.expires_at or self.reported_at + timedelta(days=1)
        if self.expires_at <= self.reported_at:
            raise ValueError("expires_at must be after reported_at")
        return self


@router.get("/places/nearby")
async def nearby_places(lat: float, lng: float, type: str | None = None, radius: float = Query(1500, ge=100, le=50000)):
    return {"places": await maps.nearby(lat, lng, type, radius)}


@router.get("/places/search")
async def search_places(query: str, lat: float | None = None, lng: float | None = None):
    return {"places": await maps.search(query, lat, lng)}


@router.get("/places/{place_id}")
async def place_details(place_id: str):
    return await maps.details(place_id)


@router.get("/routes")
async def directions(origin_lat: float, origin_lng: float, destination_lat: float, destination_lng: float, mode: str = "DRIVE"):
    return await maps.route(origin_lat, origin_lng, destination_lat, destination_lng, mode)


@router.post("/routes/smart")
async def smart_directions(request: SmartRouteRequest):
    return await smart_routes.recommend(**request.model_dump())


@router.post("/chat")
async def chat_with_roamly(request: ChatRequest):
    return await chat.reply(request.message, request.lat, request.lng, request.trip_context)


@router.get("/weather")
async def current_weather(lat: float, lng: float):
    return await weather.forecast(lat, lng)


@router.get("/users/{user_id}/preferences")
async def get_preferences(user_id: str):
    return preferences.get(user_id)


@router.put("/users/{user_id}/preferences")
async def save_preferences(user_id: str, request: UserPreferencesRequest):
    return preferences.save(user_id, request.model_dump())


@router.post("/reality/places/{place_id}/answer")
async def reality_place_answer(place_id: str, request: RealityQuestion):
    return await reality.answer_place_question(place_id, request.question)


@router.post("/reality/reports", status_code=201)
async def create_reality_report(request: RealityReportRequest):
    return await reality.create_report(request.model_dump())


@router.post("/reality/reports/{report_id}/verify")
async def verify_reality_report(report_id: str, request: ReportVerificationRequest):
    return reality.verify(report_id, request.verifier_id, request.verdict)


@router.post("/alerts/check")
async def check_proactive_alerts(request: AlertCheckRequest):
    alerts = reality.route_alerts(**request.model_dump())
    return {"alerts": alerts, "message": "New or active reports may affect your route or destination. Review evidence before changing plans." if alerts else "No active relevant reports were found. This does not guarantee conditions are clear."}


@router.post("/places/{place_id}/intelligence")
async def get_place_intelligence(place_id: str, request: IntelligenceRequest):
    return await place_intelligence.get(place_id, request.question, request.trip_context)


@router.post("/place-features", status_code=201)
async def create_place_feature(request: PlaceFeatureRequest):
    return place_intelligence.create(request.model_dump())
