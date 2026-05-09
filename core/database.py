"""
Database Configuration - SQLAlchemy
====================================
Engine, Session Factory y utilidades de base de datos para el bot Magic.

Características:
- Pool de conexiones configurable vía settings.
- pool_pre_ping para detectar conexiones muertas.
- SessionLocal como factory de sesiones.
- get_db() como generador para dependency injection.

Uso:
    from core.database import SessionLocal, get_db, init_db

    db = SessionLocal()
    try:
        # usar db...
        db.commit()
    finally:
        db.close()
"""

from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from config.settings import settings

# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

engine = create_engine(
    settings.DATABASE_URL,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_timeout=settings.DB_POOL_TIMEOUT,
    pool_pre_ping=True,           # Verifica que la conexión siga viva
    pool_recycle=3600,            # Recicla conexiones cada hora
    echo=settings.DEBUG,          # Log de queries SQL en modo debug
)

# ---------------------------------------------------------------------------
# Session Factory
# ---------------------------------------------------------------------------

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)

# ---------------------------------------------------------------------------
# Dependency Injection Helper
# ---------------------------------------------------------------------------


def get_db() -> Generator[Session, None, None]:
    """
    Generador de sesiones de base de datos para dependency injection.

    Uso típico:
        db = next(get_db())
        try:
            # usar db...
        finally:
            db.close()

    O como context manager usando contextlib.contextmanager.
    """
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Table Initialization
# ---------------------------------------------------------------------------


def init_db() -> None:
    """
    Crea todas las tablas definidas en los modelos de SQLAlchemy.

    Debe llamarse una vez al iniciar la aplicación, después de que
    todos los modelos hayan sido importados.
    """
    from models.base import Base

    Base.metadata.create_all(bind=engine)
