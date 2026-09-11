import json
import re
import httpx
from fastapi import HTTPException
from app.core.config import get_settings

ALLOWED_TYPES = ["restaurant", "cafe", "grocery_store", "pharmacy", "hospital", "public_bathroom", "parking", "atm"]
CONTEXT_SIGNALS = ["senior_companion", "stroller", "wheelchair", "avoid_stairs", "low_walking", "in_a_hurry", "night_travel", "needs_rest"]
SCHEMA = {"name": "roamly_place_intent", "strict": True, "schema": {"type": "object", "properties": {"types": {"type": "array", "items": {"type": "string", "enum": ALLOWED_TYPES}}, "query": {"type": "string"}, "open_now": {"type": "boolean"}, "intent_kind": {"type": "string", "enum": ["place_search", "walking_advice"]}, "context_signals": {"type": "array", "items": {"type": "string", "enum": CONTEXT_SIGNALS}}}, "required": ["types", "query", "open_now", "intent_kind", "context_signals"], "additionalProperties": False}}
INSTRUCTIONS = "You extract a local-place search intent for Roamly using the supplied weather and temporary trip context. Return only JSON. Do not provide locations, ratings, distances, opening hours, accessibility facts, recommendations, or factual claims. Extract only new temporary situation signals explicitly stated by the user. Types must be from the supplied schema. Use open_now only when explicitly requested. If the user asks whether it is a good time to walk, use walking_advice. For broad rain-related place requests, prefer indoor types such as cafe, restaurant, grocery_store, pharmacy, or hospital when appropriate."


class AIIntentService:
    def __init__(self):
        self.settings = get_settings()

    async def parse(self, message: str, weather: dict | None = None, trip_context: dict | None = None) -> dict:
        if not message.strip():
            raise HTTPException(422, "A message is required")
        provider = self.settings.ai_provider.lower()
        if provider == "gemini":
            try:
                result = await self._gemini(message, weather, trip_context)
            except Exception:
                if self.settings.ai_fallback_provider.lower() == "openrouter":
                    try:
                        result = await self._openrouter(message, weather, trip_context)
                    except Exception:
                        result = self._heuristic(message, weather)
                else:
                    result = self._heuristic(message, weather)
        elif provider == "openrouter":
            try:
                result = await self._openrouter(message, weather, trip_context)
            except Exception:
                result = self._heuristic(message, weather)
        else:
            result = self._heuristic(message, weather)
        return self._validate(result, message)

    async def _gemini(self, message: str, weather: dict | None, trip_context: dict | None) -> dict:
        if not self.settings.gemini_api_key:
            raise HTTPException(503, "GEMINI_API_KEY is not configured")
        payload = {"system_instruction": {"parts": [{"text": INSTRUCTIONS}]}, "contents": [{"parts": [{"text": f"Weather context: {json.dumps(weather)}\nTemporary trip context: {json.dumps(trip_context)}\nUser request: {message}"}]}], "generationConfig": {"responseMimeType": "application/json", "responseJsonSchema": SCHEMA["schema"]}}
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.settings.gemini_model}:generateContent?key={self.settings.gemini_api_key}"
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(url, json=payload)
        if response.is_error:
            raise HTTPException(502, "AI intent service could not process this request")
        data = response.json()
        parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
        text = ""
        for part in parts:
            if "text" in part:
                text = part["text"]
                break
        if not text:
            raise HTTPException(502, "No text in Gemini response")
        return json.loads(text)

    async def _openrouter(self, message: str, weather: dict | None, trip_context: dict | None) -> dict:
        if not self.settings.openrouter_api_key:
            raise HTTPException(503, "OPENROUTER_API_KEY is not configured")
        schema = SCHEMA["schema"]
        context = f"Weather context: {json.dumps(weather)}\nTemporary trip context: {json.dumps(trip_context)}\nUser request: {message}"
        payload = {"model": self.settings.openrouter_model, "messages": [{"role": "system", "content": INSTRUCTIONS}, {"role": "user", "content": context}], "response_format": {"type": "json_schema", "json_schema": {"name": SCHEMA["name"], "strict": True, "schema": schema}}}
        headers = {"Authorization": f"Bearer {self.settings.openrouter_api_key}", "Content-Type": "application/json", "HTTP-Referer": self.settings.openrouter_app_url, "X-Title": self.settings.openrouter_app_name}
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post("https://openrouter.ai/api/v1/chat/completions", json=payload, headers=headers)
        if response.is_error:
            raise HTTPException(502, "AI intent service could not process this request")
        return json.loads(response.json()["choices"][0]["message"]["content"])

    @staticmethod
    def _heuristic(message: str, weather: dict | None) -> dict:
        text = message.lower()
        mapping = {"restaurant": ["food", "eat", "restaurant", "dinner", "lunch"], "cafe": ["cafe", "coffee"], "grocery_store": ["grocery", "supermarket"], "pharmacy": ["pharmacy", "medicine", "medication"], "hospital": ["hospital", "clinic"], "public_bathroom": ["washroom", "bathroom", "toilet", "restroom"], "parking": ["parking"], "atm": ["atm", "cash machine"]}
        types = [place_type for place_type, words in mapping.items() if any(word in text for word in words)]
        walking = "walk" in text or "walking" in text
        rain_request = any(word in text for word in ["rain", "raining", "wet"]) or (bool(weather and weather.get("is_precipitating")) and any(word in text for word in ["where should i go", "nearby"]))
        if rain_request and not types and not walking: types = ["cafe", "restaurant"]
        signals = []
        signal_words = {"senior_companion": ["grandmother", "grandma", "elderly", "senior"], "stroller": ["stroller", "pushchair", "pram"], "wheelchair": ["wheelchair"], "avoid_stairs": ["no stairs", "avoid stairs", "don't want stairs"], "low_walking": ["don't want to walk much", "less walking", "cannot walk far"], "in_a_hurry": ["in a hurry", "quickly", "urgent"], "night_travel": ["at night", "travelling at night", "traveling at night"], "needs_rest": ["somewhere to rest", "need to rest", "rest area"]}
        for signal, words in signal_words.items():
            if any(word in text for word in words): signals.append(signal)
        return {"types": types, "query": "places nearby" if not types else "", "open_now": bool(re.search(r"open (right )?now|currently open", text)), "intent_kind": "walking_advice" if walking else "place_search", "context_signals": signals}

    @staticmethod
    def _validate(intent: dict, message: str) -> dict:
        types = [item for item in intent.get("types", []) if item in ALLOWED_TYPES]
        query = str(intent.get("query", "")).strip()[:160] or ("places nearby" if not types else "")
        signals = [signal for signal in intent.get("context_signals", []) if signal in CONTEXT_SIGNALS]
        return {"types": types, "query": query, "open_now": bool(intent.get("open_now", False)), "intent_kind": intent.get("intent_kind") if intent.get("intent_kind") in {"place_search", "walking_advice"} else "place_search", "context_signals": signals, "original_message": message}
