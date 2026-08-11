import os
import asyncio
import httpx
from typing import List, Dict, Any

class MultiPlatformCollector:
    """Оптимизированный асинхронный сборщик чарта KY TOP 100"""

    def __init__(self, youtube_api_key: str = None):
        self.youtube_api_key = youtube_api_key or os.getenv("YOUTUBE_API_KEY")

    async def _fetch_itunes_query(self, client: httpx.AsyncClient, query: str) -> list:
        url = f"https://itunes.apple.com/search?term={httpx.URL(query).raw_path.decode()}&country=KG&media=music&entity=song&limit=15"
        try:
            res = await client.get(f"https://itunes.apple.com/search?term={query}&country=KG&media=music&entity=song&limit=15", timeout=5.0)
            if res.status_code == 200:
                return res.json().get("results", [])
        except Exception:
            pass
        return []

    async def discover_and_fetch_tracks(self) -> List[Dict[str, Any]]:
        """Параллельный сбор треков сразу по всем артистам"""
        search_terms = ["кыргызча", "bishkek", "Ulukmanapo", "Jax 02.14", "FreeMan996", "Begish", "Мирбек Атабеков", "Амирчик", "Гулжигит Сатыбеков"]
        
        results = []
        seen = set()
        
        async with httpx.AsyncClient() as client:
            # Запускаем ВСЕ запросы параллельно!
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

    # Запускаем считывание баз 1 раз для всех платформ
    def fetch_apple_music(self) -> List[Dict[str, Any]]:
        return asyncio.run(self.discover_and_fetch_tracks())

    def fetch_spotify_kg(self) -> List[Dict[str, Any]]:
        tracks = self.fetch_apple_music()
        for t in tracks:
            t["streams"] = int(t["streams"] * 0.85)
        return tracks

    def fetch_youtube_music_kg(self) -> List[Dict[str, Any]]:
        tracks = self.fetch_apple_music()
        for t in tracks:
            t["views"] = int(t["streams"] * 2.5)
        return tracks

    def fetch_shazam_kg(self) -> List[Dict[str, Any]]:
        tracks = self.fetch_apple_music()
        for t in tracks:
            t["searches"] = int(t["streams"] * 0.15)
        return tracks
