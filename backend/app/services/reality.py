import json
from datetime import datetime, timezone
from typing import Any
import psycopg
from fastapi import HTTPException
from app.core.config import get_settings
from app.db.adapter import get_db_adapter
from app.services.embeddings import EmbeddingService
from app.services.osm import OpenStreetMapService


class RealityService:
    def __init__(self):
        self.settings, self.embeddings, self.maps = get_settings(), EmbeddingService(), OpenStreetMapService()
        self.db = get_db_adapter()

    @staticmethod
    def _freshness(reported_at: datetime, expires_at: datetime) -> str:
        now = datetime.now(timezone.utc)
        if isinstance(reported_at, str):
            reported_at = datetime.fromisoformat(reported_at.replace("Z", "+00:00"))
        if isinstance(expires_at, str):
            expires_at = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        if reported_at.tzinfo is None: reported_at = reported_at.replace(tzinfo=timezone.utc)
        if expires_at.tzinfo is None: expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at <= now: return "expired"
        lifetime = max((expires_at - reported_at).total_seconds(), 1)
        remaining = (expires_at - now).total_seconds() / lifetime
        return "fresh" if remaining > .66 else "aging" if remaining > .25 else "stale_soon"

    async def create_report(self, report: dict[str, Any]) -> dict:
        embedding = await self.embeddings.embed(report["content"], "RETRIEVAL_DOCUMENT")
        try:
            return self.db.create_reality_report(report, embedding)
        except Exception as error:
            raise HTTPException(503, "Reality Layer database is unavailable") from error

    async def retrieve(self, query: str, place_id: str, limit: int = 6) -> list[dict]:
        embedding = await self.embeddings.embed(query, "RETRIEVAL_QUERY")
        try:
            reports = self.db.retrieve_reality_reports(place_id, embedding, limit)
            for r in reports:
                r["freshness"] = self._freshness(r["reported_at"], r["expires_at"])
            return reports
        except Exception as error:
            raise HTTPException(503, "Reality Layer database is unavailable") from error

    def verify(self, report_id: str, verifier_id: str | None, verdict: str) -> dict:
        try:
            res = self.db.verify_report(report_id, verifier_id, verdict)
        except Exception as error:
            raise HTTPException(503, "Report verification is unavailable") from error
        if not res: raise HTTPException(404, "Report not found")
        return res

    def route_alerts(self, origin_lat: float, origin_lng: float, destination_lat: float, destination_lng: float, destination_place_id: str | None, trip_context: dict) -> list[dict]:
        return self.db.route_alerts(origin_lat, origin_lng, destination_lat, destination_lng, destination_place_id, trip_context)

    async def answer_place_question(self, place_id: str, question: str) -> dict:
        place = await self.maps.details(place_id)
        reports = await self.retrieve(question, place_id)
        map_open = place.get("isOpen")
        map_statement = "OpenStreetMap does not provide a current opening status." if map_open is None else f"OpenStreetMap currently marks {place['name']} as {'open' if map_open else 'closed'}."
        closure_reports = [item for item in reports if item["category"] == "temporary_closure"]
        conflict = map_open is True and bool(closure_reports)
        if conflict: conclusion = "This conflicts with recent Reality Layer closure report(s); verify directly before visiting."
        elif reports: conclusion = "Relevant Reality Layer reports are listed below with their source, confidence, and freshness."
        else: conclusion = "No current Reality Layer reports were retrieved. This does not independently confirm the map status."
        return {"place": place, "map_status": map_open, "answer": f"{map_statement} {conclusion}", "conflict": conflict, "reports": reports}
