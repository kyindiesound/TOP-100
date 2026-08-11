import time
import logging
import os
import datetime
from typing import List, Dict, Any, Optional

from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship

from collectors import MultiPlatformCollector
from analytics import KYChartAnalyticsEngine

# ==========================================
# 1. НАСТРОЙКА ЛОГИРОВАНИЯ И СИСТЕМЫ
# ==========================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("KY_TOP_ENGINE")

# ==========================================
# 2. БАЗА ДАННЫХ И ORM МОДЕЛИ
# ==========================================
DATABASE_URL = "sqlite:///./ky_chart.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class ChartHistory(Base):
    """Таблица исторического snapshot'а прогонов чарта."""
    __tablename__ = "chart_history"

    id = Column(Integer, primary_key=True, index=True)
    snapshot_date = Column(DateTime, default=datetime.datetime.utcnow, index=True)
    total_tracks_processed = Column(Integer, default=0)
    
    entries = relationship("WeeklyChartEntry", back_populates="history_snapshot", cascade="all, delete-orphan")


class WeeklyChartEntry(Base):
    """Основная таблица позиций в чарте (строго топ-100)."""
    __tablename__ = "weekly_chart_entries"

    id = Column(Integer, primary_key=True, index=True)
    snapshot_id = Column(Integer, ForeignKey("chart_history.id"), nullable=True)
    position = Column(Integer, index=True)
    previous_position = Column(Integer, nullable=True)
    peak_position = Column(Integer, default=999)
    weeks_on_chart = Column(Integer, default=1)
    
    title = Column(String, index=True)
    artist = Column(String, index=True)
    cover_url = Column(String)
    
    total_score = Column(Integer, index=True)
    apple_streams = Column(Integer, default=0)
    spotify_streams = Column(Integer, default=0)
    youtube_views = Column(Integer, default=0)
    shazam_counts = Column(Integer, default=0)
    
    change_type = Column(String, default="NEW")
    change_value = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    history_snapshot = relationship("ChartHistory", back_populates="entries")


Base.metadata.create_all(bind=engine)

# ==========================================
# 3. PYDANTIC СХЕМЫ (DTO VALIDATION)
# ==========================================
class BreakdownSchema(BaseModel):
    apple_streams: int
    spotify_streams: int
    youtube_views: int
    shazam_counts: int


class TrackChartItemResponse(BaseModel):
    rank: int
    title: str
    artist: str
    cover_url: str
    ky_score: int
    peak: int
    weeks_on_chart: int
    change_type: str
    change_value: int
    breakdown: BreakdownSchema

    class Config:
        orm_mode = True


class PipelineStatusResponse(BaseModel):
    status: str
    message: str
    processed_tracks: int
    execution_time_seconds: float


# ==========================================
# 4. СЕРВИСНЫЙ СЛОЙ И КЭШ
# ==========================================
class MemoryCacheManager:
    """Управление in-memory кэшем данных."""
    def __init__(self, ttl_seconds: int = 300):
        self.ttl = ttl_seconds
        self._cache_store: Dict[str, Any] = {}
        self._timestamps: Dict[str, float] = {}

    def get(self, key: str) -> Optional[Any]:
        now = time.time()
        if key in self._cache_store:
            if now - self._timestamps.get(key, 0) < self.ttl:
                return self._cache_store[key]
            else:
                self.invalidate(key)
        return None

    def set(self, key: str, value: Any):
        self._cache_store[key] = value
        self._timestamps[key] = time.time()

    def invalidate(self):
        self._cache_store.clear()
        self._timestamps.clear()


cache_manager = MemoryCacheManager(ttl_seconds=300)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ==========================================
# 5. FASTAPI ПРИЛОЖЕНИЕ И РОУТЫ
# ==========================================
app = FastAPI(title="KY TOP 100 Analytics Engine", version="2.5.1")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", include_in_schema=False)
def read_root():
    if os.path.exists("index.html"):
        return FileResponse("index.html")
    return {"status": "ok", "service": "KY TOP 100 Chart Engine"}


