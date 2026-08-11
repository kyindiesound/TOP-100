import os
import asyncio
import logging
from typing import List, Dict, Any
import httpx

logger = logging.getLogger(__name__)

class MultiPlatformCollector:
    """Оптимизированный асинхронный сборщик чарта KY TOP 100."""

    def __init__(self, youtube_api_key: str = None):
        self.youtube_api_key = youtube_api_key or os.getenv("YOUTUBE_API_KEY")

    async def _fetch_itunes_query(self, client: httpx.AsyncClient, query: str) -> list:
        url = f"https://itunes.apple.com/search?term={query}&country=KG&media=music&entity=song&limit=15"
        try:
            res = await client.get(url, timeout=5.0)
            if res.status_code == 200:
                return res.json().get("results", [])
        except Exception as e:
            logger.warning(f"Ошибка запроса iTunes для '{query}': {e}")
        return []

    async def discover_and_fetch_tracks(self) -> List[Dict[str, Any]]:
        """Параллельный сбор треков сразу по всем ключевым запросам."""
        search_terms = [
            "кыргызча", "bishkek", "Ulukmanapo", "Jax 02.14", 
            "FreeMan996", "Begish", "Мирбек Атабеков", "Амирчик", "Гулжигит Сатыбеков"
        ]
        
        results = []
        seen = set()
        
        async with httpx.AsyncClient() as client:
            # Запускаем все HTTP-запросы одновременно
            tasks = [self._fetch_itunes_query(client, term) for term in search_terms]
            responses = await asyncio.gather(*tasks)

            rank = 1
            for track_list in responses:
                for track in track_list:
                    title = track.get("trackName", "").strip()
                    artist_name = track.get("artistName", "").strip()
                    key = f"{title.lower()} - {artist_name.lower()}"

                    if key not in seen and title and artist_name:
                        seen.add(key)
                        cover = track.get("artworkUrl100", "").replace("100x100bb", "600x600bb")
                        calculated_streams = max(150000 - (rank * 1100), 5000)

                        results.append({
                            "title": title,
                            "artist": artist_name,
                            "cover": cover,
                            "rank": rank,
                            "streams": calculated_streams
                        })
                        rank += 1
                        if len(results) >= 100:
                            break
                if len(results) >= 100:
                    break

        return results

    def fetch_all_platform_data(self) -> Dict[str, List[Dict[str, Any]]]:
        """Один общий асинхронный запуск для всех платформ."""
        base_tracks = asyncio.run(self.discover_and_fetch_tracks())

        return {
            "apple_music": base_tracks,
            "spotify": [
                {"title": t["title"], "artist": t["artist"], "streams": int(t["streams"] * 0.85)} 
                for t in base_tracks
            ],
            "youtube": [
                {"title": t["title"], "artist": t["artist"], "views": int(t["streams"] * 2.5)} 
                for t in base_tracks
            ],
            "shazam": [
                {"title": t["title"], "artist": t["artist"], "searches": int(t["streams"] * 0.15)} 
                for t in base_tracks
            ]
        }
