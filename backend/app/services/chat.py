from app.services.ai_intent import AIIntentService
from app.services.osm import OpenStreetMapService
from app.services.weather import WeatherService
from fastapi import HTTPException


class RoamlyChatService:
    def __init__(self):
        self.intent = AIIntentService()
        self.maps = OpenStreetMapService()
        self.weather = WeatherService()

    async def reply(self, message: str, latitude: float, longitude: float, trip_context: dict | None = None) -> dict:
        try:
            weather = await self.weather.forecast(latitude, longitude)
        except HTTPException:
            weather = None
        context = {**(trip_context or {})}
        intent = await self.intent.parse(message, weather, context)
        for signal in intent["context_signals"]:
            context[signal] = True
        if context.get("needs_rest") and not intent["types"]:
            intent["types"] = ["cafe"]
        if context.get("night_travel"):
            intent["open_now"] = True
        if intent["intent_kind"] == "walking_advice":
            message = weather["walk_advice"] if weather else "Live weather is unavailable, so I cannot assess walking conditions right now."
            return {"message": message, "intent": intent, "trip_context": context, "places": [], "weather": weather}
        searches = intent["types"] or [None]
        found = []
        radius = 1000 if context.get("low_walking") or context.get("in_a_hurry") else 3000
        for place_type in searches:
            results = await self.maps.nearby(latitude, longitude, place_type, radius) if place_type else await self.maps.search(intent["query"], latitude, longitude)
            found.extend(results)
        if intent["open_now"]:
            found = [place for place in found if place["isOpen"] is True]
        unique = {place["id"]: place for place in found if place.get("id")}
        places = list(unique.values())[:20]
        notes = []
        if radius < 3000: notes.append("I limited the search to a closer area for less walking or urgency.")
        if context.get("night_travel"): notes.append("Opening status is only applied when OpenStreetMap provides it; otherwise verify directly.")
        if context.get("wheelchair") or context.get("avoid_stairs") or context.get("stroller"):
            notes.append("Accessibility, entrances, and stairs are not verified by standard place results; use a Reality check for current local reports.")
        if places:
            weather_note = " Current rain was considered when selecting these place types." if weather and weather["is_precipitating"] else ""
            text = "I found places matching your request. Place details come from OpenStreetMap." + weather_note
        elif intent["open_now"]:
            text = "I couldn't find matching places currently marked open in this area."
        else:
            text = "I couldn't find matching places in this area. Try a broader request."
        return {"message": text, "intent": intent, "trip_context": context, "context_notes": notes, "places": places, "weather": weather}