@app.post("/api/v1/admin/run-pipeline")
@app.post("/api/v1/chart/recalculate")
def run_analytics_pipeline(db: Session = Depends(get_db)):
    """Запуск перерасчета и сохранение строго ТОП-100 треков."""
    start_time = time.time()
    logger.info("Запуск конвейера перерасчета чарта (ТОП-100)...")

    collector = MultiPlatformCollector()
    raw_data = collector.fetch_all_platform_data()
    consolidated = KYChartAnalyticsEngine.process_cross_platform_data(raw_data)

    scored_tracks = []
    for track in consolidated:
        bd = track["platform_breakdown"]
        score = int(
            bd["apple_streams"] * 1.0 +
            bd["spotify_streams"] * 1.0 +
            bd["youtube_views"] * 0.5 +
            bd["shazam_counts"] * 2.0
        )
        track["total_score"] = score
        scored_tracks.append(track)

    scored_tracks.sort(key=lambda x: x["total_score"], reverse=True)
    
    # СТРОГОЕ ОГРАНИЧЕНИЕ НА 100 ТРЕКОВ
    top_100 = scored_tracks[:100]

    old_entries = {
        f"{e.artist.lower().strip()} - {e.title.lower().strip()}": e
        for e in db.query(WeeklyChartEntry).all()
    }

    history_snapshot = ChartHistory(total_tracks_processed=len(top_100))
    db.add(history_snapshot)
    db.flush()

    db.query(WeeklyChartEntry).delete()

    for current_rank, track in enumerate(top_100, start=1):
        bd = track["platform_breakdown"]
        key = f"{track['artist'].lower().strip()} - {track['title'].lower().strip()}"
        
        prev_entry = old_entries.get(key)
        
        if prev_entry:
            prev_pos = prev_entry.position
            weeks = prev_entry.weeks_on_chart + 1
            peak = min(prev_entry.peak_position, current_rank)
            
            if current_rank < prev_pos:
                c_type, c_val = "UP", prev_pos - current_rank
            elif current_rank > prev_pos:
                c_type, c_val = "DOWN", current_rank - prev_pos
            else:
                c_type, c_val = "SAME", 0
        else:
            prev_pos = None
            weeks = 1
            peak = current_rank
            c_type, c_val = "NEW", 0

        entry = WeeklyChartEntry(
            snapshot_id=history_snapshot.id,
            position=current_rank,
            previous_position=prev_pos,
            peak_position=peak,
            weeks_on_chart=weeks,
            title=track["title"],
            artist=track["artist"],
            cover_url=track["cover_url"],
            total_score=track["total_score"],
            apple_streams=bd["apple_streams"],
            spotify_streams=bd["spotify_streams"],
            youtube_views=bd["youtube_views"],
            shazam_counts=bd["shazam_counts"],
            change_type=c_type,
            change_value=c_val
        )
        db.add(entry)

    db.commit()
    cache_manager.invalidate()
    
    elapsed = round(time.time() - start_time, 2)
    logger.info(f"Конвейер ТОП-100 завершен за {elapsed} сек.")

    return PipelineStatusResponse(
        status="success",
        message="Чарт успешно обновлен (ТОП-100).",
        processed_tracks=len(top_100),
        execution_time_seconds=elapsed
    )


@app.get("/api/v1/chart/analytics", response_model=List[TrackChartItemResponse])
def get_analytics_chart(db: Session = Depends(get_db)):
    """Отдача строго топ-100 треков с кэшированием."""
    cache_key = "chart_top_100"
    cached_data = cache_manager.get(cache_key)
    
    if cached_data:
        return cached_data

    entries = db.query(WeeklyChartEntry).order_by(WeeklyChartEntry.position.asc()).limit(100).all()
    
    result = []
    for entry in entries:
        result.append({
            "rank": entry.position,
            "title": entry.title,
            "artist": entry.artist,
            "cover_url": entry.cover_url,
            "ky_score": entry.total_score,
            "peak": entry.peak_position,
            "weeks_on_chart": entry.weeks_on_chart,
            "change_type": entry.change_type,
            "change_value": entry.change_value,
            "breakdown": {
                "apple_streams": entry.apple_streams,
                "spotify_streams": entry.spotify_streams,
                "youtube_views": entry.youtube_views,
                "shazam_counts": entry.shazam_counts
            }
        })

    cache_manager.set(cache_key, result)
    return result
