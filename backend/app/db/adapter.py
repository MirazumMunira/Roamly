import json
import math
import os
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
import psycopg
from app.core.config import get_settings

DB_PATH = Path(__file__).resolve().parent.parent.parent / "roamly.db"

def cosine_similarity(v1: list[float], v2: list[float]) -> float:
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0
    dot = sum(a * b for a, b in zip(v1, v2))
    norm_a = math.sqrt(sum(a * a for a in v1))
    norm_b = math.sqrt(sum(b * b for b in v2))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)

def parse_iso(dt_str: Any) -> datetime:
    if isinstance(dt_str, datetime):
        if dt_str.tzinfo is None:
            return dt_str.replace(tzinfo=timezone.utc)
        return dt_str
    if not dt_str:
        return datetime.now(timezone.utc)
    try:
        dt = datetime.fromisoformat(str(dt_str).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return datetime.now(timezone.utc)


class DatabaseAdapter:
    _instance = None

    def __init__(self):
        self.settings = get_settings()
        self._use_postgres = None
        self._init_db()

    def is_postgres(self) -> bool:
        if self._use_postgres is not None:
            return self._use_postgres
        db_url = self.settings.database_url
        if db_url.startswith("sqlite"):
            self._use_postgres = False
            return False
        # Test connection to PostgreSQL
        try:
            conn_str = db_url.replace("postgresql+psycopg://", "postgresql://")
            with psycopg.connect(conn_str, connect_timeout=2) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
            self._use_postgres = True
            return True
        except Exception:
            self._use_postgres = False
            return False

    def _get_pg_conn(self):
        conn_str = self.settings.database_url.replace("postgresql+psycopg://", "postgresql://")
        return psycopg.connect(conn_str)

    def _get_sqlite_conn(self):
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        if not self.is_postgres():
            with self._get_sqlite_conn() as conn:
                cur = conn.cursor()
                cur.execute("""
                CREATE TABLE IF NOT EXISTS reality_reports (
                    id TEXT PRIMARY KEY,
                    place_id TEXT,
                    latitude REAL,
                    longitude REAL,
                    category TEXT NOT NULL,
                    content TEXT NOT NULL,
                    source_kind TEXT NOT NULL DEFAULT 'user_report',
                    reported_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    confidence REAL NOT NULL DEFAULT 0.50,
                    base_confidence REAL NOT NULL DEFAULT 0.50,
                    verification_count INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'active',
                    metadata TEXT NOT NULL DEFAULT '{}',
                    embedding TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """)
                cur.execute("""
                CREATE TABLE IF NOT EXISTS reality_report_verifications (
                    id TEXT PRIMARY KEY,
                    report_id TEXT NOT NULL,
                    verifier_id TEXT,
                    verdict TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE (report_id, verifier_id)
                )
                """)
                cur.execute("""
                CREATE TABLE IF NOT EXISTS place_features (
                    id TEXT PRIMARY KEY,
                    place_id TEXT NOT NULL,
                    feature_type TEXT NOT NULL,
                    details TEXT NOT NULL,
                    source_kind TEXT NOT NULL DEFAULT 'partner',
                    confidence REAL NOT NULL DEFAULT 0.50,
                    observed_at TEXT NOT NULL,
                    expires_at TEXT,
                    metadata TEXT NOT NULL DEFAULT '{}'
                )
                """)
                cur.execute("""
                CREATE TABLE IF NOT EXISTS user_preferences (
                    id TEXT PRIMARY KEY,
                    user_id TEXT UNIQUE NOT NULL,
                    preferred_categories TEXT NOT NULL DEFAULT '[]',
                    preferred_transport_mode TEXT NOT NULL DEFAULT 'DRIVE',
                    situation_defaults TEXT NOT NULL DEFAULT '{}',
                    updated_at TEXT NOT NULL
                )
                """)
                conn.commit()

    # --- Reality Reports ---

    def create_reality_report(self, report: dict[str, Any], embedding: list[float]) -> dict:
        now = datetime.now(timezone.utc)
        rep_at = report.get("reported_at") or now
        exp_at = report.get("expires_at") or (rep_at + (timedelta(days=1) if isinstance(rep_at, datetime) else 86400))
        if isinstance(rep_at, datetime):
            rep_at_iso = rep_at.isoformat()
        else:
            rep_at_iso = str(rep_at)
        if isinstance(exp_at, datetime):
            exp_at_iso = exp_at.isoformat()
        else:
            exp_at_iso = str(exp_at)

        conf = float(report.get("confidence", 0.5))
        meta = json.dumps(report.get("metadata", {}))

        if self.is_postgres():
            sql = """INSERT INTO reality_reports (place_id, latitude, longitude, category, content, source_kind, reported_at, expires_at, confidence, base_confidence, metadata, embedding)
                     VALUES (%(place_id)s, %(latitude)s, %(longitude)s, %(category)s, %(content)s, %(source_kind)s, %(reported_at)s, %(expires_at)s, %(confidence)s, %(confidence)s, %(metadata)s, %(embedding)s)
                     RETURNING id, reported_at, expires_at"""
            vector_str = "[" + ",".join(str(v) for v in embedding) + "]"
            payload = {
                **report,
                "metadata": meta,
                "embedding": vector_str,
                "reported_at": rep_at,
                "expires_at": exp_at,
                "confidence": conf
            }
            with self._get_pg_conn() as conn, conn.cursor() as cur:
                cur.execute(sql, payload)
                row = cur.fetchone()
                return {"id": str(row[0]), "reported_at": row[1], "expires_at": row[2]}

        # SQLite fallback
        rep_id = str(uuid.uuid4())
        created_at_iso = now.isoformat()
        embedding_json = json.dumps(embedding)
        sql = """INSERT INTO reality_reports
                 (id, place_id, latitude, longitude, category, content, source_kind, reported_at, expires_at, confidence, base_confidence, verification_count, status, metadata, embedding, created_at)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 'active', ?, ?, ?)"""
        with self._get_sqlite_conn() as conn:
            cur = conn.cursor()
            cur.execute(sql, (
                rep_id,
                report.get("place_id"),
                report.get("latitude"),
                report.get("longitude"),
                report.get("category"),
                report.get("content"),
                report.get("source_kind", "user_report"),
                rep_at_iso,
                exp_at_iso,
                conf,
                conf,
                meta,
                embedding_json,
                created_at_iso
            ))
            conn.commit()
        return {"id": rep_id, "reported_at": rep_at_iso, "expires_at": exp_at_iso}

    def retrieve_reality_reports(self, place_id: str, query_embedding: list[float], limit: int = 6) -> list[dict]:
        if self.is_postgres():
            vector_str = "[" + ",".join(str(v) for v in query_embedding) + "]"
            sql = """SELECT id, category, content, source_kind, reported_at, expires_at, confidence, verification_count,
                     1 - (embedding <=> %(embedding)s::vector) AS similarity
                     FROM reality_reports WHERE place_id = %(place_id)s AND status = 'active' AND expires_at > NOW()
                     ORDER BY embedding <=> %(embedding)s::vector LIMIT %(limit)s"""
            with self._get_pg_conn() as conn, conn.cursor() as cur:
                cur.execute(sql, {"embedding": vector_str, "place_id": place_id, "limit": limit})
                rows = cur.fetchall()
            return [
                {
                    "id": str(r[0]),
                    "category": r[1],
                    "content": r[2],
                    "source": r[3],
                    "reported_at": r[4],
                    "expires_at": r[5],
                    "confidence": float(r[6]),
                    "verifications": r[7],
                    "similarity": round(float(r[8]), 3),
                }
                for r in rows
            ]

        # SQLite retrieval
        now = datetime.now(timezone.utc)
        sql = """SELECT id, category, content, source_kind, reported_at, expires_at, confidence, verification_count, embedding
                 FROM reality_reports WHERE place_id = ? AND status = 'active'"""
        with self._get_sqlite_conn() as conn:
            cur = conn.cursor()
            cur.execute(sql, (place_id,))
            rows = cur.fetchall()

        scored = []
        for r in rows:
            exp_at = parse_iso(r["expires_at"])
            if exp_at <= now:
                continue
            emb = json.loads(r["embedding"]) if isinstance(r["embedding"], str) else r["embedding"]
            sim = cosine_similarity(query_embedding, emb)
            rep_at = parse_iso(r["reported_at"])
            scored.append({
                "id": str(r["id"]),
                "category": r["category"],
                "content": r["content"],
                "source": r["source_kind"],
                "reported_at": rep_at,
                "expires_at": exp_at,
                "confidence": float(r["confidence"]),
                "verifications": r["verification_count"],
                "similarity": round(sim, 3)
            })

        scored.sort(key=lambda x: x["similarity"], reverse=True)
        return scored[:limit]

    def verify_report(self, report_id: str, verifier_id: str | None, verdict: str) -> dict | None:
        if self.is_postgres():
            sql = """WITH vote AS (INSERT INTO reality_report_verifications (report_id, verifier_id, verdict) VALUES (%s, %s, %s)
                     ON CONFLICT (report_id, verifier_id) DO UPDATE SET verdict = EXCLUDED.verdict RETURNING verdict),
                     totals AS (SELECT COALESCE(SUM(CASE WHEN verdict='confirm' THEN 1 ELSE 0 END),0) confirms, COALESCE(SUM(CASE WHEN verdict='dispute' THEN 1 ELSE 0 END),0) disputes FROM reality_report_verifications WHERE report_id=%s)
                     UPDATE reality_reports r SET verification_count = (SELECT confirms + disputes FROM totals), confidence = LEAST(.95, GREATEST(.05, r.base_confidence + ((SELECT confirms - disputes FROM totals) * .08)))
                     WHERE r.id=%s RETURNING r.id, r.confidence, r.verification_count"""
            with self._get_pg_conn() as conn, conn.cursor() as cur:
                cur.execute(sql, (report_id, verifier_id or None, verdict, report_id, report_id))
                row = cur.fetchone()
                if not row:
                    return None
                return {"id": str(row[0]), "confidence": float(row[1]), "verifications": row[2]}

        # SQLite verification
        with self._get_sqlite_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT id, base_confidence FROM reality_reports WHERE id = ?", (report_id,))
            rep = cur.fetchone()
            if not rep:
                return None
            base_conf = float(rep["base_confidence"])

            # Vote upsert
            v_id = verifier_id or str(uuid.uuid4())
            now_iso = datetime.now(timezone.utc).isoformat()
            cur.execute("""
            INSERT INTO reality_report_verifications (id, report_id, verifier_id, verdict, created_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(report_id, verifier_id) DO UPDATE SET verdict = excluded.verdict
            """, (str(uuid.uuid4()), report_id, v_id, verdict, now_iso))

            # Count totals
            cur.execute("""
            SELECT
                COALESCE(SUM(CASE WHEN verdict='confirm' THEN 1 ELSE 0 END), 0) AS confirms,
                COALESCE(SUM(CASE WHEN verdict='dispute' THEN 1 ELSE 0 END), 0) AS disputes
            FROM reality_report_verifications WHERE report_id = ?
            """, (report_id,))
            totals = cur.fetchone()
            confirms = totals["confirms"]
            disputes = totals["disputes"]
            new_count = confirms + disputes
            new_confidence = min(0.95, max(0.05, base_conf + ((confirms - disputes) * 0.08)))

            cur.execute("""
            UPDATE reality_reports SET verification_count = ?, confidence = ? WHERE id = ?
            """, (new_count, new_confidence, report_id))
            conn.commit()
            return {"id": report_id, "confidence": round(new_confidence, 2), "verifications": new_count}

    def route_alerts(self, origin_lat: float, origin_lng: float, destination_lat: float, destination_lng: float, destination_place_id: str | None, trip_context: dict) -> list[dict]:
        lat_min, lat_max = sorted([origin_lat, destination_lat])
        lng_min, lng_max = sorted([origin_lng, destination_lng])
        padding = 0.008
        relevant = ["flooding", "road_closure", "sidewalk", "construction", "traffic_light", "local_problem", "entrance", "elevator", "parking", "crowding", "public_facility"]

        if self.is_postgres():
            sql = """SELECT id, category, content, confidence, verification_count, reported_at, expires_at, place_id
                     FROM reality_reports WHERE status='active' AND expires_at > NOW() AND category = ANY(%s)
                     AND (place_id = %s OR (latitude BETWEEN %s AND %s AND longitude BETWEEN %s AND %s))
                     ORDER BY reported_at DESC LIMIT 12"""
            try:
                with self._get_pg_conn() as conn, conn.cursor() as cur:
                    cur.execute(sql, (relevant, destination_place_id, lat_min-padding, lat_max+padding, lng_min-padding, lng_max+padding))
                    rows = cur.fetchall()
            except Exception:
                return []
            return self._build_alerts(rows, trip_context)

        # SQLite route alerts
        now = datetime.now(timezone.utc)
        placeholders = ",".join("?" for _ in relevant)
        sql = f"""SELECT id, category, content, confidence, verification_count, reported_at, expires_at, place_id
                  FROM reality_reports WHERE status='active' AND category IN ({placeholders})
                  AND (place_id = ? OR (latitude BETWEEN ? AND ? AND longitude BETWEEN ? AND ?))
                  ORDER BY reported_at DESC LIMIT 12"""
        params = [*relevant, destination_place_id, lat_min-padding, lat_max+padding, lng_min-padding, lng_max+padding]
        try:
            with self._get_sqlite_conn() as conn:
                cur = conn.cursor()
                cur.execute(sql, params)
                rows = cur.fetchall()
        except Exception:
            return []

        filtered_rows = []
        for r in rows:
            exp_at = parse_iso(r["expires_at"])
            if exp_at > now:
                filtered_rows.append((r["id"], r["category"], r["content"], r["confidence"], r["verification_count"], parse_iso(r["reported_at"]), exp_at, r["place_id"]))
        return self._build_alerts(filtered_rows, trip_context)

    @staticmethod
    def _build_alerts(rows: list, trip_context: dict) -> list[dict]:
        sensitive = {"wheelchair", "stroller", "avoid_stairs", "low_walking", "senior_companion"}
        alerts = []
        for row in rows:
            impact = "may affect your current destination or route area"
            if row[1] in {"entrance", "elevator", "sidewalk"} and any(trip_context.get(key) for key in sensitive):
                impact = "may be especially relevant to your active accessibility context"
            alerts.append({
                "id": str(row[0]),
                "category": row[1],
                "content": row[2],
                "confidence": float(row[3]),
                "verifications": row[4],
                "reported_at": row[5],
                "expires_at": row[6],
                "impact": impact,
                "evidence_note": "This is a time-limited community/partner report, not a safety guarantee."
            })
        return alerts

    def get_corridor_conditions(self, origin_lat: float, origin_lng: float, dest_lat: float, dest_lng: float) -> list[dict]:
        lat_min, lat_max = sorted([origin_lat, dest_lat])
        lng_min, lng_max = sorted([origin_lng, dest_lng])
        padding = 0.008

        if self.is_postgres():
            sql = """SELECT category, content, confidence FROM reality_reports
                     WHERE status='active' AND expires_at > NOW() AND latitude BETWEEN %s AND %s AND longitude BETWEEN %s AND %s"""
            try:
                with self._get_pg_conn() as conn, conn.cursor() as cur:
                    cur.execute(sql, (lat_min-padding, lat_max+padding, lng_min-padding, lng_max+padding))
                    return [{"category": r[0], "content": r[1], "confidence": float(r[2])} for r in cur.fetchall()]
            except Exception:
                return []

        # SQLite
        now = datetime.now(timezone.utc)
        sql = """SELECT category, content, confidence, expires_at FROM reality_reports
                 WHERE status='active' AND latitude BETWEEN ? AND ? AND longitude BETWEEN ? AND ?"""
        try:
            with self._get_sqlite_conn() as conn:
                cur = conn.cursor()
                cur.execute(sql, (lat_min-padding, lat_max+padding, lng_min-padding, lng_max+padding))
                results = []
                for r in cur.fetchall():
                    if parse_iso(r["expires_at"]) > now:
                        results.append({"category": r["category"], "content": r["content"], "confidence": float(r["confidence"])})
                return results
        except Exception:
            return []

    # --- Place Features ---

    def create_place_feature(self, item: dict[str, Any]) -> str:
        now = datetime.now(timezone.utc)
        obs_at = item.get("observed_at") or now
        exp_at = item.get("expires_at")
        meta = json.dumps(item.get("metadata", {}))

        if self.is_postgres():
            sql = """INSERT INTO place_features (place_id, feature_type, details, source_kind, confidence, observed_at, expires_at, metadata)
                     VALUES (%(place_id)s, %(feature_type)s, %(details)s, %(source_kind)s, %(confidence)s, %(observed_at)s, %(expires_at)s, %(metadata)s) RETURNING id"""
            payload = {**item, "metadata": meta, "observed_at": obs_at, "expires_at": exp_at}
            with self._get_pg_conn() as conn, conn.cursor() as cur:
                cur.execute(sql, payload)
                return str(cur.fetchone()[0])

        # SQLite
        feat_id = str(uuid.uuid4())
        obs_iso = obs_at.isoformat() if isinstance(obs_at, datetime) else str(obs_at)
        exp_iso = exp_at.isoformat() if isinstance(exp_at, datetime) else (str(exp_at) if exp_at else None)
        sql = """INSERT INTO place_features (id, place_id, feature_type, details, source_kind, confidence, observed_at, expires_at, metadata)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"""
        with self._get_sqlite_conn() as conn:
            cur = conn.cursor()
            cur.execute(sql, (
                feat_id,
                item["place_id"],
                item["feature_type"],
                item["details"],
                item.get("source_kind", "partner"),
                float(item.get("confidence", 0.5)),
                obs_iso,
                exp_iso,
                meta
            ))
            conn.commit()
        return feat_id

    def get_place_features(self, place_id: str) -> list[dict]:
        if self.is_postgres():
            sql = """SELECT id, feature_type, details, source_kind, confidence, observed_at, expires_at FROM place_features
                     WHERE place_id=%s AND (expires_at IS NULL OR expires_at > NOW()) ORDER BY observed_at DESC"""
            try:
                with self._get_pg_conn() as conn, conn.cursor() as cur:
                    cur.execute(sql, (place_id,))
                    rows = cur.fetchall()
            except Exception:
                rows = []
            return [
                {
                    "id": str(r[0]),
                    "type": r[1],
                    "details": r[2],
                    "source": r[3],
                    "confidence": float(r[4]),
                    "observed_at": r[5],
                    "expires_at": r[6]
                }
                for r in rows
            ]

        # SQLite
        now = datetime.now(timezone.utc)
        sql = """SELECT id, feature_type, details, source_kind, confidence, observed_at, expires_at FROM place_features
                 WHERE place_id=? ORDER BY observed_at DESC"""
        try:
            with self._get_sqlite_conn() as conn:
                cur = conn.cursor()
                cur.execute(sql, (place_id,))
                rows = cur.fetchall()
        except Exception:
            return []

        features = []
        for r in rows:
            exp_at = parse_iso(r["expires_at"]) if r["expires_at"] else None
            if exp_at and exp_at <= now:
                continue
            features.append({
                "id": str(r["id"]),
                "type": r["feature_type"],
                "details": r["details"],
                "source": r["source_kind"],
                "confidence": float(r["confidence"]),
                "observed_at": parse_iso(r["observed_at"]),
                "expires_at": exp_at
            })
        return features

    # --- User Preferences ---

    def get_user_preferences(self, user_id: str) -> dict:
        default = {"preferred_categories": [], "preferred_transport_mode": "DRIVE", "situation_defaults": {}}
        if self.is_postgres():
            try:
                with self._get_pg_conn() as conn, conn.cursor() as cur:
                    cur.execute("SELECT preferred_categories, preferred_transport_mode, situation_defaults FROM user_preferences WHERE user_id = %s", (user_id,))
                    row = cur.fetchone()
                if row:
                    return {"preferred_categories": row[0], "preferred_transport_mode": row[1], "situation_defaults": row[2]}
                return default
            except Exception:
                return default

        # SQLite
        try:
            with self._get_sqlite_conn() as conn:
                cur = conn.cursor()
                cur.execute("SELECT preferred_categories, preferred_transport_mode, situation_defaults FROM user_preferences WHERE user_id = ?", (user_id,))
                row = cur.fetchone()
            if row:
                cats = json.loads(row["preferred_categories"]) if isinstance(row["preferred_categories"], str) else row["preferred_categories"]
                sit = json.loads(row["situation_defaults"]) if isinstance(row["situation_defaults"], str) else row["situation_defaults"]
                return {"preferred_categories": cats, "preferred_transport_mode": row["preferred_transport_mode"], "situation_defaults": sit}
            return default
        except Exception:
            return default

    def save_user_preferences(self, user_id: str, data: dict) -> dict:
        cats_json = json.dumps(data.get("preferred_categories", []))
        mode = data.get("preferred_transport_mode", "DRIVE")
        sit_json = json.dumps(data.get("situation_defaults", {}))
        now_iso = datetime.now(timezone.utc).isoformat()

        if self.is_postgres():
            sql = """INSERT INTO user_preferences (user_id, preferred_categories, preferred_transport_mode, situation_defaults)
                     VALUES (%s, %s::jsonb, %s, %s::jsonb)
                     ON CONFLICT (user_id) DO UPDATE SET preferred_categories = EXCLUDED.preferred_categories, preferred_transport_mode = EXCLUDED.preferred_transport_mode, situation_defaults = EXCLUDED.situation_defaults, updated_at = NOW()"""
            with self._get_pg_conn() as conn, conn.cursor() as cur:
                cur.execute(sql, (user_id, cats_json, mode, sit_json))
            return data

        # SQLite
        sql = """INSERT INTO user_preferences (id, user_id, preferred_categories, preferred_transport_mode, situation_defaults, updated_at)
                 VALUES (?, ?, ?, ?, ?, ?)
                 ON CONFLICT(user_id) DO UPDATE SET preferred_categories = excluded.preferred_categories, preferred_transport_mode = excluded.preferred_transport_mode, situation_defaults = excluded.situation_defaults, updated_at = excluded.updated_at"""
        with self._get_sqlite_conn() as conn:
            cur = conn.cursor()
            cur.execute(sql, (str(uuid.uuid4()), user_id, cats_json, mode, sit_json, now_iso))
            conn.commit()
        return data


def get_db_adapter() -> DatabaseAdapter:
    if DatabaseAdapter._instance is None:
        DatabaseAdapter._instance = DatabaseAdapter()
    return DatabaseAdapter._instance
