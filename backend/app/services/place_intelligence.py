import json
import psycopg
from fastapi import HTTPException
from app.core.config import get_settings
from app.db.adapter import get_db_adapter
from app.services.reality import RealityService

FEATURE_TYPES = {"department", "emergency_entrance", "entrance", "elevator", "gate", "internal_navigation", "bus_route", "accessible_stop", "lighting", "activity_level", "hazard", "accessible_parking", "parking_restriction", "parking_availability", "rest_seating", "quiet_area", "wifi", "charging", "changing_room", "washroom", "accessible_entrance"}

class PlaceIntelligenceService:
    def __init__(self):
        self.settings, self.reality = get_settings(), RealityService()
        self.db = get_db_adapter()

    def create(self, item):
        try:
            feat_id = self.db.create_place_feature(item)
            return {"id": feat_id}
        except Exception as error:
            raise HTTPException(503, "Place intelligence database is unavailable") from error

    async def get(self, place_id, question, trip_context):
        features = self.db.get_place_features(place_id)
        try:
            reports = await self.reality.retrieve(question, place_id)
        except Exception:
            reports = []
        wanted = []
        if trip_context.get("wheelchair") or trip_context.get("stroller") or trip_context.get("avoid_stairs"): wanted += ["elevator", "accessible_entrance", "washroom", "changing_room"]
        if trip_context.get("senior_companion") or trip_context.get("low_walking") or trip_context.get("needs_rest"): wanted += ["rest_seating", "washroom"]
        if trip_context.get("night_travel"): wanted += ["lighting", "activity_level", "hazard"]
        return {"features": features, "reports": reports, "requested_capabilities": list(dict.fromkeys(wanted)), "unknown_capabilities": [name for name in dict.fromkeys(wanted) if not any(item["type"] == name for item in features)], "evidence_note": "Features and reports are evidence with source, confidence, and freshness; missing evidence is not evidence of absence."}
