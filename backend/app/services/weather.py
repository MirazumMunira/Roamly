import httpx
from fastapi import HTTPException

WEATHER_CODES = {0: ("Clear sky", "clear"), 1: ("Mostly clear", "clear"), 2: ("Partly cloudy", "cloudy"), 3: ("Overcast", "cloudy"), 45: ("Fog", "fog"), 48: ("Rime fog", "fog"), 51: ("Light drizzle", "rain"), 53: ("Drizzle", "rain"), 55: ("Heavy drizzle", "rain"), 61: ("Light rain", "rain"), 63: ("Rain", "rain"), 65: ("Heavy rain", "rain"), 71: ("Light snow", "snow"), 73: ("Snow", "snow"), 75: ("Heavy snow", "snow"), 80: ("Rain showers", "rain"), 81: ("Rain showers", "rain"), 82: ("Violent rain showers", "rain"), 95: ("Thunderstorm", "storm"), 96: ("Thunderstorm with hail", "storm"), 99: ("Thunderstorm with hail", "storm")}


class WeatherService:
    async def forecast(self, latitude: float, longitude: float) -> dict:
        params = {"latitude": latitude, "longitude": longitude, "current": "temperature_2m,apparent_temperature,precipitation,rain,weather_code,wind_speed_10m", "hourly": "precipitation_probability,precipitation,weather_code", "forecast_days": 1, "timezone": "auto"}
        async with httpx.AsyncClient(timeout=12) as client:
            response = await client.get("https://api.open-meteo.com/v1/forecast", params=params)
        if response.is_error:
            raise HTTPException(502, "Weather service is unavailable")
        data = response.json(); current, hourly = data["current"], data["hourly"]
        label, condition = WEATHER_CODES.get(current["weather_code"], ("Unknown conditions", "unknown"))
        start = hourly["time"].index(current["time"]) if current["time"] in hourly["time"] else 0
        next_hours = [{"time": hourly["time"][index], "precipitation_probability": hourly["precipitation_probability"][index], "condition": WEATHER_CODES.get(hourly["weather_code"][index], ("Unknown", "unknown"))[0]} for index in range(start, min(start + 4, len(hourly["time"]))) ]
        rainy = condition in {"rain", "storm"} or current.get("precipitation", 0) > 0
        walk_advice = "Avoid walking outdoors if possible due to current storm conditions." if condition == "storm" else "Use rain protection and take care on wet surfaces." if rainy else "Conditions are generally suitable for walking; check the next-hour forecast before leaving."
        return {"source": "Open-Meteo", "current": {"time": current["time"], "temperature_c": current["temperature_2m"], "feels_like_c": current["apparent_temperature"], "condition": label, "condition_group": condition, "precipitation_mm": current["precipitation"], "wind_kph": current["wind_speed_10m"]}, "next_hours": next_hours, "is_precipitating": rainy, "walk_advice": walk_advice}
