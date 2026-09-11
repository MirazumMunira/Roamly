import json
import psycopg
from fastapi import HTTPException
from app.core.config import get_settings


from app.db.adapter import get_db_adapter


class PreferenceService:
    def __init__(self):
        self.db = get_db_adapter()

    def get(self, user_id: str) -> dict:
        return self.db.get_user_preferences(user_id)

    def save(self, user_id: str, data: dict) -> dict:
        try:
            return self.db.save_user_preferences(user_id, data)
        except Exception as error:
            raise HTTPException(503, "Preferences could not be saved.") from error
