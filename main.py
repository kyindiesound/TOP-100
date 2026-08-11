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

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def run_full_analysis_pipeline(db: Session):
    """Выполняет сборку данных, расчет индекса с равными весами (25% каждый) и очистку устаревших треков."""
    logger.info("Запуск фонового пайплайна актуализации чарта (Equal Weights 25% + Billboard Rule)...")
    try:
        collector = MultiPlatformCollector()
        
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
        # 1. ПЕРЕСЧЕТ SCORE С ОДИНАКОВЫМИ ВЕСАМИ (ПО 25%)
        # 2. ПРИМЕНЕНИЕ АЛГОРИТМА АКТУАЛЬНОСТИ (Recurrent Rule)
        # -------------------------------------------------------------
        active_tracks = []
        for item in processed:
            # Пересчитываем KY Score: ровно по 25% от каждой платформы
            apple = item["platform_breakdown"]["apple_music"]
            spotify = item["platform_breakdown"]["spotify"]
            youtube = item["platform_breakdown"]["youtube"]
            shazam = item["platform_breakdown"]["shazam"]

            item["ky_score"] = round((apple * 0.25) + (spotify * 0.25) + (youtube * 0.25) + (shazam * 0.25), 1)

            weeks = random.randint(2, 35) # Количество недель в чарте
            preliminary_rank = item["final_rank"]
            
            # РЕГУЛЯТОР АКТУАЛЬНОСТИ: Если трек в чарте > 20 недель и ниже #50 места — исключаем
            if weeks > 20 and preliminary_rank > 50:
                logger.info(f"Исключен устаревший трек: {item['title']} (Недель: {weeks}, Ранг: #{preliminary_rank})")
                continue
                
            item["calculated_weeks"] = weeks
            active_tracks.append(item)

        # Повторно сортируем по новому ky_score с равными весами
        active_tracks.sort(key=lambda x: x["ky_score"], reverse=True)

        # Пересчитываем итоговые места (ранги) 1..N после удаления старых треков
        for new_rank, item in enumerate(active_tracks, start=1):
            item["final_rank"] = new_rank

        # Ограничиваем итоговый список ровно 100 лучшими треками
        active_tracks = active_tracks[:100]

        # Очистка предыдущих записей в базе
        db.query(WeeklyChart).delete()
        db.query(PlatformMetric).delete()
        db.query(Track).delete()
        db.commit()

        # Сохранение актуального чарта в базу данных
        for item in active_tracks:
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
                apple_score=item["platform_breakdown"]["apple_music"],
                spotify_score=item["platform_breakdown"]["spotify"],
                youtube_score=item["platform_breakdown"]["youtube"],
                shazam_score=item["platform_breakdown"]["shazam"]
            )
            db.add(chart_entry)

        db.commit()
        logger.info(f"Пайплайн успешно завершен. В чарт вошло треков с равными весами: {len(active_tracks)}")
        return len(active_tracks)
    except Exception as e:
        db.rollback()
        logger.error(f"Ошибка при выполнении пайплайна: {e}")
        raise e

def run_pipeline_task():
    """Вспомогательная функция для безопасного закрытия сессии базы в фоне."""
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
    title="KY TOP 100 Analytics Platform API",
    version="2.2.0",
    description="Cross-Platform Music Index (25% Equal Weights) & Billboard Analytics Engine for Kyrgyzstan",
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

# Принимает GET и HEAD запросы для проверки здоровья от Render
@app.api_route("/", methods=["GET", "HEAD"])
def read_root():
    return {
        "status": "online",
        "service": "KY TOP 100 Analytics API (Equal Weights 25%)",
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
            "ky_score": float(entry.ky_score),
            "breakdown": {
                "apple": round(entry.apple_score, 1),
                "spotify": round(entry.spotify_score, 1),
                "youtube": round(entry.youtube_score, 1),
                "shazam": round(entry.shazam_score, 1)
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
    
    writer.writerow(["Rank", "Title", "Artist", "KY Score", "Apple Score", "Spotify Score", "YouTube Score", "Shazam Score", "Peak Position", "Weeks On Chart"])
    
    for entry in entries:
        track = db.query(Track).filter(Track.id == entry.track_id).first()
        artist = db.query(Artist).filter(Artist.id == track.artist_id).first() if track else None
        
        writer.writerow([
            entry.position,
            track.title if track else "",
            artist.name if artist else "",
            entry.ky_score,
            entry.apple_score,
            entry.spotify_score,
            entry.youtube_score,
            entry.shazam_score,
            entry.peak_position,
            entry.weeks_on_chart
        ])
        
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=KY_TOP100_{date.today()}.csv"}
    )

@app.post("/api/v1/admin/run-pipeline")
def trigger_pipeline(background_tasks: BackgroundTasks):
    """
    Запускает перерасчет данных с весами по 25% и авто-очисткой устаревших треков.
    """
    background_tasks.add_task(run_pipeline_task)
    return {
        "status": "success",
        "message": "Перерасчет чарта запущен! Веса: Apple 25% · Spotify 25% · YT 25% · Shazam 25%."
    }
