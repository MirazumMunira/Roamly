"""Provider-based embeddings for Reality Layer semantic retrieval."""
import hashlib
import math
import httpx
from app.core.config import get_settings


class EmbeddingService:
    def __init__(self):
        self.settings = get_settings()

    @staticmethod
    def _deterministic_fallback(text: str, dimensions: int) -> list[float]:
        words = text.lower().split()
        vec = [0.0] * dimensions
        if not words:
            vec[0] = 1.0
            return vec
        for word in words:
            h = int(hashlib.md5(word.encode("utf-8")).hexdigest(), 16)
            idx = h % dimensions
            sign = 1.0 if (h >> 1) & 1 else -1.0
            vec[idx] += sign
        norm = math.sqrt(sum(x * x for x in vec))
        if norm > 0:
            vec = [x / norm for x in vec]
        else:
            vec[0] = 1.0
        return vec

    async def embed(self, text: str, task_type: str = "RETRIEVAL_DOCUMENT") -> list[float]:
        if self.settings.embedding_provider.lower() == "gemini" and self.settings.gemini_api_key:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.settings.gemini_embedding_model}:embedContent?key={self.settings.gemini_api_key}"
            payload = {
                "content": {"parts": [{"text": text}]},
                "outputDimensionality": self.settings.embedding_dimensions,
                "taskType": task_type
            }
            try:
                async with httpx.AsyncClient(timeout=20) as client:
                    response = await client.post(url, json=payload)
                if response.status_code == 200:
                    vector = response.json().get("embedding", {}).get("values", [])
                    if len(vector) == self.settings.embedding_dimensions:
                        return vector
                    elif len(vector) > self.settings.embedding_dimensions:
                        return vector[:self.settings.embedding_dimensions]
            except Exception:
                pass
        return self._deterministic_fallback(text, self.settings.embedding_dimensions)
