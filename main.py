import time
import logging
import os
from typing import List
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlalchemy import create_engine, Column, Integer, String, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
import datetime

from collectors import MultiPlatformCollector
from analytics import KYChartAnalyticsEngine

# Настройка приложения и БД
app = FastAPI(title="KY TOP 100 Analytics API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATABASE_URL = "sqlite:///./ky_chart.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Модель базы данных
class WeeklyChart(Base):
    __tablename__ = "weekly_chart"

    id = Column(Integer, primary_key=True, index=True)
    position = Column(Integer, index=True)
    title = Column(String)
    artist = Column(String)
    cover_url = Column(String)
    total_score = Column(Integer)
    apple_streams = Column(Integer, default=0)
    spotify_streams = Column(Integer, default=0)
    youtube_views = Column(Integer, default=0)
    shazam_counts = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Кэш в памяти для мгновенной отдачи чарта (на 5 минут)
CACHE_TTL = 300
_chart_cache = {"timestamp": 0, "data": None}

def invalidate_cache():
    _chart_cache["timestamp"] = 0
    _chart_cache["data"] = None

@app.get("/")
def read_root():
    """Отдача index.html или статуса сервера."""
    if os.path.exists("index.html"):
        return FileResponse("index.html")
    return {"status": "ok", "message": "KY TOP 100 API Service is Running"}

@app.post("/api/v1/admin/run-pipeline")
@app.post("/api/v1/chart/recalculate")
def recalculate_chart(db: Session = Depends(get_db)):
    """Запуск оптимизированного конвейера расчета чарта."""
    collector = MultiPlatformCollector()
    
    # 1. Быстрый асинхронный сбор данных с платформ
    raw_data = collector.fetch_all_platform_data()
    
    # 2. Нормализация и агрегация
    consolidated = KYChartAnalyticsEngine.process_cross_platform_data(raw_data)
    
    # 3. Расчёт итогового индекса KY Score
    scored_tracks = []
    for track in consolidated:
        breakdown = track["platform_breakdown"]
        score = int(
            breakdown["apple_streams"] * 1.0 +
            breakdown["spotify_streams"] * 1.0 +
            breakdown["youtube_views"] * 0.5 +
            breakdown["shazam_counts"] * 2.0
        )
        track["total_score"] = score
        scored_tracks.append(track)
        
    scored_tracks.sort(key=lambda x: x["total_score"], reverse=True)
    top_100 = scored_tracks[:100]

    # 4. Обновление БД
    db.query(WeeklyChart).delete()
    
    for rank, track in enumerate(top_100, start=1):
        bd = track["platform_breakdown"]
        entry = WeeklyChart(
            position=rank,
            title=track["title"],
            artist=track["artist"],
            cover_url=track["cover_url"],
            total_score=track["total_score"],
            apple_streams=bd["apple_streams"],
            spotify_streams=bd["spotify_streams"],
            youtube_views=bd["youtube_views"],
            shazam_counts=bd["shazam_counts"]
        )
        db.add(entry)
        
    db.commit()
    
    # Сбрасываем кэш после перерасчёта
    invalidate_cache()
    
    return {"status": "success", "processed_tracks": len(top_100)}

@app.get("/api/v1/chart/analytics")
def get_analytics_chart(db: Session = Depends(get_db)):
    """Получение ТОП-100 с названиями полей, совпадающими с фронтендом."""
    now = time.time()
    
    # Отдаем кэш, если он не устарел
    if _chart_cache["data"] and (now - _chart_cache["timestamp"] < CACHE_TTL):
        return _chart_cache["data"]

    entries = db.query(WeeklyChart).order_by(WeeklyChart.position.asc()).limit(100).all()
    
    result = []
    for entry in entries:
        result.append({
            "rank": entry.position,
            "title": entry.title,
            "artist": entry.artist,
            "cover_url": entry.cover_url,
            "ky_score": entry.total_score,
            "peak": entry.position,
            "weeks_on_chart": 1,
            "change_type": "NEW",
            "change_value": 0,
            "breakdown": {
                "apple_streams": entry.apple_streams,
                "spotify_streams": entry.spotify_streams,
                "youtube_views": entry.youtube_views,
                "shazam_counts": entry.shazam_counts
            }
        })

    _chart_cache["timestamp"] = now
    _chart_cache["data"] = result
    return result
