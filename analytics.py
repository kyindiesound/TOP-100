class KYChartAnalyticsEngine:
    """Математический движок сведе́ния мультиплатформенных рейтингов в единый KY Score"""

    WEIGHTS = {
        "apple_music": 0.35,
        "spotify": 0.25,
        "youtube": 0.25,
        "shazam": 0.15
    }

    @classmethod
    def calculate_points(cls, rank: int) -> float:
        """Инверсивная формула распределения очков от 1 до 100 места"""
        if not rank or rank > 100:
            return 0.0
        return float((101 - rank) ** 1.35)

    @classmethod
    def process_cross_platform_data(cls, raw_data: dict) -> list:
        aggregated = {}

        for platform, tracks in raw_data.items():
            weight = cls.WEIGHTS.get(platform, 0.1)
            for item in tracks:
                # Нормализация названия для точного мэтчинга треков
                key = f"{item['title'].strip().lower()} - {item['artist'].strip().lower()}"
                
                if key not in aggregated:
                    aggregated[key] = {
                        "title": item["title"],
                        "artist": item["artist"],
                        "cover_url": item.get("cover", "https://images.unsplash.com/photo-1511671782779-c97d3d27a1d4?w=300"),
                        "scores": {"apple_music": 0.0, "spotify": 0.0, "youtube": 0.0, "shazam": 0.0}
                    }
                
                points = cls.calculate_points(item.get("rank", 100))
                aggregated[key]["scores"][platform] = points * weight

        # Расчет итогового KY Score
        final_chart = []
        for key, data in aggregated.items():
            total_ky_score = sum(data["scores"].values()) * 10
            final_chart.append({
                "title": data["title"],
                "artist": data["artist"],
                "cover_url": data["cover_url"],
                "ky_score": round(total_ky_score, 2),
                "platform_breakdown": data["scores"]
            })

        # Сортировка по увязанному рейтингу
        final_chart.sort(key=lambda x: x["ky_score"], reverse=True)
        
        # Присвоение итоговых позиций
        for rank, track in enumerate(final_chart, start=1):
            track["final_rank"] = rank

        return final_chart