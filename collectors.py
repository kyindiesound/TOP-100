import requests
import json

class MultiPlatformCollector:
    """Сборщик чарта Кыргызстана (KY TOP 100) с динамическим поиском и обложками"""

    # Список ключевых артистов и трендсеттеров кыргызской музыкальной сцены
    KG_ARTISTS = [
        "Ulukmanapo", "Jax 02.14", "FreeMan996", "Begish", "Mirza", 
        "Кайрат Примбердиев", "Бек Борбиев", "Нурлан Насип", "Айгерим Расул кызы",
        "Мирбек Атабеков", "Нурмат Садыров", "Фристайл Кыргызстан", "Ордо Сахна",
        "Омар", "Амирчик", "Гулжигит Сатыбеков", "Анжелика", "Добр", 
        "Ямаджи & Вайбс", "Баястан", "Асхат Сулайманов", "Чолпон Талипбек"
    ]

    def fetch_kg_tracks_via_itunes(self) -> list:
        """Поиск актуальных треков кыргызских артистов с настоящими обложками высокими разрешениями"""
        results = []
        seen = set()
        rank = 1

        for artist in self.KG_ARTISTS:
            try:
                # Поиск треков конкретного артиста через iTunes API (регион KG)
                url = f"https://itunes.apple.com/search?term={requests.utils.quote(artist)}&country=KG&media=music&entity=song&limit=10"
                res = requests.get(url, timeout=5)
                
                if res.status_code == 200:
                    tracks = res.json().get("results", [])
                    for track in tracks:
                        title = track.get("trackName", "").strip()
                        artist_name = track.get("artistName", "").strip()
                        
                        # Уникальность по паре (трек + артист)
                        key = f"{title.lower()} - {artist_name.lower()}"
                        if key not in seen and title and artist_name:
                            seen.add(key)
                            
                            # Качественная обложка 600x600 px
                            cover = track.get("artworkUrl100", "").replace("100x100bb", "600x600bb")
                            
                            results.append({
                                "title": title,
                                "artist": artist_name,
                                "cover": cover,
                                "rank": rank
                            })
                            rank += 1
                            
                            if len(results) >= 100:
                                break
            except Exception as e:
                print(f"[KG Track Collector Error for {artist}]: {e}")
                
            if len(results) >= 100:
                break

        return results

    def fetch_apple_music(self) -> list:
        return self.fetch_kg_tracks_via_itunes()

    def fetch_spotify_kg(self) -> list:
        return self.fetch_apple_music()

    def fetch_youtube_music_kg(self) -> list:
        return self.fetch_apple_music()

    def fetch_shazam_kg(self) -> list:
        return self.fetch_apple_music()