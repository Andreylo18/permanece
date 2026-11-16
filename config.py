"""Configuración de PERMANECE.

Toda credencial se lee de variables de entorno (archivo .env en desarrollo).
Nunca guardes contraseñas reales en el repositorio (RNF-05, QA-03).
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


def _load_dotenv():
    """Carga un .env simple sin dependencias externas."""
    env_file = BASE_DIR / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()


def _url_base_datos():
    """PostgreSQL (Neon) en producción; SQLite local si no hay DATABASE_URL.

    Neon y Render entregan URLs tipo postgres:// o postgresql://; SQLAlchemy
    necesita saber que el driver es psycopg (v3).
    """
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        return f"sqlite:///{BASE_DIR / 'permanece_dev.db'}"
    for prefijo in ("postgres://", "postgresql://"):
        if url.startswith(prefijo):
            return "postgresql+psycopg://" + url[len(prefijo):]
    return url


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "cambia-esta-clave-en-produccion")

    SQLALCHEMY_DATABASE_URI = _url_base_datos()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}
    if SQLALCHEMY_DATABASE_URI.startswith("postgresql"):
        # Falla con un error claro en vez de quedarse esperando si la red bloquea la conexión
        SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True, "pool_recycle": 280,
                                     "connect_args": {"connect_timeout": 15}}

    # Sesiones
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_HTTPONLY = True
    PERMANENT_SESSION_LIFETIME = 60 * 60 * 8  # 8 horas

    ITEMS_POR_PAGINA = 15
    ZONA_HORARIA = "America/Bogota"

    # Correo (Brevo, por API HTTPS: Render gratis bloquea los puertos SMTP)
    BREVO_API_KEY = os.environ.get("BREVO_API_KEY", "")
    CORREO_REMITENTE = os.environ.get("CORREO_REMITENTE", "")
    CORREO_NOMBRE = os.environ.get("CORREO_NOMBRE", "PERMANECE")
    # Dirección pública de la app, para los enlaces de los correos
    APP_URL = os.environ.get("APP_URL", "").rstrip("/")
    HORAS_VALIDEZ_ENLACE = 72


class ProductionConfig(Config):
    # RNF-01: cookies solo por HTTPS
    SESSION_COOKIE_SECURE = True
    REMEMBER_COOKIE_SECURE = True
    PREFERRED_URL_SCHEME = "https"


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = os.environ.get("TEST_DATABASE_URL", "sqlite:///:memory:")
    BREVO_API_KEY = ""
    APP_URL = "http://localhost"
    WTF_CSRF_ENABLED = False
    SECRET_KEY = "test"


config_por_nombre = {
    "development": Config,
    "production": ProductionConfig,
    "testing": TestingConfig,
}
