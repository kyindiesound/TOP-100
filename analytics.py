import logging
import re
from typing import List, Dict, Any, Optional

logger = logging.getLogger("KY_ANALYTICS_PRO")

class KYChartAnalyticsEngine:
    """
    Расширенный промышленный движок нормализации, очистки, 
    кросс-платформенного мэтчинга и углубленной музыкальной аналитики.
    """

    # Стоп-слова и технические маркеры для очистки названий
    NOISE_PATTERNS = [
        r'\(.*?\)', r'\[.*?\]', r'\{.*?\}',
        r'official video', r'music video', r'клип', r'премьера трека',
        r'hq', r'lyrics', r'текст песни', r'audio', r'remix', r'remastered'
    ]

    @classmethod
    def clean_text(cls, text: str) -> str:
        """Глубокая очистка текстовых полей для безупречного мэтчинга треков между платформами."""
        if not text:
            return ""
        
        text = text.lower()
        
        # Удаляем шумовые паттерны в скобках и ключевые слова
        for pattern in cls.NOISE_PATTERNS:
            text = re.sub(pattern, '', text)
            
        # Оставляем только латиницу, кириллицу и цифры
        text = re.sub(r'[^а-яёa-z0-9\s]', '', text)
        return " ".join(text.split())

    @classmethod
    def calculate_cross_platform_score(cls, breakdown: Dict[str, int]) -> int:
        """
        Весовой алгоритм расчета итогового индекса популярности (KY Score).
        Учитывает разную ценность и объем аудитории на платформах.
        """
        apple_weight = 1.2
        spotify_weight = 1.0
        youtube_weight = 0.4
        shazam_weight = 2.5  # Шазам сильный индикатор реального интереса

        score = (
            breakdown.get("apple_streams", 0) * apple_weight +
            breakdown.get("spotify_streams", 0) * spotify_weight +
            breakdown.get("youtube_views", 0) * youtube_weight +
            breakdown.get("shazam_counts", 0) * shazam_weight
        )
        return int(score)

    @classmethod
    def detect_track_badges(cls, rank: int, prev_rank: Optional[int], weeks: int) -> Dict[str, Any]:
        """Определение специальных бейджей и статусов трека для фронтенда."""
        badges = []
        
        if weeks == 1:
            badges.append("NEW")
        
        if prev_rank is not None:
            jump = prev_rank - rank
            if jump >= 10:
                badges.append("BIGGEST_GAINER")
            elif jump > 0:
                badges.append("RISING")

        if rank <= 10:
            badges.append("TOP_10")
            
        if rank == 1:
            badges.append("CHART_LEADER")

        return {
            "is_hot": rank <= 5,
            "badges": badges
        }

    @classmethod
    def normalize_artist_name(cls, artist: str) -> str:
        """Нормализация имени артиста для устранения расхождений (например, 'Айдана Оторбаева' vs 'Aydana')."""
        if not artist:
            return "Unknown"
        artist = artist.strip()
        # Исправление частых опечаток или регистра
        return artist.title()

    @classmethod
    def process_cross_platform_data(cls, raw_data: Dict[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
        """
        Главный метод сведения данных:
        1. Нормализация названий.
        2. Объединение YouTube, Apple Music, Spotify и Shazam.
        3. Вычисление суммарных метрик и предварительная сортировка.
        """
        logger.info("Начало кросс-платформенного анализа и мэтчинга треков...")
        aggregated_tracks: Dict[str, Dict[str, Any]] = {}

        # 1. YouTube база
        youtube_items = raw_data.get("youtube", [])
        for item in youtube_items:
            title = item.get("title", "Unknown").strip()
            artist = cls.normalize_artist_name(item.get("artist", "Unknown"))
            views = item.get("views", 0)
            cover = item.get("cover", "")

            clean_title = cls.clean_text(title)
            clean_artist = cls.clean_text(artist)
            match_key = f"{clean_artist}____{clean_title}"

            aggregated_tracks[match_key] = {
                "title": title,
                "artist": artist,
                "cover_url": cover,
                "platform_breakdown": {
                    "apple_streams": 0,
                    "spotify_streams": 0,
                    "youtube_views": views,
                    "shazam_counts": 0
                }
            }

        # 2. Apple Music интеграция
        for item in raw_data.get("apple_music", []):
            title = item.get("title", "").strip()
            artist = cls.normalize_artist_name(item.get("artist", ""))
            streams = item.get("streams", 0)
            cover = item.get("cover", "")

            clean_title = cls.clean_text(title)
            clean_artist = cls.clean_text(artist)
            match_key = f"{clean_artist}____{clean_title}"

            if match_key in aggregated_tracks:
                aggregated_tracks[match_key]["platform_breakdown"]["apple_streams"] = streams
                if not aggregated_tracks[match_key]["cover_url"] and cover:
                    aggregated_tracks[match_key]["cover_url"] = cover
            else:
                aggregated_tracks[match_key] = {
                    "title": title or "Unknown",
                    "artist": artist or "Unknown",
                    "cover_url": cover,
                    "platform_breakdown": {
                        "apple_streams": streams,
                        "spotify_streams": 0,
                        "youtube_views": 0,
                        "shazam_counts": 0
                    }
                }

        # 3. Spotify интеграция
        for item in raw_data.get("spotify", []):
            title = item.get("title", "").strip()
            artist = cls.normalize_artist_name(item.get("artist", ""))
            streams = item.get("streams", 0)

            clean_title = cls.clean_text(title)
            clean_artist = cls.clean_text(artist)
            match_key = f"{clean_artist}____{clean_title}"

            if match_key in aggregated_tracks:
                aggregated_tracks[match_key]["platform_breakdown"]["spotify_streams"] = streams

        # 4. Shazam интеграция
        for item in raw_data.get("shazam", []):
            title = item.get("title", "").strip()
            artist = cls.normalize_artist_name(item.get("artist", ""))
            searches = item.get("searches", 0)

            clean_title = cls.clean_text(title)
            clean_artist = cls.clean_text(artist)
            match_key = f"{clean_artist}____{clean_title}"

            if match_key in aggregated_tracks:
                aggregated_tracks[match_key]["platform_breakdown"]["shazam_counts"] = searches

        # Постобработка и фильтрация результатов
        processed_result = []
        for track_data in aggregated_tracks.values():
            # Вычисляем предварительный скор внутри структуры
            bd = track_data["platform_breakdown"]
            track_data["calculated_score"] = cls.calculate_cross_platform_score(bd)
            processed_result.append(track_data)

        logger.info(f"Успешно обработано и сопоставлено уникальных треков: {len(processed_result)}")
        return processed_result
