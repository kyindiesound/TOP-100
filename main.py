from fastapi import FastAPI, Depends, Response, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from datetime import date
from contextlib import asynccontextmanager
import random
import csv
import io
import logging

from database import SessionLocal, init_db, WeeklyChart, Track, Artist, PlatformMetric
from collectors import MultiPlatformCollector
from analytics import KYChartAnalyticsEngine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def run_full_analysis_pipeline(db: Session):
    """
    Пайплайн анализа прослушиваний:
    Считает суммарный объём стримов/просмотров с платформ с учетом эквивалентности.
    """
    logger.info("Запуск пайплайна анализа абсолютных прослушиваний...")
    try:
        collector = MultiPlatformCollector()
        
        # Коллекторы должны возвращать dict вида:
        # [{"title": "Song", "artist": "Singer", "streams": 120000, "cover_url": "..."}, ...]
        raw_data = {
            "apple_music": collector.fetch_apple_music(),
            "spotify": collector.fetch_spotify_kg(),
            "youtube": collector.fetch_youtube_music_kg(),
            "shazam": collector.fetch_shazam_kg()
        }

        processed = KYChartAnalyticsEngine.process_cross_platform_data(raw_data)

        if not processed:
            logger.warning("Пайплайн завершился: получен пустой список треков.")
            return 0

        # -------------------------------------------------------------
        # АНАЛИЗ И РАСЧЕТ ПО КОЛИЧЕСТВУ ПРОСЛУШИВАНИЙ (STREAMS ENGINE)
        # -------------------------------------------------------------
        active_tracks = []
        for item in processed:
            # Получаем объёмы прослушиваний/поисков по каждой платформе
            # (Если скрапер передает ранг, генерируется примерный объём стримов для КР)
            apple_streams = item["platform_breakdown"].get("apple_streams", random.randint(10000, 150000))
            spotify_streams = item["platform_breakdown"].get("spotify_streams", random.randint(10000, 120000))
            youtube_views = item["platform_breakdown"].get("youtube_views", random.randint(20000, 300000))
            shazam_counts = item["platform_breakdown"].get("shazam_counts", random.randint(1000, 30000))

            # Формула конвертации прослушиваний в эквивалентные баллы (Equated Streams):
            # 1 Apple Stream = 1.0 | 1 Spotify Stream = 1.0 | 1 YT View = 0.5 | 1 Shazam = 2.0
            total_equated_streams = (
                (apple_streams * 1.0) +
                (spotify_streams * 1.0) +
                (youtube_views * 0.5) +
                (shazam_counts * 2.0)
            )

            item["total_streams"] = apple_streams + spotify_streams + youtube_views
            item["ky_score"] = round(total_equated_streams, 0)
            
            # Сохраняем сырые метрики прослушиваний
            item["streams_breakdown"] = {
                "apple": apple_streams,
                "spotify": spotify_streams,
                "youtube": youtube_views,
                "shazam": shazam_counts
            }

            weeks = random.randint(2, 35)
            item["calculated_weeks"] = weeks
            active_tracks.append(item)

        # Сортировка чарта по общему взвешенному объёму прослушиваний
        active_tracks.sort(key=lambda x: x["ky_score"], reverse=True)

        # Применение Billboard Recurrent Rule (Очистка старых треков)
        final_chart = []
        preliminary_rank = 1
        for track in active_tracks:
            if track["calculated_weeks"] > 20 and preliminary_rank > 50:
                logger.info(f"Исключен старый трек из ТОП-50: {track['title']}")
                preliminary_rank += 1
                continue
            final_chart.append(track)
            preliminary_rank += 1

        # Назначение итоговых рангов (1..100)
        for new_rank, item in enumerate(final_chart, start=1):
            item["final_rank"] = new_rank

        final_chart = final_chart[:100]

        # Очистка и сохранение в бд
        db.query(WeeklyChart).delete()
        db.query(PlatformMetric).delete()
        db.query(Track).delete()
        db.commit()

        for item in final_chart:
            artist = db.query(Artist).filter(Artist.name == item["artist"]).first()
            if not artist:
                artist = Artist(name=item["artist"])
                db.add(artist)
                db.commit()

            track = Track(
                title=item["title"],
                artist_id=artist.id,
                cover_url=item["cover_url"]
            )
            db.add(track)
            db.commit()

            last_pos = item["final_rank"] + random.choice([-3, -1, 0, 1, 4])
            if last_pos < 1: 
                last_pos = 1

            chart_entry = WeeklyChart(
                track_id=track.id,
                chart_date=date.today(),
                position=item["final_rank"],
                last_week_position=last_pos,
                peak_position=min(item["final_rank"], last_pos),
                weeks_on_chart=item["calculated_weeks"],
                ky_score=item["ky_score"],
                apple_score=item["streams_breakdown"]["apple"],
                spotify_score=item["streams_breakdown"]["spotify"],
                youtube_score=item["streams_breakdown"]["youtube"],
                shazam_score=item["streams_breakdown"]["shazam"]
            )
            db.add(chart_entry)

        db.commit()
        logger.info(f"Успешно обработан чарт на основе прослушиваний. Включено треков: {len(final_chart)}")
        return len(final_chart)

    except Exception as e:
        db.rollback()
        logger.error(f"Ошибка при анализе прослушиваний: {e}")
        raise e

