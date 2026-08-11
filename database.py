import logging
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.engine import Engine

from config import settings

# Настройка системного логгера для базы данных
logger = logging.getLogger("KY_DATABASE_CORE")

# Определяем параметры подключения в зависимости от типа БД (SQLite / PostgreSQL)
engine_args = {}
if "sqlite" in settings.DATABASE_URL:
    engine_args["connect_args"] = {"check_same_thread": False}
    # Включаем внешние ключи для SQLite
    @event.listens_for(Engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
else:
    # Настройки пула соединений для production-баз данных (PostgreSQL / MySQL)
    engine_args["pool_size"] = 10
    engine_args["max_overflow"] = 20
    engine_args["pool_recycle"] = 3600

# Инициализация главного движка SQLAlchemy
engine = create_engine(settings.DATABASE_URL, **engine_args)

# Фабрика сессий
SessionLocal = sessionmaker(
    autocommit=False, 
    autoflush=False, 
    bind=engine,
    expire_on_commit=False
)

# Базовый класс для ORM моделей
Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """
    Генератор сессий базы данных для FastAPI Dependency Injection (Depends).
    Автоматически закрывает соединение и откатывает транзакции при исключениях.
    """
    db = SessionLocal()
    try:
        yield db
    except Exception as e:
        logger.error(f"Критическая ошибка в транзакции БД: {e}", exc_info=True)
        db.rollback()
        raise
    finally:
        db.close()


@contextmanager
def get_db_context() -> Generator[Session, None, None]:
    """
    Контекстный менеджер для работы с БД вне эндпоинтов FastAPI 
    (например, в фоновых задачах, скриптах сбора или CLI).
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception as e:
        logger.error(f"Ошибка в контекстном менеджере БД: {e}", exc_info=True)
        db.rollback()
        raise
    finally:
        db.close()


def init_db() -> None:
    """Полная инициализация схемы базы данных и создание таблиц."""
    try:
        logger.info(f"Инициализация подключения к БД по адресу: {settings.DATABASE_URL.split('://')[0]}://***")
        Base.metadata.create_all(bind=engine)
        logger.info("Таблицы базы данных успешно созданы / проверены.")
    except Exception as e:
        logger.error(f"Не удалось инициализировать структуру базы данных: {e}", exc_info=True)
        raise RuntimeError(f"Database initialization failed: {e}")


def check_db_health() -> bool:
    """Проверка доступности базы данных для healthcheck-эндпоинтов."""
    try:
        with engine.connect() as connection:
            connection.exec_driver_sql("SELECT 1")
        return True
    except Exception as e:
        logger.error(f"Healthcheck базы данных не пройден: {e}")
        return False
