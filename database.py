import os
from sqlalchemy import create_engine, Column, Integer, String, Date, ForeignKey, Numeric, Float
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./ky_top100.db")

engine = create_engine(
    DATABASE_URL, 
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Artist(Base):
    __tablename__ = "artists"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, unique=True)
    avatar_url = Column(String(512), nullable=True)
    tracks = relationship("Track", back_populates="artist")

class Track(Base):
    __tablename__ = "tracks"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    artist_id = Column(Integer, ForeignKey("artists.id"))
    cover_url = Column(String(512), nullable=True)
    isrc = Column(String(32), nullable=True, index=True)  # Код трека для дедупликации
    
    artist = relationship("Artist", back_populates="tracks")
    raw_metrics = relationship("PlatformMetric", back_populates="track")
    charts = relationship("WeeklyChart", back_populates="track")

class PlatformMetric(Base):
    """Сырые данные с разбивкой по площадкам"""
    __tablename__ = "platform_metrics"
    id = Column(Integer, primary_key=True, index=True)
    track_id = Column(Integer, ForeignKey("tracks.id"))
    platform = Column(String(50), nullable=False)  # apple_music, spotify, youtube, shazam
    rank = Column(Integer, nullable=True)
    play_count = Column(Integer, default=0)
    shazams_count = Column(Integer, default=0)
    
    track = relationship("Track", back_populates="raw_metrics")

class WeeklyChart(Base):
    """Финальный скомпонованный чарт"""
    __tablename__ = "weekly_charts"
    id = Column(Integer, primary_key=True, index=True)
    track_id = Column(Integer, ForeignKey("tracks.id"))
    chart_date = Column(Date, index=True)
    position = Column(Integer, nullable=False)
    last_week_position = Column(Integer, nullable=True)
    peak_position = Column(Integer, nullable=False)
    weeks_on_chart = Column(Integer, default=1)
    
    # Финальные весовые баллы
    ky_score = Column(Numeric(12, 2), nullable=False)
    apple_score = Column(Float, default=0.0)
    spotify_score = Column(Float, default=0.0)
    youtube_score = Column(Float, default=0.0)
    shazam_score = Column(Float, default=0.0)

    track = relationship("Track", back_populates="charts")

def init_db():
    Base.metadata.create_all(bind=engine)