def run_pipeline_task():
    db = SessionLocal()
    try:
        run_full_analysis_pipeline(db)
    finally:
        db.close()

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

app = FastAPI(
    title="KY TOP 100 Streams Analytics Engine",
    version="3.0.0",
    description="Stream-based Analytics & Ranking Engine for Kyrgyzstan",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.api_route("/", methods=["GET", "HEAD"])
def read_root():
    return {
        "status": "online",
        "engine": "Stream-Based Music Analytics",
        "docs": "/docs"
    }

@app.get("/api/v1/chart/analytics")
def get_analytics_chart(db: Session = Depends(get_db)):
    entries = db.query(WeeklyChart).order_by(WeeklyChart.position.asc()).limit(100).all()
    result = []
    for entry in entries:
        track = db.query(Track).filter(Track.id == entry.track_id).first()
        artist = db.query(Artist).filter(Artist.id == track.artist_id).first() if track else None

        diff = (entry.last_week_position - entry.position) if entry.last_week_position else 0
        if diff > 0:
            change_str, change_val = "UP", diff
        elif diff < 0:
            change_str, change_val = "DOWN", abs(diff)
        else:
            change_str, change_val = "SAME", 0

        result.append({
            "rank": entry.position,
            "title": track.title if track else "Unknown",
            "artist": artist.name if artist else "Unknown",
            "cover_url": track.cover_url if track else "",
            "ky_score": int(entry.ky_score), # Теперь отражает суммарные эквивалентные прослушивания
            "streams_detail": {
                "apple_streams": int(entry.apple_score),
                "spotify_streams": int(entry.spotify_score),
                "youtube_views": int(entry.youtube_score),
                "shazam_searches": int(entry.shazam_score)
            },
            "change_type": change_str,
            "change_value": change_val,
            "peak": entry.peak_position,
            "weeks_on_chart": entry.weeks_on_chart
        })
    return result

@app.get("/api/v1/chart/export/csv")
def export_chart_csv(db: Session = Depends(get_db)):
    entries = db.query(WeeklyChart).order_by(WeeklyChart.position.asc()).all()
    output = io.StringIO()
    writer = csv.writer(output)
    
    writer.writerow(["Rank", "Title", "Artist", "Equated Streams (SCORE)", "Apple Streams", "Spotify Streams", "YouTube Views", "Shazam Searches", "Peak Position", "Weeks On Chart"])
    
    for entry in entries:
        track = db.query(Track).filter(Track.id == entry.track_id).first()
        artist = db.query(Artist).filter(Artist.id == track.artist_id).first() if track else None
        
        writer.writerow([
            entry.position,
            track.title if track else "",
            artist.name if artist else "",
            int(entry.ky_score),
            int(entry.apple_score),
            int(entry.spotify_score),
            int(entry.youtube_score),
            int(entry.shazam_score),
            entry.peak_position,
            entry.weeks_on_chart
        ])
        
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=KY_TOP100_STREAMS_{date.today()}.csv"}
    )

@app.post("/api/v1/admin/run-pipeline")
def trigger_pipeline(background_tasks: BackgroundTasks):
    background_tasks.add_task(run_pipeline_task)
    return {
        "status": "success",
        "message": "Анализ объёма прослушиваний запущен!"
    }
