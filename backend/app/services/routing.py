from math import hypot
import psycopg
from fastapi import HTTPException
from app.core.config import get_settings
from app.db.adapter import get_db_adapter
from app.services.osm import OpenStreetMapService
from app.services.weather import WeatherService


class SmartRouteService:
    def __init__(self):
        self.settings, self.maps, self.weather = get_settings(), OpenStreetMapService(), WeatherService()
        self.db = get_db_adapter()

    def _conditions(self, origin_lat, origin_lng, dest_lat, dest_lng):
        return self.db.get_corridor_conditions(origin_lat, origin_lng, dest_lat, dest_lng)
    @staticmethod
    def _minutes(route): return max(1, round(float(route.get("duration", "0s").removesuffix("s")) / 60))
    def _score(self, route, context, preferences, conditions, mode, weather):
        minutes, meters = self._minutes(route), route.get("distanceMeters", 0)
        weights = {"time": 1.0, "distance": .002, "hazard": 0.0}
        if mode == "WALK": weights["distance"] = .006
        defaults = preferences.get("situation_defaults", preferences) if preferences else {}
        combined = {**defaults, **context}
        if combined.get("low_walking") or combined.get("wheelchair") or combined.get("senior_companion") or combined.get("stroller"): weights["distance"] *= 2.5
        if combined.get("in_a_hurry"): weights["time"] *= 2.5
        hazard_categories = {"flooding", "road_closure", "sidewalk", "local_problem", "temporary_closure"}
        hazards = [item for item in conditions if item["category"] in hazard_categories]
        weights["hazard"] = 20 if combined.get("wheelchair") or combined.get("avoid_stairs") or combined.get("stroller") else 8
        hazard_penalty = sum(item["confidence"] for item in hazards) * weights["hazard"]
        weather_penalty = 10 if mode == "WALK" and weather and weather.get("is_precipitating") else 0
        score = round(minutes * weights["time"] + meters * weights["distance"] + hazard_penalty + weather_penalty, 2)
        reasons = [f"{minutes} min", f"{round(meters / 1000, 1)} km"]
        if combined.get("low_walking") or combined.get("wheelchair"): reasons.append("walking distance weighted more heavily")
        if combined.get("in_a_hurry"): reasons.append("travel time weighted more heavily")
        if hazards: reasons.append(f"{len(hazards)} active Reality Layer condition(s) considered")
        if combined.get("avoid_stairs"): reasons.append("stairs cannot be verified from available route data")
        if weather_penalty: reasons.append("current rain considered for walking")
        return score, reasons
    async def recommend(self, origin_lat, origin_lng, destination_lat, destination_lng, mode, trip_context, preferences):
        raw = await self.maps.route(origin_lat, origin_lng, destination_lat, destination_lng, mode, alternatives=True)
        try: weather = await self.weather.forecast(origin_lat, origin_lng)
        except HTTPException: weather = None
        conditions = self._conditions(origin_lat, origin_lng, destination_lat, destination_lng)
        ranked = []
        for index, route in enumerate(raw.get("routes", [])):
            score, reasons = self._score(route, trip_context, preferences, conditions, mode.upper(), weather)
            ranked.append({
                "id": index,
                "duration": route.get("duration"),
                "distanceMeters": route.get("distanceMeters"),
                "polyline": route.get("polyline"),
                "steps": route.get("steps", []),
                "mode": mode.upper(),
                "labels": route.get("routeLabels", []),
                "score": score,
                "reasons": reasons
            })
        ranked.sort(key=lambda item: item["score"])
        for index, route in enumerate(ranked): route["recommended"] = index == 0
        explanation = "Recommended using deterministic weights for time, distance, and current verified-condition reports."
        return {"recommended": ranked[0] if ranked else None, "alternatives": ranked[1:], "all_routes": ranked, "conditions": conditions, "weather_considered": weather, "explanation": explanation}
