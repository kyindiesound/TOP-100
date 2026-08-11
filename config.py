import os
from typing import List, Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """
    Расширенный класс конфигурации приложения на базе Pydantic v2.
    Управляет всеми системными переменными, путями и параметрами безопасности.
    """
    
    # Основные метаданные проекта
    PROJECT_NAME: str = Field(default="KY TOP 100 Analytics API", description="Название API сервиса")
    VERSION: str = Field(default="2.5.1", description="Версия приложения")
    DEBUG_MODE: bool = Field(default=False, description="Режим отладки")
    
    # База данных
    DATABASE_URL: str = Field(
        default="sqlite:///./ky_chart.db",
        description="Строка подключения к базе данных (SQLite или PostgreSQL)"
    )
    
    # Кэширование
    CACHE_TTL_SECONDS: int = Field(
        default=300,
        description="Время жизни кэша в секундах (по умолчанию 5 минут)"
    )
    
    # Внешние ключи интеграций
    YOUTUBE_API_KEY: Optional[str] = Field(
        default=os.getenv("YOUTUBE_API_KEY", ""),
        description="API ключ Google Data v3 для расширенного сбора статистики"
    )
    
    # Лимиты чарта
    CHART_MAX_TRACKS: int = Field(
        default=100,
        description="Фиксированный размер топ-чарта"
    )
    
    # Сетевые настройки и CORS
    ALLOWED_ORIGINS: List[str] = Field(
        default=["*"],
        description="Список разрешенных доменов для CORS-запросов"
    )
    HOST: str = Field(default="0.0.0.0", description="Хост для запуска uvicorn")
    PORT: int = Field(default=10000, description="Порт для запуска приложения")

    # Конфигурация загрузки из .env файла
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

# Глобальный экземпляр настроек для импорта в другие модули
settings = Settings()
