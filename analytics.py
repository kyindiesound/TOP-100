import re
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class KYChartAnalyticsEngine:
    """
    Аналитический движок для сведения, очистки и взвешенного подсчета 
    прослушиваний треков с различных платформ в Кыргызстане.
    """

    @staticmethod
    def _normalize_string(text: str) -> str:
        """Приводит название трека/артиста к единому виду для сравнения."""
        if not text:
            return ""
        text = text.lower()
        # Удаляем лишние символы, скобки, feat, ft и спецсимволы
        text = re.sub(r'\(.*?\)|\[.*?\]', '', text)
        text = re.sub(r'\b(feat|ft|featuring|remix|prod)\b.*', '', text)
        text = re.sub(r'[^a-zA-Zа-яА-Я0-9\s]', '', text)
        return ' '.join(text.split())

    @classmethod
    def process_cross_platform_data(cls, raw_data: Dict[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
        """
        Принимает сырые данные от MultiPlatformCollector и объединяет их по трекам.
        
        Ожидаемая структура raw_data:
        {
            "apple_music": [...],
            "spotify": [...],
            "youtube": [...],
            "shazam": [...]
        }
        """
        consolidated_tracks: Dict[str, Dict[str, Any]] = {}

        # 1. Агрегация Apple Music
        for item in raw_data.get("apple_music", []):
            title = item.get("title", "")
            artist = item.get("artist", "")
            norm_key = f"{cls._normalize_string(title)}_{cls._normalize_string(artist)}"

            if not norm_key or norm_key == "_":
                continue

            consolidated_tracks[norm_key] = {
                "title": title,
                "artist": artist,
                "cover_url": item.get("cover", ""),
                "platform_breakdown": {
                    "apple_streams": item.get("streams", 0),
                    "spotify_streams": 0,
                    "youtube_views": 0,
                    "shazam_counts": 0
                }
            }

        # 2. Агрегация Spotify
        for item in raw_data.get("spotify", []):
            norm_key = f"{cls._normalize_string(item.get('title', ''))}_{cls._normalize_string(item.get('artist', ''))}"
            if norm_key in consolidated_tracks:
                consolidated_tracks[norm_key]["platform_breakdown"]["spotify_streams"] = item.get("streams", 0)

        # 3. Агрегация YouTube
        for item in raw_data.get("youtube", []):
            norm_key = f"{cls._normalize_string(item.get('title', ''))}_{cls._normalize_string(item.get('artist', ''))}"
            if norm_key in consolidated_tracks:
                consolidated_tracks[norm_key]["platform_breakdown"]["youtube_views"] = item.get("views", 0)

        # 4. Агрегация Shazam
        for item in raw_data.get("shazam", []):
            norm_key = f"{cls._normalize_string(item.get('title', ''))}_{cls._normalize_string(item.get('artist', ''))}"
            if norm_key in consolidated_tracks:
                consolidated_tracks[norm_key]["platform_breakdown"]["shazam_counts"] = item.get("searches", 0)

        results = list(consolidated_tracks.values())
        logger.info(f"Сведено {len(results)} уникальных треков из сырых данных.")
        return results
